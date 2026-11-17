"""Paso 3 del taller (10 %). Funciones que actualizan la base consolidada.

La función principal es procesar_dia(). Recibe los archivos diarios del paso 1
(datos_AAAA-MM-DD.csv y manifiesto_AAAA-MM-DD.json) y

  * incorpora los anuncios nuevos y actualiza los existentes sin perder su historia,
  * registra una sola observación por anuncio y por día,
  * anota en la tabla 'cambios' lo que cambió (precio, kilometraje, disponibilidad...),
  * distingue entre encontrado, no encontrado en una búsqueda completa y
    disponibilidad desconocida porque la búsqueda tuvo errores,
  * es idempotente. Procesar dos veces el mismo archivo no cambia nada, porque se
    guarda la huella SHA-256 de los archivos de cada día.

Un fallo de descarga no demuestra que el carro salió de oferta. Por eso un anuncio
que se encontró pero no se pudo descargar queda 'encontrado' sin datos ese día, y
su información más reciente sigue siendo la del último día en que sí se descargó.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from contextlib import closing
from datetime import date
from itertools import combinations
from pathlib import Path

from . import paso1_extraccion as extraccion
from .paso1_recoleccion import DESCARGADO, leer_csv
from .paso2_base_de_datos import (CAMPOS_COMPARADOS, CAMPOS_VEHICULO, COLUMNAS_OBSERVACION, DESCONOCIDA,
                                  ENCONTRADO, NO_ENCONTRADO, SQL_RECONSTRUIR_ANUNCIOS, conectar)


# --- Utilidades ---------------------------------------------------------------------------
def huella(*rutas: Path) -> str:
    sha = hashlib.sha256()
    for ruta in rutas:
        if ruta is not None and Path(ruta).exists():
            sha.update(Path(ruta).read_bytes())
    return sha.hexdigest()


def _a_sql(valor):
    if isinstance(valor, bool):
        return int(valor)
    if isinstance(valor, float) and math.isnan(valor):
        return None
    return valor


def _iguales(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    try:
        return math.isclose(float(a), float(b), rel_tol=0, abs_tol=1e-6)
    except (TypeError, ValueError):
        return str(a).strip() == str(b).strip()


def _como_texto(valor) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor)


# --- La función de actualización ------------------------------------------------------
def procesar_dia(ruta_bd: Path, ruta_datos: Path, ruta_manifiesto: Path | None = None,
                 run_id: str | None = None, fecha: date | None = None) -> dict:
    """Recibe los archivos diarios del paso 1 y actualiza la base consolidada.

    * Incorpora los anuncios nuevos y actualiza los existentes.
    * Registra una observación por anuncio y día (nunca duplica anuncios).
    * Distingue encontrado / no encontrado en una búsqueda completa /
      disponibilidad desconocida por un error de la búsqueda.
    * Es idempotente: si los archivos de ese día ya se procesaron con el mismo
      contenido, no cambia nada; si cambiaron (por ejemplo, se re-ejecutó el día),
      reemplaza las observaciones de ese día y recalcula lo que depende de ellas.
    """
    ruta_datos = Path(ruta_datos)
    manifiesto = {}
    if ruta_manifiesto is not None and Path(ruta_manifiesto).exists():
        manifiesto = json.loads(Path(ruta_manifiesto).read_text(encoding="utf-8"))
    if fecha is None:
        fecha = date.fromisoformat(manifiesto.get("fecha") or ruta_datos.stem.split("_")[-1])
    dia = fecha.isoformat()
    run_id = run_id or manifiesto.get("run_id")
    # Sin manifiesto no hay forma de saber si la búsqueda fue completa: se asume que no.
    busqueda_completa = bool(manifiesto.get("busqueda_completa", False))
    filas = leer_csv(ruta_datos)
    firma = huella(ruta_datos, ruta_manifiesto)

    with closing(conectar(ruta_bd)) as con:
        previa = con.execute("SELECT huella_sha256 FROM archivos_procesados WHERE fecha = ?", (dia,)).fetchone()
        if previa and previa[0] == firma:
            metricas = calcular_metricas(con, dia)
            metricas.update(ya_procesado=True, tamano_bd_bytes=Path(ruta_bd).stat().st_size)
            return metricas

        with con:  # una sola transacción: o se aplica todo o nada
            con.execute("DELETE FROM observaciones WHERE fecha = ?", (dia,))
            vistos_hoy = set()
            marcadores = ", ".join("?" for _ in COLUMNAS_OBSERVACION)
            for fila in filas:
                id_anuncio = fila["id_anuncio"]
                if not id_anuncio or id_anuncio in vistos_hoy:
                    continue
                vistos_hoy.add(id_anuncio)
                registro = {c: fila.get(c) for c in COLUMNAS_OBSERVACION}
                registro.update(fecha=dia, run_id=run_id, disponibilidad=ENCONTRADO)
                if fila.get("estado_descarga") != DESCARGADO:
                    # Sin descarga exitosa no hay datos del vehículo para ese día.
                    for campo in CAMPOS_VEHICULO + ["cumple_criterios", "motivo_no_cumple"]:
                        registro[campo] = None
                con.execute(f"INSERT INTO observaciones ({', '.join(COLUMNAS_OBSERVACION)}) VALUES ({marcadores})",
                            [_a_sql(registro[c]) for c in COLUMNAS_OBSERVACION])

            # Anuncios conocidos que hoy no aparecieron.
            disponibilidad = NO_ENCONTRADO if busqueda_completa else DESCONOCIDA
            conocidos = [f[0] for f in con.execute(
                "SELECT DISTINCT id_anuncio FROM observaciones WHERE fecha < ?", (dia,))]
            for id_anuncio in conocidos:
                if id_anuncio in vistos_hoy:
                    continue
                url = con.execute("SELECT url FROM observaciones WHERE id_anuncio = ? AND url IS NOT NULL "
                                  "ORDER BY fecha DESC LIMIT 1", (id_anuncio,)).fetchone()
                con.execute("INSERT INTO observaciones (id_anuncio, fecha, run_id, url, disponibilidad) "
                            "VALUES (?, ?, ?, ?, ?)", (id_anuncio, dia, run_id, url[0] if url else None, disponibilidad))

            recalcular_cambios(con, desde=dia)
            _reconstruir_anuncios(con)
            detectar_posibles_duplicados(con, dia)
            con.execute("INSERT OR REPLACE INTO archivos_procesados VALUES (?, ?, ?, ?, ?, ?)",
                        (dia, ruta_datos.name, firma, _ahora_iso(), run_id, len(filas)))

        metricas = calcular_metricas(con, dia)
    metricas.update(ya_procesado=False, tamano_bd_bytes=Path(ruta_bd).stat().st_size,
                    busqueda_completa=busqueda_completa)
    return metricas


def _ahora_iso() -> str:
    from . import configuracion as config
    return config.iso(config.ahora())


def _reconstruir_anuncios(con: sqlite3.Connection) -> None:
    # executescript haría COMMIT por su cuenta; por eso se ejecuta sentencia por sentencia.
    borrar, insertar = SQL_RECONSTRUIR_ANUNCIOS.strip().split(";", 1)
    con.execute(borrar)
    con.execute(insertar.strip().rstrip(";"))


def recalcular_cambios(con: sqlite3.Connection, desde: str) -> None:
    """Compara cada observación con la anterior del mismo anuncio y anota las diferencias.

    Se recalcula desde la fecha procesada en adelante, para que re-procesar un
    día viejo deje coherentes los cambios de los días siguientes.
    """
    con.execute("DELETE FROM cambios WHERE fecha >= ?", (desde,))
    nuevos = []
    anterior_id = None
    ultimo_estado = ultimo_dato = None
    for obs in con.execute("SELECT * FROM observaciones ORDER BY id_anuncio, fecha"):
        if obs["id_anuncio"] != anterior_id:
            anterior_id, ultimo_estado, ultimo_dato = obs["id_anuncio"], None, None
        if obs["fecha"] >= desde:
            if ultimo_estado is not None and obs["disponibilidad"] != ultimo_estado["disponibilidad"]:
                nuevos.append((obs["id_anuncio"], obs["fecha"], "disponibilidad",
                               ultimo_estado["disponibilidad"], obs["disponibilidad"], ultimo_estado["fecha"]))
            if obs["estado_descarga"] == DESCARGADO and ultimo_dato is not None:
                for campo in CAMPOS_COMPARADOS:
                    if not _iguales(ultimo_dato[campo], obs[campo]):
                        nuevos.append((obs["id_anuncio"], obs["fecha"], campo, _como_texto(ultimo_dato[campo]),
                                       _como_texto(obs[campo]), ultimo_dato["fecha"]))
        ultimo_estado = obs
        if obs["estado_descarga"] == DESCARGADO:
            ultimo_dato = obs
    con.executemany("INSERT INTO cambios VALUES (?, ?, ?, ?, ?, ?)", nuevos)


def detectar_posibles_duplicados(con: sqlite3.Connection, dia: str) -> None:
    """Marca parejas de anuncios distintos que podrían ser el mismo vehículo.

    Criterio: mismo año, nivel de versión, transmisión, color y ciudad, con
    kilometraje casi igual (diferencia de máximo 3 % o 2.000 km) y precio a menos
    de 10 %. Solo se marca, no se fusiona: dos carros iguales de un mismo
    concesionario también cumplirían estas condiciones.
    """
    anuncios = [dict(f) for f in con.execute(
        "SELECT id_anuncio, anio, version, transmision, color, ciudad, kilometraje, precio "
        "FROM anuncios WHERE precio IS NOT NULL AND kilometraje IS NOT NULL")]
    parejas = set()
    for a, b in combinations(anuncios, 2):
        claves_a = (a["anio"], extraccion.nivel_version(a["version"]), extraccion.normalizar(a["transmision"]),
                    extraccion.normalizar(a["color"]), extraccion.normalizar(a["ciudad"]))
        claves_b = (b["anio"], extraccion.nivel_version(b["version"]), extraccion.normalizar(b["transmision"]),
                    extraccion.normalizar(b["color"]), extraccion.normalizar(b["ciudad"]))
        if claves_a != claves_b or not all(claves_a):
            continue
        km_ok = abs(a["kilometraje"] - b["kilometraje"]) <= max(2000, 0.03 * max(a["kilometraje"], b["kilometraje"]))
        precio_ok = abs(a["precio"] - b["precio"]) <= 0.10 * max(a["precio"], b["precio"])
        if km_ok and precio_ok:
            parejas.add(tuple(sorted((a["id_anuncio"], b["id_anuncio"]))))
    actuales = {(f[0], f[1]) for f in con.execute("SELECT id_a, id_b FROM posibles_duplicados")}
    for pareja in actuales - parejas:
        con.execute("DELETE FROM posibles_duplicados WHERE id_a = ? AND id_b = ?", pareja)
    criterio = "mismo año, versión, caja, color y ciudad; km y precio casi iguales"
    for id_a, id_b in parejas - actuales:
        con.execute("INSERT INTO posibles_duplicados VALUES (?, ?, ?, ?)", (id_a, id_b, criterio, dia))


def calcular_metricas(con: sqlite3.Connection, dia: str) -> dict:
    """Agregados, actualizados y sin cambios de un día, calculados desde la base.

    Como salen de la base y no de un contador, repetir el procesamiento da
    exactamente los mismos números.
    """
    def ids(sql: str) -> set[str]:
        return {f[0] for f in con.execute(sql, (dia,))}

    encontrados = ids("SELECT id_anuncio FROM observaciones WHERE fecha = ? AND disponibilidad = 'encontrado'")
    del_dia = ids("SELECT id_anuncio FROM observaciones WHERE fecha = ?")
    previos = ids("SELECT DISTINCT id_anuncio FROM observaciones WHERE fecha < ?")
    con_cambios = ids("SELECT DISTINCT id_anuncio FROM cambios WHERE fecha = ?")
    conteo = {f[0]: f[1] for f in con.execute(
        "SELECT disponibilidad, COUNT(*) FROM observaciones WHERE fecha = ? GROUP BY disponibilidad", (dia,))}
    return {
        "registros_agregados": len(encontrados - previos),
        "registros_actualizados": len((del_dia & previos) & con_cambios),
        "registros_sin_cambios": len((del_dia & previos) - con_cambios),
        "observaciones_del_dia": len(del_dia),
        "encontrados": conteo.get(ENCONTRADO, 0),
        "no_encontrados": conteo.get(NO_ENCONTRADO, 0),
        "disponibilidad_desconocida": conteo.get(DESCONOCIDA, 0),
        "cambios_registrados": con.execute("SELECT COUNT(*) FROM cambios WHERE fecha = ?", (dia,)).fetchone()[0],
        "anuncios_unicos": con.execute("SELECT COUNT(*) FROM anuncios").fetchone()[0],
    }


# --- Utilidades de mantenimiento y entrega ----------------------------------------------
def reconstruir_desde_archivos(ruta_bd: Path, carpeta_diarios: Path) -> list[dict]:
    """Borra la base y la vuelve a construir procesando todos los días en orden.

    Demuestra que la base es reproducible a partir de los archivos diarios.
    """
    ruta_bd = Path(ruta_bd)
    if ruta_bd.exists():
        ruta_bd.unlink()
    resultados = []
    for ruta_datos in sorted(Path(carpeta_diarios).glob("datos_*.csv")):
        fecha = ruta_datos.stem.split("_")[-1]
        manifiesto = ruta_datos.with_name(f"manifiesto_{fecha}.json")
        resultados.append({"fecha": fecha, **procesar_dia(ruta_bd, ruta_datos, manifiesto)})
    return resultados



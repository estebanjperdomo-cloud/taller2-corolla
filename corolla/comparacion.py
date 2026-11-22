"""Comparación entre modelos (Toyota Corolla, Mazda 3 y Kia K3).

El taller evalúa la comparación entre vehículos. Cada modelo ya tiene su propio análisis
diario (paso 6). Este módulo los pone lado a lado con las mismas reglas para los tres.

* El mismo día para todos, el último que tienen los tres, y un anuncio cuenta una sola vez.
* Precios comparados por año del modelo, porque comparar solo medianas engaña cuando un
  modelo tiene carros más nuevos que otro (todos los Kia K3 publicados son 2025 o 2026).
* Un mismo modelo de precios simple para los tres (logaritmo del precio contra el año y el
  logaritmo del kilometraje), así el efecto de cada año y de cada kilómetro se puede comparar.
  Es más sencillo que el del paso 6, que además usa la versión de cada marca.
* Lo que pasó en el periodo que tienen en común: anuncios distintos, cambios de precio,
  anuncios que dejaron de aparecer y posibles gangas del análisis diario.

Solo lee las bases y los reportes, nunca los modifica. python taller.py comparar escribe en
entrega/comparacion/ una tabla (CSV), el detalle (JSON) y una gráfica (PNG).
"""
from __future__ import annotations

import csv
import json
import math
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

import numpy as np

from . import configuracion as config, formato
from .paso6_analisis import PRECIO_MAX, PRECIO_MIN

CARPETA = Path("entrega") / "comparacion"
ANIO_CENTRO = 2024      # el año se mide desde 2024 para que la constante del modelo sea legible


def fuentes(modo: str = "oficial", raiz_datos: Path | None = None) -> list[tuple[str, config.Rutas]]:
    """Los tres modelos con sus carpetas, el Corolla primero."""
    raiz = raiz_datos or config.carpeta_datos()
    lista = [("Toyota Corolla", config.Rutas(modo, raiz))]
    lista += [(b.nombre, config.rutas_modelo(b, modo, raiz)) for b in config.MODELOS_EXTRA]
    return lista


def _consultar(ruta_bd: Path, sql: str, parametros: tuple = ()) -> list[tuple]:
    """Consulta de solo lectura. Si la base no existe devuelve una lista vacía."""
    if not ruta_bd.exists():
        return []
    with closing(sqlite3.connect(ruta_bd.resolve().as_uri() + "?mode=ro", uri=True)) as con:
        return con.execute(sql, parametros).fetchall()


def dias_con_datos(rutas: config.Rutas) -> list[str]:
    return [f for (f,) in _consultar(rutas.bd, "SELECT DISTINCT fecha FROM observaciones "
                                               "WHERE disponibilidad = 'encontrado' ORDER BY fecha")]


def anuncios_del_dia(rutas: config.Rutas, fecha: str) -> list[dict]:
    """Anuncios encontrados ese día que cumplen los criterios y tienen un precio válido."""
    filas = _consultar(rutas.bd, """
        SELECT id_anuncio, anio, precio, kilometraje, combustible FROM observaciones
        WHERE fecha = ? AND disponibilidad = 'encontrado' AND cumple_criterios = 1
          AND precio BETWEEN ? AND ?""", (fecha, PRECIO_MIN, PRECIO_MAX))
    return [dict(zip(("id", "anio", "precio", "km", "combustible"), fila)) for fila in filas]


def medidas_del_dia(anuncios: list[dict]) -> dict:
    """Precio, kilometraje, año y motor de un día, y la mediana de precio por año del modelo."""
    if not anuncios:
        return {"anuncios": 0}
    precios = np.array([a["precio"] for a in anuncios], dtype=float)
    kms = [a["km"] for a in anuncios if a["km"]]
    anios = [a["anio"] for a in anuncios if a["anio"]]
    hibridos = sum(1 for a in anuncios if "brid" in (a["combustible"] or "").lower())
    por_anio = {}
    for anio in sorted(set(anios)):
        del_anio = [a["precio"] for a in anuncios if a["anio"] == anio]
        por_anio[str(anio)] = {"n": len(del_anio), "mediana": float(np.median(del_anio))}
    return {
        "anuncios": len(anuncios),
        "precio_mediana": float(np.median(precios)),
        "precio_q1": float(np.percentile(precios, 25)),
        "precio_q3": float(np.percentile(precios, 75)),
        "km_mediana": float(np.median(kms)) if kms else None,
        "anio_min": min(anios) if anios else None,
        "anio_max": max(anios) if anios else None,
        "hibridos_pct": hibridos / len(anuncios),
        "por_anio": por_anio,
    }


def efectos_precio(anuncios: list[dict]) -> dict:
    """Modelo común, log(precio) = a + b·(año − 2024) + c·log(kilometraje).

    Devuelve cuánto cambia el precio con un año más nuevo y al duplicar el kilometraje.
    Con menos de diez anuncios o un solo año no se estima nada, y con dos años se avisa
    que el efecto por año es poco confiable.
    """
    filas = [a for a in anuncios if a["anio"] and a["km"] and a["km"] > 0]
    anios = {a["anio"] for a in filas}
    if len(filas) < 10 or len(anios) < 2:
        return {"n": len(filas), "por_anio_pct": None, "doble_km_pct": None, "r2": None,
                "nota": "muy pocos anuncios o un solo año del modelo"}
    x = np.column_stack([np.ones(len(filas)), [a["anio"] - ANIO_CENTRO for a in filas],
                         np.log([a["km"] for a in filas])])
    y = np.log([a["precio"] for a in filas])
    coeficientes, *_ = np.linalg.lstsq(x, y, rcond=None)
    ajuste = x @ coeficientes
    r2 = 1 - float(((y - ajuste) ** 2).sum() / ((y - y.mean()) ** 2).sum())
    nota = "solo dos años del modelo, el efecto por año es poco confiable" if len(anios) < 3 else None
    return {"n": len(filas), "por_anio_pct": math.exp(coeficientes[1]) - 1,
            "doble_km_pct": 2 ** coeficientes[2] - 1, "r2": r2, "nota": nota}


def movimiento(rutas: config.Rutas, desde: str, hasta: str) -> dict:
    """Lo que pasó en el periodo común. Anuncios distintos, cambios de precio y anuncios que
    dejaron de aparecer (no prueba que se vendieran, ver la disponibilidad en el README)."""
    distintos = _consultar(rutas.bd, "SELECT COUNT(DISTINCT id_anuncio) FROM observaciones "
                                     "WHERE fecha BETWEEN ? AND ? AND disponibilidad = 'encontrado'",
                           (desde, hasta))
    desaparecidos = _consultar(rutas.bd, "SELECT COUNT(DISTINCT id_anuncio) FROM observaciones "
                                         "WHERE fecha BETWEEN ? AND ? AND disponibilidad = 'no_encontrado'",
                               (desde, hasta))
    bajadas = subidas = 0
    for anterior, nuevo in _consultar(rutas.bd, "SELECT valor_anterior, valor_nuevo FROM cambios "
                                                "WHERE campo = 'precio' AND fecha BETWEEN ? AND ?",
                                      (desde, hasta)):
        try:
            diferencia = float(nuevo) - float(anterior)
        except (TypeError, ValueError):
            continue
        bajadas += diferencia < 0
        subidas += diferencia > 0
    return {"anuncios_distintos": distintos[0][0] if distintos else 0,
            "dejaron_de_aparecer": desaparecidos[0][0] if desaparecidos else 0,
            "bajadas_precio": bajadas, "subidas_precio": subidas}


def gangas(rutas: config.Rutas, fechas: list[str]) -> dict:
    """Posibles gangas que encontró el análisis diario (paso 6) de ese modelo."""
    por_dia, distintas = {}, set()
    for fecha in fechas:
        archivo = rutas.reporte(date.fromisoformat(fecha)) / f"resumen_{fecha}.json"
        if not archivo.exists():
            continue
        alertas = [a for a in json.loads(archivo.read_text(encoding="utf-8")).get("alertas") or []
                   if a.get("clasificacion") == "posible ganga"]
        por_dia[fecha] = len(alertas)
        distintas |= {a.get("id_anuncio") for a in alertas}
    return {"por_dia": por_dia, "distintas": len(distintas)}


def mismo_anio(modelos: list[dict]) -> list[dict]:
    """Cuánto más barato o más caro es cada modelo que el Corolla del mismo año."""
    base = modelos[0].get("por_anio", {})
    filas = []
    for modelo in modelos[1:]:
        for anio, valores in modelo.get("por_anio", {}).items():
            if anio in base:
                filas.append({"modelo": modelo["modelo"], "anio": int(anio),
                              "n_modelo": valores["n"], "n_corolla": base[anio]["n"],
                              "diferencia_pct": valores["mediana"] / base[anio]["mediana"] - 1})
    return filas


def comparar(modo: str = "oficial", fecha: date | None = None, raiz_datos: Path | None = None,
             destino: Path | None = None, con_grafica: bool = True) -> dict:
    """Arma la comparación, la guarda en 'destino' y la devuelve."""
    lista = fuentes(modo, raiz_datos)
    dias = {nombre: dias_con_datos(rutas) for nombre, rutas in lista}
    con_datos = [(nombre, rutas) for nombre, rutas in lista if dias[nombre]]
    if len(con_datos) < 2:
        raise RuntimeError("Hacen falta datos de al menos dos modelos para compararlos.")
    comunes = sorted(set.intersection(*(set(dias[nombre]) for nombre, _ in con_datos)))
    if not comunes:
        raise RuntimeError("Los modelos no tienen ningún día con datos en común.")
    dia = fecha.isoformat() if fecha else comunes[-1]
    periodo = [d for d in comunes if d <= dia]
    modelos = []
    for nombre, rutas in con_datos:
        anuncios = anuncios_del_dia(rutas, dia)
        modelos.append({"modelo": nombre, "primer_dia": dias[nombre][0], "dias_con_datos": len(dias[nombre]),
                        **medidas_del_dia(anuncios), "efectos": efectos_precio(anuncios),
                        **movimiento(rutas, periodo[0], dia), "gangas": gangas(rutas, periodo)})
    resultado = {"dia": dia, "periodo_comun": [periodo[0], dia], "modo": modo,
                 "modelos": modelos, "mismo_anio": mismo_anio(modelos)}
    destino = destino or config.RAIZ_PROYECTO / CARPETA
    guardar(resultado, destino, con_grafica)
    return resultado


def guardar(resultado: dict, destino: Path, con_grafica: bool = True) -> list[Path]:
    destino.mkdir(parents=True, exist_ok=True)
    archivos = [destino / "comparacion_modelos.json", destino / "comparacion_modelos.csv"]
    archivos[0].write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    anios = sorted({anio for m in resultado["modelos"] for anio in m.get("por_anio", {})})
    columnas = ["modelo", "dia", "anuncios", "precio_mediana", "precio_q1", "precio_q3", "km_mediana",
                "anio_min", "anio_max", "hibridos_pct", "por_anio_pct", "doble_km_pct", "r2",
                "anuncios_distintos_periodo", "bajadas_precio", "subidas_precio", "dejaron_de_aparecer",
                "posibles_gangas_distintas"] + [f"mediana_{a}" for a in anios] + [f"n_{a}" for a in anios]
    with open(archivos[1], "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas)
        escritor.writeheader()
        for m in resultado["modelos"]:
            fila = {c: m.get(c) for c in columnas}
            fila.update(dia=resultado["dia"], por_anio_pct=m["efectos"]["por_anio_pct"],
                        doble_km_pct=m["efectos"]["doble_km_pct"], r2=m["efectos"]["r2"],
                        anuncios_distintos_periodo=m["anuncios_distintos"],
                        posibles_gangas_distintas=m["gangas"]["distintas"])
            for anio in anios:
                valores = m.get("por_anio", {}).get(anio)
                fila[f"mediana_{anio}"] = valores["mediana"] if valores else None
                fila[f"n_{anio}"] = valores["n"] if valores else 0
            escritor.writerow(fila)
    if con_grafica:
        from .paso6_grafica import comparacion_por_anio
        archivos.append(comparacion_por_anio(resultado, destino / "comparacion_modelos.png"))
    return archivos


def _cuantos(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def texto(resultado: dict) -> list[str]:
    """Resumen para la terminal y para el documento, en frases cortas."""
    lineas = [f"Comparación del {config.fecha_larga(date.fromisoformat(resultado['dia']))}, "
              f"periodo común del {resultado['periodo_comun'][0]} al {resultado['periodo_comun'][1]}."]
    for m in resultado["modelos"]:
        if not m.get("anuncios"):
            lineas.append(f"* {m['modelo']}. Sin anuncios ese día.")
            continue
        efectos = m["efectos"]
        efecto = (f"Con el mismo kilometraje, cada año más nuevo suma {formato.porcentaje(efectos['por_anio_pct'])} "
                  f"y duplicar el kilometraje resta {formato.porcentaje(-efectos['doble_km_pct'])}"
                  if efectos["por_anio_pct"] is not None else "No alcanza para estimar el modelo de precios")
        if efectos.get("nota"):
            efecto += f" ({efectos['nota']})"
        lineas.append(
            f"* {m['modelo']}. {m['anuncios']} anuncios, modelos {m['anio_min']} a {m['anio_max']}, "
            f"precio mediano {formato.millones(m['precio_mediana'])} (la mitad entre "
            f"{formato.millones(m['precio_q1'], sufijo='')} y {formato.millones(m['precio_q3'])}), "
            f"{formato.kilometros(m['km_mediana'])} de mediana y {formato.porcentaje(m['hibridos_pct'], 0)} híbridos. "
            f"{efecto}. En el periodo hubo {_cuantos(m['bajadas_precio'], 'bajada', 'bajadas')} y "
            f"{_cuantos(m['subidas_precio'], 'subida', 'subidas')} de precio, "
            f"{_cuantos(m['dejaron_de_aparecer'], 'anuncio dejó', 'anuncios dejaron')} de aparecer y "
            f"{_cuantos(m['gangas']['distintas'], 'posible ganga', 'posibles gangas')}.")
    for fila in resultado["mismo_anio"]:
        signo = "más barato" if fila["diferencia_pct"] < 0 else "más caro"
        lineas.append(f"* {fila['modelo']} {fila['anio']} está {formato.porcentaje(abs(fila['diferencia_pct']))} "
                      f"{signo} que el Corolla del mismo año ({fila['n_modelo']} y {fila['n_corolla']} anuncios).")
    return lineas

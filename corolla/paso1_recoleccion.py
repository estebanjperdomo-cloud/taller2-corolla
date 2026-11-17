"""Paso 1 del taller (20 %). Recolectar los enlaces y descargar los datos.

Cada día produce en datos/<modo>/diarios/:
  * enlaces_AAAA-MM-DD.csv     todos los enlaces encontrados, sin repetir
  * datos_AAAA-MM-DD.csv       los datos de cada anuncio (entrada de la consolidación)
  * manifiesto_AAAA-MM-DD.json resumen de la búsqueda: ¿se leyeron todas las páginas?
y en datos/<modo>/crudos/AAAA-MM-DD/ las respuestas originales, sin datos personales.

Estados de descarga (iguales en ambos archivos):
  sin intentar  todavía no se ha intentado; la hora del intento queda vacía
  descargado    la información se extrajo y quedó guardada
  fallido       se intentó pero hubo un error; se guarda el motivo
"""
from __future__ import annotations

import csv
import json
import random
import shutil
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Iterable, Protocol

from . import configuracion as config
from . import paso1_extraccion as extraccion
from .paso1_navegador import ErrorDescarga

SIN_INTENTAR = "sin intentar"
DESCARGADO = "descargado"
FALLIDO = "fallido"
ESTADOS = (SIN_INTENTAR, DESCARGADO, FALLIDO)

COLUMNAS_ENLACES = [
    "id_anuncio", "url", "pagina_busqueda", "fecha_hora_descubrimiento", "es_nuevo",
    "estado_descarga", "fecha_hora_ultimo_intento", "intentos", "motivo_error",
]
COLUMNAS_VEHICULO = [
    "marca", "linea", "anio", "version", "precio", "moneda", "kilometraje", "transmision",
    "ciudad", "sunroof", "sunroof_fuente", "combustible", "color", "cilindraje",
    "estado_vehiculo", "vendido", "estado_publicacion", "fecha_publicacion_carroya",
    "n_accesorios", "accesorios", "cumple_criterios", "motivo_no_cumple",
]
COLUMNAS_DATOS = ["id_anuncio", "url", "estado_descarga", "fecha_hora_descarga", "motivo_error"] + COLUMNAS_VEHICULO
COLUMNAS_NUMERICAS = {"anio", "precio", "kilometraje", "cilindraje", "n_accesorios", "intentos", "pagina_busqueda"}
COLUMNAS_BOOLEANAS = {"sunroof", "cumple_criterios", "es_nuevo"}


class FuenteCarroya(Protocol):
    """Lo que el recolector necesita de una fuente: el navegador real o el simulador."""

    def obtener_busqueda(self, pagina: int) -> dict: ...

    def obtener_detalle(self, url: str, id_anuncio: str) -> dict: ...


# --- Lectura y escritura de CSV (sin pandas, para no alterar los tipos) ------------------
def _a_texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "True" if valor else "False"
    return str(valor)


def escribir_csv(ruta: Path, filas: Iterable[dict], columnas: list[str]) -> None:
    """Escritura atómica: primero a un temporal y luego se reemplaza.

    Si el proceso se cae a mitad de camino, el archivo anterior queda intacto.
    """
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_suffix(ruta.suffix + ".tmp")
    with open(temporal, "w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas, extrasaction="ignore")
        escritor.writeheader()
        for fila in filas:
            escritor.writerow({c: _a_texto(fila.get(c)) for c in columnas})
    temporal.replace(ruta)


def leer_csv(ruta: Path) -> list[dict]:
    """Lee un archivo diario y recupera los tipos: números, booleanos y vacíos."""
    with open(ruta, encoding="utf-8", newline="") as archivo:
        filas = list(csv.DictReader(archivo))
    for fila in filas:
        for clave, valor in fila.items():
            if valor == "" or valor is None:
                fila[clave] = None
            elif clave in COLUMNAS_BOOLEANAS:
                fila[clave] = {"true": True, "false": False}.get(valor.strip().lower())
            elif clave in COLUMNAS_NUMERICAS:
                fila[clave] = extraccion.numero_o_nada(valor)
    return filas


def escribir_json(ruta: Path, contenido) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_suffix(ruta.suffix + ".tmp")
    temporal.write_text(json.dumps(contenido, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    temporal.replace(ruta)


# --- Reintentos ------------------------------------------------------------------------
def con_reintentos(funcion: Callable[[], dict], intentos: int = config.INTENTOS_POR_DESCARGA,
                   espera: tuple[float, float] = config.ESPERA_ENTRE_REINTENTOS_S,
                   registrar: Callable[[str], None] | None = None):
    """Llama funcion() hasta 'intentos' veces. Devuelve (resultado, intentos_usados, ultimo_error)."""
    ultimo_error = None
    for numero in range(1, intentos + 1):
        try:
            return funcion(), numero, None
        except Exception as exc:  # cualquier falla de red, navegador o sitio
            ultimo_error = str(exc) if isinstance(exc, ErrorDescarga) else f"{type(exc).__name__}: {exc}"
            if registrar:
                registrar(f"Intento {numero} de {intentos} falló: {ultimo_error}")
            if numero < intentos:
                time.sleep(random.uniform(*espera) * numero)
    return None, intentos, ultimo_error


# --- Búsqueda: recorrer todas las páginas ------------------------------------------------
@dataclass
class ResultadoBusqueda:
    enlaces: dict = field(default_factory=dict)        # id -> fila del archivo de enlaces
    tarjetas: dict = field(default_factory=dict)       # id -> resumen de la tarjeta
    descartados: list = field(default_factory=list)    # no cumplen marca, línea o año
    total_reportado: int | None = None
    paginas_esperadas: int | None = None
    paginas_ok: list = field(default_factory=list)
    paginas_fallidas: dict = field(default_factory=dict)
    vistos: int = 0
    completa: bool = False
    motivo_incompleta: str | None = None


def buscar_enlaces(fuente: FuenteCarroya, ids_conocidos: set[str],
                   guardar_crudo: Callable[[str, dict], None] | None = None,
                   registrar: Callable[[str], None] = print,
                   max_paginas: int = config.MAX_PAGINAS,
                   espera_reintentos: tuple[float, float] = config.ESPERA_ENTRE_REINTENTOS_S,
                   plantilla_detalle: str = config.URL_DETALLE) -> ResultadoBusqueda:
    """Recorre TODAS las páginas de resultados y junta los enlaces sin repetir."""
    r = ResultadoBusqueda()
    vistos: set[str] = set()

    def procesar(pagina: int) -> None:
        respuesta, _, error = con_reintentos(lambda: fuente.obtener_busqueda(pagina),
                                             espera=espera_reintentos, registrar=registrar)
        if respuesta is None:
            r.paginas_fallidas[pagina] = error
            registrar(f"No se pudo leer la página {pagina}: {error}")
            return
        momento = config.iso(config.ahora())
        if guardar_crudo:
            guardar_crudo(f"busqueda_pagina_{pagina}.json", extraccion.recortar_busqueda(respuesta))
        if r.paginas_esperadas is None:
            r.paginas_esperadas = extraccion.numero_o_nada(respuesta.get("pages"))
            r.total_reportado = extraccion.numero_o_nada(respuesta.get("count"))
        r.paginas_fallidas.pop(pagina, None)
        if pagina not in r.paginas_ok:
            r.paginas_ok.append(pagina)
        nuevos_en_pagina = 0
        for item in extraccion.anuncios_de_busqueda(respuesta):
            tarjeta = extraccion.resumen_tarjeta(item, plantilla_detalle)
            id_anuncio = tarjeta["id_anuncio"]
            if id_anuncio in vistos:
                continue
            vistos.add(id_anuncio)
            nuevos_en_pagina += 1
            cumple, motivo = extraccion.verificar_criterios(tarjeta["marca"], tarjeta["linea"], tarjeta["anio"])
            if not cumple:
                r.descartados.append({"id_anuncio": id_anuncio, "url": tarjeta["url"],
                                      "pagina_busqueda": pagina, "motivo": motivo})
                continue
            r.tarjetas[id_anuncio] = tarjeta
            r.enlaces[id_anuncio] = {
                "id_anuncio": id_anuncio,
                "url": tarjeta["url"],
                "pagina_busqueda": pagina,
                "fecha_hora_descubrimiento": momento,
                "es_nuevo": id_anuncio not in ids_conocidos,
                "estado_descarga": SIN_INTENTAR,
                "fecha_hora_ultimo_intento": None,
                "intentos": 0,
                "motivo_error": None,
            }
        registrar(f"Página {pagina}: {nuevos_en_pagina} anuncios sin repetir "
                  f"(van {len(vistos)} de {r.total_reportado} que reporta Carroya).")

    procesar(1)
    if r.paginas_esperadas is None:
        r.motivo_incompleta = "no se pudo leer la primera página de resultados"
        r.vistos = len(vistos)
        return r

    ultima = min(int(r.paginas_esperadas), max_paginas)
    for pagina in range(2, ultima + 1):
        procesar(pagina)

    # Segunda oportunidad para las páginas que fallaron.
    for pagina in sorted(r.paginas_fallidas):
        registrar(f"Reintentando la página {pagina} al final del recorrido.")
        procesar(pagina)

    # Si se publican o retiran anuncios mientras recorremos, algunos pueden
    # "saltar" de página. Si faltan, se hace una segunda pasada completa.
    if not r.paginas_fallidas and r.total_reportado and len(vistos) < r.total_reportado:
        registrar(f"Cobertura {len(vistos)} de {r.total_reportado}: segunda pasada por las páginas.")
        for pagina in range(1, ultima + 1):
            procesar(pagina)

    r.vistos = len(vistos)
    if r.paginas_fallidas:
        r.motivo_incompleta = f"páginas sin leer: {sorted(r.paginas_fallidas)}"
    elif r.paginas_esperadas > max_paginas:
        r.motivo_incompleta = f"la búsqueda reporta {r.paginas_esperadas} páginas y el tope es {max_paginas}"
    elif r.total_reportado is not None and len(vistos) < r.total_reportado:
        r.motivo_incompleta = f"se vieron {len(vistos)} de {r.total_reportado} anuncios reportados"
    elif not vistos and len(ids_conocidos) >= 10:
        r.motivo_incompleta = "la búsqueda no devolvió anuncios; posible cambio en el sitio"
    else:
        r.completa = True
    return r


# --- Descarga de cada anuncio ------------------------------------------------------------
def fila_datos_vacia(id_anuncio: str, url: str) -> dict:
    fila = {columna: None for columna in COLUMNAS_DATOS}
    fila.update(id_anuncio=id_anuncio, url=url, estado_descarga=SIN_INTENTAR)
    return fila


def descargar_anuncios(fuente: FuenteCarroya, busqueda: ResultadoBusqueda,
                       guardar_progreso: Callable[[dict], None],
                       guardar_crudo: Callable[[str, dict], None] | None = None,
                       registrar: Callable[[str], None] = print,
                       max_anuncios: int | None = None,
                       espera_reintentos: tuple[float, float] = config.ESPERA_ENTRE_REINTENTOS_S) -> dict:
    """Descarga la ficha de cada enlace y extrae sus datos. Devuelve {id: fila de datos}."""
    datos = {i: fila_datos_vacia(i, e["url"]) for i, e in busqueda.enlaces.items()}
    guardar_progreso(datos)
    pendientes = list(busqueda.enlaces)
    if max_anuncios is not None:
        pendientes = pendientes[:max_anuncios]

    for numero, id_anuncio in enumerate(pendientes, start=1):
        enlace, fila = busqueda.enlaces[id_anuncio], datos[id_anuncio]
        respuesta, intentos, error = con_reintentos(
            lambda: fuente.obtener_detalle(enlace["url"], id_anuncio),
            espera=espera_reintentos, registrar=registrar)
        momento = config.iso(config.ahora())
        enlace.update(intentos=intentos, fecha_hora_ultimo_intento=momento)
        fila["fecha_hora_descarga"] = momento
        if respuesta is not None:
            try:
                fila.update(extraccion.campos_detalle(respuesta, id_anuncio, busqueda.tarjetas.get(id_anuncio)))
            except Exception as exc:
                error = f"no se pudieron extraer los datos: {exc}"
            else:
                if guardar_crudo:
                    guardar_crudo(f"detalle_{id_anuncio}.json", extraccion.sanitizar(respuesta))
        estado = FALLIDO if error else DESCARGADO
        for registro in (enlace, fila):
            registro.update(estado_descarga=estado, motivo_error=error)
        if error:
            registrar(f"Anuncio {id_anuncio}: fallido ({error}).")
        if numero % config.GUARDAR_CADA == 0:
            guardar_progreso(datos)
            registrar(f"Descargados {numero} de {len(pendientes)} anuncios.")

    guardar_progreso(datos)
    return datos


def contar_estados(filas: Iterable[dict]) -> dict:
    conteo = {estado: 0 for estado in ESTADOS}
    for fila in filas:
        conteo[fila.get("estado_descarga") or SIN_INTENTAR] += 1
    return conteo


# --- Orquestación del paso 1 --------------------------------------------------------------
def apartar_archivos_previos(rutas: config.Rutas, fecha: date, registrar: Callable[[str], None] = print) -> Path | None:
    """Si el día ya tenía archivos (por ejemplo, se repite una ejecución que falló),
    los mueve a diarios/reemplazados/ en lugar de sobrescribirlos. Así no se pierde
    la evidencia de la ejecución anterior."""
    previos = [r for r in (rutas.enlaces(fecha), rutas.datos(fecha), rutas.manifiesto(fecha)) if r.exists()]
    if not previos:
        return None
    destino = rutas.reemplazados / f"{fecha.isoformat()}_reemplazado_{config.ahora():%H%M%S}"
    destino.mkdir(parents=True, exist_ok=True)
    for ruta in previos:
        shutil.move(str(ruta), destino / ruta.name)
    if rutas.crudos_dia(fecha).exists():
        shutil.move(str(rutas.crudos_dia(fecha)), destino / "crudos")
    registrar(f"El día {fecha.isoformat()} ya tenía archivos; se guardaron en {destino.relative_to(rutas.base)}.")
    return destino


def ejecutar_paso_1(fuente: FuenteCarroya, rutas: config.Rutas, fecha: date, run_id: str,
                    bitacora, ids_conocidos: set[str], estado_dia: dict | None = None,
                    guardar_estado: Callable[[], None] | None = None,
                    max_anuncios: int | None = None,
                    espera_reintentos: tuple[float, float] = config.ESPERA_ENTRE_REINTENTOS_S,
                    plantilla_detalle: str = config.URL_DETALLE) -> dict:
    """Búsqueda + descarga. Devuelve el manifiesto del día (también lo guarda)."""
    rutas.crear()
    apartar_archivos_previos(rutas, fecha, bitacora.info)
    carpeta_crudos = rutas.crudos_dia(fecha)
    carpeta_crudos.mkdir(parents=True, exist_ok=True)

    def guardar_crudo(nombre: str, contenido: dict) -> None:
        (carpeta_crudos / nombre).write_text(json.dumps(contenido, ensure_ascii=False), encoding="utf-8")

    def anotar(etapa_nombre: str, etapa) -> None:
        if estado_dia is not None:
            estado_dia["etapas"][etapa_nombre] = {"estado": etapa.estado or "ok", "fin": config.iso(config.ahora())}
            estado_dia["metricas"].update({k: v for k, v in etapa.metricas.items() if v is not None})
            if guardar_estado:
                guardar_estado()

    busqueda = ResultadoBusqueda(motivo_incompleta="la etapa de búsqueda no terminó")
    with bitacora.etapa("busqueda") as etapa:
        busqueda = buscar_enlaces(fuente, ids_conocidos, guardar_crudo, bitacora.info,
                                  espera_reintentos=espera_reintentos, plantilla_detalle=plantilla_detalle)
        escribir_csv(rutas.enlaces(fecha), busqueda.enlaces.values(), COLUMNAS_ENLACES)
        etapa.metricas.update(
            paginas_esperadas=busqueda.paginas_esperadas,
            paginas_recorridas=len(busqueda.paginas_ok),
            busqueda_completa=busqueda.completa,
            enlaces_encontrados=len(busqueda.enlaces),
            anuncios_nuevos=sum(1 for e in busqueda.enlaces.values() if e["es_nuevo"]),
            total_reportado=busqueda.total_reportado,
            descartados_por_criterios=len(busqueda.descartados),
        )
        for pagina, error in sorted(busqueda.paginas_fallidas.items()):
            etapa.error(f"página {pagina}: {error}")
        if not busqueda.completa:
            etapa.error(f"búsqueda incompleta: {busqueda.motivo_incompleta}")
    errores_busqueda = list(etapa.errores)
    anotar("busqueda", etapa)

    datos: dict = {}
    with bitacora.etapa("descarga") as etapa:
        def guardar_progreso(filas: dict) -> None:
            escribir_csv(rutas.datos(fecha), filas.values(), COLUMNAS_DATOS)
            escribir_csv(rutas.enlaces(fecha), busqueda.enlaces.values(), COLUMNAS_ENLACES)

        datos = descargar_anuncios(fuente, busqueda, guardar_progreso, guardar_crudo, bitacora.info,
                                   max_anuncios=max_anuncios, espera_reintentos=espera_reintentos)
        conteo = contar_estados(datos.values())
        etapa.metricas.update(
            enlaces_encontrados=len(busqueda.enlaces),
            descargas_exitosas=conteo[DESCARGADO],
            descargas_fallidas=conteo[FALLIDO],
            descargas_pendientes=conteo[SIN_INTENTAR],
        )
        if conteo[FALLIDO]:
            etapa.error(f"{conteo[FALLIDO]} descargas fallidas")
        if conteo[SIN_INTENTAR]:
            etapa.error(f"{conteo[SIN_INTENTAR]} anuncios quedaron sin intentar")
    anotar("descarga", etapa)
    if not rutas.datos(fecha).exists():          # por si la etapa falló antes de escribir
        escribir_csv(rutas.datos(fecha), datos.values(), COLUMNAS_DATOS)

    conteo = contar_estados(datos.values())
    manifiesto = {
        "fecha": fecha.isoformat(),
        "run_id": run_id,
        "modo": rutas.modo,
        "generado_en": config.iso(config.ahora()),
        "zona_horaria": config.NOMBRE_ZONA,
        "url_busqueda": config.URL_BUSQUEDA.format(pagina=1),
        "criterios": {"marca": config.MARCA, "linea": config.LINEA,
                      "anio_min": config.ANIO_MIN, "anio_max": config.ANIO_MAX},
        "total_reportado_por_carroya": busqueda.total_reportado,
        "paginas_esperadas": busqueda.paginas_esperadas,
        "paginas_leidas": sorted(busqueda.paginas_ok),
        "paginas_fallidas": {str(k): v for k, v in sorted(busqueda.paginas_fallidas.items())},
        "anuncios_vistos_en_busqueda": busqueda.vistos,
        "enlaces_que_cumplen_criterios": len(busqueda.enlaces),
        "anuncios_nuevos_para_el_sistema": sum(1 for e in busqueda.enlaces.values() if e["es_nuevo"]),
        "descartados_por_criterios": busqueda.descartados,
        "busqueda_completa": busqueda.completa,
        "motivo_busqueda_incompleta": busqueda.motivo_incompleta,
        "errores_busqueda": errores_busqueda,
        "descargas": conteo,
        "archivo_enlaces": rutas.enlaces(fecha).name,
        "archivo_datos": rutas.datos(fecha).name,
    }
    escribir_json(rutas.manifiesto(fecha), manifiesto)
    return manifiesto

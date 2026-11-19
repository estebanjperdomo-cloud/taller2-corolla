"""Archivo de estado de la ejecución diaria (datos/<modo>/estado/ejecucion_AAAA-MM-DD.json).

La recolección lo crea al empezar con estado 'en_curso' y lo actualiza al
terminar cada etapa. El correo de las 11:00 lo lee para saber si el proceso
terminó, sigue en curso o falló, y así decirlo en el reporte.

Además, mientras la recolección corre tiene tomado un candado de archivo
(estado/recoleccion_AAAA-MM-DD.lock). El correo programado lo revisa para no salir
con la recolección a medias cuando el Mac se despierta tarde y launchd lanza las dos
tareas al mismo tiempo.
"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from . import configuracion as config

ETAPAS = ("busqueda", "descarga", "consolidacion", "analisis")
EN_CURSO = "en_curso"
COMPLETADA = "completada"
CON_ADVERTENCIAS = "completada_con_advertencias"
FALLIDA = "fallida"


def leer(rutas: config.Rutas, fecha: date) -> dict | None:
    ruta = rutas.archivo_estado(fecha)
    if not ruta.exists():
        return None
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def guardar(rutas: config.Rutas, fecha: date, estado: dict) -> None:
    ruta = rutas.archivo_estado(fecha)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_suffix(".tmp")
    temporal.write_text(json.dumps(estado, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    temporal.replace(ruta)


def nuevo(fecha: date, run_id: str, modo: str, origen: str = "manual") -> dict:
    return {
        "fecha": fecha.isoformat(),
        "run_id": run_id,
        "modo": modo,
        "estado": EN_CURSO,
        "origen": origen,
        "inicio": config.iso(config.ahora()),
        "fin": None,
        "zona_horaria": config.NOMBRE_ZONA,
        "etapas": {etapa: {"estado": "pendiente", "fin": None} for etapa in ETAPAS},
        "metricas": {},
        "errores": [],
    }


def cerrar(estado: dict) -> dict:
    """Decide el estado general del día a partir de cómo terminó cada etapa."""
    etapas = estado["etapas"]
    errores = estado.get("errores") or []
    metricas = estado.get("metricas") or {}
    sin_datos = not metricas.get("enlaces_encontrados")
    busqueda_fallida = etapas["busqueda"]["estado"] == "error" or (sin_datos and not metricas.get("busqueda_completa"))
    if etapas["consolidacion"]["estado"] == "error" or busqueda_fallida:
        estado["estado"] = FALLIDA
    elif errores or any(e["estado"] != "ok" for e in etapas.values()):
        estado["estado"] = CON_ADVERTENCIAS
    else:
        estado["estado"] = COMPLETADA
    estado["fin"] = config.iso(config.ahora())
    return estado


# --- ¿Hay una recolección corriendo? ---------------------------------------------------------
def _ruta_candado(rutas: config.Rutas, fecha: date) -> Path:
    return rutas.estado / f"recoleccion_{fecha.isoformat()}.lock"


@contextmanager
def candado_recoleccion(rutas: config.Rutas, fecha: date):
    """Se toma mientras corre la recolección del día (Corolla y modelos adicionales).

    Es un candado del sistema operativo (fcntl). Si el proceso se cae o el Mac se apaga,
    el sistema lo suelta solo, así nunca queda pegado. En Windows no hace falta.
    """
    rutas.crear()
    try:
        import fcntl
    except ImportError:
        yield
        return
    with open(_ruta_candado(rutas, fecha), "a") as archivo:
        fcntl.flock(archivo, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(archivo, fcntl.LOCK_UN)


def recoleccion_en_marcha(rutas: config.Rutas, fecha: date) -> bool:
    """True si otro proceso tiene tomado el candado de la recolección de ese día."""
    ruta = _ruta_candado(rutas, fecha)
    if not ruta.exists():
        return False
    try:
        import fcntl
    except ImportError:
        return False
    with open(ruta, "a") as archivo:
        try:
            fcntl.flock(archivo, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        except OSError:
            return False
        fcntl.flock(archivo, fcntl.LOCK_UN)
        return False


def _duracion(segundos: float) -> str:
    return f"{segundos:.0f} segundos" if segundos < 120 else f"{segundos / 60:.0f} minutos"


def esperar_recoleccion(rutas: config.Rutas, fecha: date, max_espera_s: float = 3600,
                        gracia_s: float = 120, intervalo_s: float = 20, registrar=print) -> str:
    """Lo usa el correo programado antes de armar el reporte.

    * Si la recolección del día está corriendo, la espera hasta 'max_espera_s' (una hora).
    * Si todavía no hay rastro de la recolección, espera 'gracia_s' (dos minutos) por si
      está arrancando, porque al despertar el Mac launchd lanza las tareas a la vez.
    Devuelve 'lista', 'sin_recoleccion' o 'sigue_en_curso'. En los tres casos el correo sale.
    """
    inicio = time.monotonic()
    avisado = False
    while True:
        esperado = time.monotonic() - inicio
        if recoleccion_en_marcha(rutas, fecha):
            if esperado >= max_espera_s:
                registrar(f"La recolección sigue corriendo después de {_duracion(esperado)}. "
                          "El correo sale ya con lo que haya.")
                return "sigue_en_curso"
            if not avisado:
                registrar(f"La recolección del día todavía está corriendo. El correo la espera "
                          f"(máximo {max_espera_s / 60:.0f} minutos).")
                avisado = True
        elif leer(rutas, fecha) is not None:
            if avisado:
                registrar(f"La recolección terminó. El correo sale después de esperar {_duracion(esperado)}.")
            return "lista"
        elif esperado >= gracia_s:
            return "sin_recoleccion"
        time.sleep(intervalo_s)

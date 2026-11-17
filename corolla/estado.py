"""Archivo de estado de la ejecución diaria (datos/<modo>/estado/ejecucion_AAAA-MM-DD.json).

La recolección lo crea al empezar con estado 'en_curso' y lo actualiza al
terminar cada etapa. El correo de las 11:00 lo lee para saber si el proceso
terminó, sigue en curso o falló, y así decirlo en el reporte.
"""
from __future__ import annotations

import json
from datetime import date

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

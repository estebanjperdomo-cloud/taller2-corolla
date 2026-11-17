"""Paso 5 del taller (10 %). Logs de cada etapa del workflow.

Cada ejecución (recolección o correo) escribe:
  * datos/<modo>/logs/<run_id>.jsonl  una línea JSON por etapa, con inicio, fin,
    duración, estado, métricas y errores;
  * datos/<modo>/logs/workflow.log     mensajes legibles, línea por línea.

Se usa un archivo JSONL por ejecución para que la recolección y el correo nunca
escriban el mismo archivo a la vez. El log consolidado del periodo se arma al
final con `python taller.py exportar`. Todas las horas van en America/Bogota
con su desfase explícito (-05:00).
"""
from __future__ import annotations

import json
import logging
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from . import configuracion as config

# Columnas fijas del log (mínimos pedidos por el taller y algunas más).
METRICAS = (
    "paginas_esperadas", "paginas_recorridas", "busqueda_completa",
    "enlaces_encontrados", "anuncios_nuevos",
    "descargas_exitosas", "descargas_fallidas", "descargas_pendientes",
    "registros_agregados", "registros_actualizados", "registros_sin_cambios",
    "anuncios_unicos", "tamano_bd_bytes",
    "anuncios_validos_analisis", "posibles_gangas", "posibles_gangas_nuevas",
    "correo_estado",
)
COLUMNAS_LOG = (["run_id", "modo", "tipo_ejecucion", "fecha_reporte", "etapa", "inicio", "fin",
                 "duracion_s", "estado", "zona_horaria"] + list(METRICAS) + ["otros", "errores"])


class _FormatoBogota(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        return config.iso(config.ahora())


@dataclass
class Etapa:
    nombre: str
    metricas: dict = field(default_factory=dict)
    errores: list = field(default_factory=list)
    estado: str | None = None

    def error(self, mensaje) -> None:
        self.errores.append(str(mensaje))


class Bitacora:
    def __init__(self, rutas: config.Rutas, run_id: str, tipo: str, fecha_reporte: date,
                 consola: bool = True):
        rutas.logs.mkdir(parents=True, exist_ok=True)
        self.rutas, self.run_id, self.tipo, self.fecha = rutas, run_id, tipo, fecha_reporte
        self.archivo = rutas.logs / f"{run_id}.jsonl"
        self.registros: list[dict] = []
        self.logger = logging.getLogger(f"corolla.{run_id}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        if not self.logger.handlers:
            formato = _FormatoBogota(f"%(asctime)s | %(levelname)s | {run_id} | %(message)s")
            archivo = logging.FileHandler(rutas.logs / "workflow.log", encoding="utf-8")
            archivo.setFormatter(formato)
            self.logger.addHandler(archivo)
            if consola:
                pantalla = logging.StreamHandler()
                pantalla.setFormatter(formato)
                self.logger.addHandler(pantalla)

    def info(self, mensaje: str) -> None:
        self.logger.info(mensaje)

    def aviso(self, mensaje: str) -> None:
        self.logger.warning(mensaje)

    def cerrar(self) -> None:
        for manejador in list(self.logger.handlers):
            manejador.close()
            self.logger.removeHandler(manejador)

    @contextmanager
    def etapa(self, nombre: str):
        """Mide y registra una etapa. Si algo falla adentro, el error se anota y
        el flujo sigue: el correo debe salir aunque falle parte del proceso."""
        etapa = Etapa(nombre)
        inicio = config.ahora()
        self.info(f"Inicia la etapa '{nombre}'.")
        try:
            yield etapa
        except Exception as exc:
            etapa.error(f"{type(exc).__name__}: {exc}")
            etapa.estado = "error"
            self.logger.error("Error en la etapa '%s'\n%s", nombre, traceback.format_exc())
        finally:
            fin = config.ahora()
            if etapa.estado is None:
                etapa.estado = "con_advertencias" if etapa.errores else "ok"
            registro = {
                "run_id": self.run_id, "modo": self.rutas.modo, "tipo_ejecucion": self.tipo,
                "fecha_reporte": self.fecha.isoformat(), "etapa": nombre,
                "inicio": config.iso(inicio), "fin": config.iso(fin),
                "duracion_s": round((fin - inicio).total_seconds(), 2),
                "estado": etapa.estado, "zona_horaria": config.NOMBRE_ZONA,
            }
            for metrica in METRICAS:
                registro[metrica] = etapa.metricas.get(metrica)
            otros = {k: v for k, v in etapa.metricas.items() if k not in METRICAS}
            registro["otros"] = otros or None
            registro["errores"] = " | ".join(etapa.errores) or None
            self._escribir(registro)
            self.info(f"Termina la etapa '{nombre}' con estado {etapa.estado} "
                      f"en {registro['duracion_s']} s.")

    def _escribir(self, registro: dict) -> None:
        self.registros.append(registro)
        with open(self.archivo, "a", encoding="utf-8") as archivo:
            archivo.write(json.dumps(registro, ensure_ascii=False, default=_serializable) + "\n")


def _serializable(valor):
    if hasattr(valor, "item"):          # números de numpy
        return valor.item()
    return str(valor)


def leer_registros(carpeta_logs: Path, run_id: str | None = None) -> list[dict]:
    archivos = [carpeta_logs / f"{run_id}.jsonl"] if run_id else sorted(carpeta_logs.glob("*.jsonl"))
    registros = []
    for archivo in archivos:
        if archivo.exists():
            for linea in archivo.read_text(encoding="utf-8").splitlines():
                if linea.strip():
                    registros.append(json.loads(linea))
    return sorted(registros, key=lambda r: (r.get("inicio") or "", r.get("run_id") or ""))


def exportar_log_consolidado(carpeta_logs: Path, destino: Path) -> int:
    """Une todos los JSONL del periodo en un CSV y un JSONL. Devuelve las filas."""
    import csv

    registros = leer_registros(carpeta_logs)
    destino.mkdir(parents=True, exist_ok=True)
    with open(destino / "log_consolidado.jsonl", "w", encoding="utf-8") as archivo:
        for registro in registros:
            archivo.write(json.dumps(registro, ensure_ascii=False, default=_serializable) + "\n")
    with open(destino / "log_consolidado.csv", "w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=COLUMNAS_LOG, extrasaction="ignore")
        escritor.writeheader()
        for registro in registros:
            fila = dict(registro)
            if isinstance(fila.get("otros"), dict):
                fila["otros"] = json.dumps(fila["otros"], ensure_ascii=False, default=_serializable)
            escritor.writerow({k: ("" if fila.get(k) is None else fila.get(k)) for k in COLUMNAS_LOG})
    return len(registros)

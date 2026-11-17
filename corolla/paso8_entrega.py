"""Paso 8 del taller (10 %). Exportaciones y archivo comprimido para Bloque Neón.

python taller.py entregar arma entrega_taller2_corolla.zip con

  * el código, las dependencias (requirements.txt) y las instrucciones (README y guía),
  * datos/oficial con los archivos diarios de los seis días, la base consolidada,
    los logs, los reportes y las copias de los correos enviados,
  * datos/prueba con las pruebas, separadas e identificadas como pruebas,
  * datos/launchd con la salida de las tareas programadas del Mac (evidencia del paso 4),
  * entrega/ con la base en CSV y Excel, el log consolidado, las tareas programadas,
    los correos recibidos que ustedes exportan y el documento de una página.

Nunca entran el archivo .env (credenciales), el entorno virtual ni la demostración.
Antes de cerrar el zip se revisa que la contraseña del correo no aparezca en ningún archivo.
"""
from __future__ import annotations

import os
import shutil
import zipfile
from datetime import timedelta
from pathlib import Path

from . import configuracion as config
from .paso2_base_de_datos import exportar
from .paso5_bitacora import exportar_log_consolidado

EXCLUIR = {".env", ".venv", "__pycache__", ".pytest_cache", ".git", ".DS_Store", "demo"}
CARPETA_ENTREGA = "entrega"
NOMBRE_ZIP = "entrega_taller2_corolla.zip"


def exportar_todo(rutas: config.Rutas, destino: Path | None = None) -> list[Path]:
    """Tablas de la base en CSV y Excel, y el log consolidado del periodo."""
    destino = destino or config.RAIZ_PROYECTO / CARPETA_ENTREGA
    archivos = []
    if rutas.bd.exists():
        archivos += exportar(rutas.bd, destino / "base_consolidada")
    exportar_log_consolidado(rutas.logs, destino / "logs")
    archivos += [destino / "logs" / "log_consolidado.csv", destino / "logs" / "log_consolidado.jsonl"]
    return archivos


def copiar_tareas_programadas(destino: Path) -> list[Path]:
    """Copia los .plist de launchd del paso 4, para mostrar cómo quedó programado."""
    from .paso4_programacion import TAREAS, ruta_plist

    copiados = []
    for tarea in TAREAS:
        origen = ruta_plist(tarea)
        if origen.exists():
            destino.mkdir(parents=True, exist_ok=True)
            copiados.append(Path(shutil.copy2(origen, destino / origen.name)))
    return copiados


def revisar(raiz: Path = config.RAIZ_PROYECTO) -> list[str]:
    """Lista de lo que falta para que la entrega esté completa (vacía si todo está)."""
    rutas = config.Rutas("oficial", raiz / "datos")
    faltantes = []
    dia = config.PERIODO_INICIO
    while dia <= config.PERIODO_FIN:
        for archivo in (rutas.enlaces(dia), rutas.datos(dia)):
            if not archivo.exists():
                faltantes.append(f"falta {archivo.relative_to(raiz)}")
        dia += timedelta(days=1)
    if not rutas.bd.exists():
        faltantes.append("falta la base consolidada oficial")
    recibidos = raiz / CARPETA_ENTREGA / "correos_recibidos"
    n_correos = len([a for a in recibidos.glob("*") if a.is_file() and not a.name.startswith(".")]) \
        if recibidos.exists() else 0
    if n_correos < 6:
        faltantes.append(f"en {CARPETA_ENTREGA}/correos_recibidos hay {n_correos} correos exportados y se piden 6")
    if not list((raiz / CARPETA_ENTREGA).glob("documento_una_pagina*.pdf")):
        faltantes.append(f"falta {CARPETA_ENTREGA}/documento_una_pagina.pdf")
    return faltantes


def _archivos_del_zip(raiz: Path, destino: Path) -> list[Path]:
    archivos = []
    for ruta in sorted(raiz.rglob("*")):
        relativa = ruta.relative_to(raiz)
        if ruta.is_dir() or set(relativa.parts) & EXCLUIR or ruta.suffix in (".zip", ".tmp") or ruta == destino:
            continue
        archivos.append(ruta)
    return archivos


def _revisar_credenciales(archivos: list[Path]) -> None:
    """Detiene la entrega si la contraseña del correo aparece escrita en algún archivo."""
    clave = (os.environ.get("SMTP_PASSWORD") or "").replace(" ", "")
    if len(clave) < 8:
        return
    for ruta in archivos:
        if ruta.stat().st_size > 20_000_000:
            continue
        try:
            contenido = ruta.read_bytes()
        except OSError:
            continue
        if clave.encode() in contenido:
            raise RuntimeError(f"La contraseña del correo aparece en {ruta}. Bórrela de ese archivo y repita.")


def empaquetar(raiz: Path = config.RAIZ_PROYECTO, destino: Path | None = None) -> tuple[Path, list[str]]:
    """Arma el zip de la entrega. Devuelve la ruta del zip y lo que todavía falta."""
    rutas = config.Rutas("oficial", raiz / "datos")
    exportar_todo(rutas, raiz / CARPETA_ENTREGA)
    copiar_tareas_programadas(raiz / CARPETA_ENTREGA / "programacion")
    (raiz / CARPETA_ENTREGA / "correos_recibidos").mkdir(parents=True, exist_ok=True)
    destino = destino or raiz / NOMBRE_ZIP
    archivos = _archivos_del_zip(raiz, destino)
    _revisar_credenciales(archivos)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zip_:
        for ruta in archivos:
            zip_.write(ruta, (Path(raiz.name) / ruta.relative_to(raiz)).as_posix())
    return destino, revisar(raiz)

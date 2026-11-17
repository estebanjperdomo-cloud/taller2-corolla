"""python taller.py verificar revisa que todo esté listo y dice qué falta y cómo arreglarlo."""
from __future__ import annotations

import importlib
import os
import socket
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from . import configuracion as config

OK, FALTA, AVISO = "OK", "FALTA", "AVISO"
CARPETAS_PROTEGIDAS = ("/Documents/", "/Desktop/", "/Downloads/", "/Mobile Documents/", "/Library/CloudStorage/")
LIBRERIAS = ("playwright", "pandas", "numpy", "matplotlib", "jinja2", "openpyxl", "dotenv")
VALORES_DE_EJEMPLO = ("cuenta_que_envia@gmail.com", "xxxxxxxxxxxxxxxx", "correo_de_esteban@gmail.com",
                      "correo_del_companero@gmail.com")


def _python() -> tuple[str, str, str]:
    version = ".".join(map(str, sys.version_info[:3]))
    if sys.version_info < (3, 10):
        return FALTA, f"Python {version}", "Instale Python 3.12 (brew install python@3.12) y cree de nuevo el .venv"
    return OK, f"Python {version}", ""


def _entorno() -> tuple[str, str, str]:
    if sys.prefix != sys.base_prefix:
        return OK, f"entorno virtual activo ({sys.prefix})", ""
    return AVISO, "el entorno virtual no está activo", "Ejecute: source .venv/bin/activate"


def _librerias() -> tuple[str, str, str]:
    faltan = []
    for nombre in LIBRERIAS:
        try:
            importlib.import_module(nombre)
        except ImportError:
            faltan.append(nombre)
    if faltan:
        return FALTA, f"faltan librerías: {', '.join(faltan)}", "Ejecute: pip install -r requirements.txt"
    return OK, "librerías instaladas", ""


def _chromium() -> tuple[str, str, str]:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            navegador = p.chromium.launch()
            navegador.close()
        return OK, "Chromium de Playwright abre bien", ""
    except Exception as exc:
        return FALTA, f"Chromium no abre ({str(exc).splitlines()[0][:120]})", \
            "Ejecute: python -m playwright install chromium"


def _env(raiz: Path) -> tuple[str, str, str]:
    if not (raiz / ".env").exists():
        return FALTA, "no existe el archivo .env", "Ejecute: cp .env.example .env y llénelo (guía, parte 1.6)"
    faltan = [v for v in ("SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO")
              if not os.environ.get(v) or any(e in os.environ.get(v, "") for e in VALORES_DE_EJEMPLO)]
    if faltan:
        return FALTA, f"en .env faltan o siguen de ejemplo: {', '.join(faltan)}", "Abra el .env con: open -e .env"
    return OK, f".env completo (envía {os.environ['SMTP_USER']} a {os.environ['EMAIL_TO']})", ""


def _carpeta(raiz: Path) -> tuple[str, str, str]:
    texto = str(raiz) + "/"
    if any(p in texto for p in CARPETAS_PROTEGIDAS):
        return FALTA, f"el proyecto está en {raiz}", \
            "Muévalo a su carpeta personal, por ejemplo: mv \"" + str(raiz) + "\" ~/taller2-corolla"
    return OK, f"carpeta del proyecto {raiz}", ""


def _zona_horaria() -> tuple[str, str, str]:
    desfase = config.ahora().astimezone().utcoffset()  # zona del sistema
    if desfase == timedelta(hours=-5):
        return OK, "el reloj del sistema está en hora de Colombia (UTC-5)", ""
    return AVISO, f"el reloj del sistema está en UTC{desfase}", \
        "No es grave. 'programar' convierte las 8:00 y 11:00 de Bogotá a la hora del Mac"


def _internet() -> tuple[str, str, str]:
    try:
        with socket.create_connection(("www.carroya.com", 443), timeout=8):
            return OK, "hay conexión con www.carroya.com", ""
    except OSError as exc:
        return AVISO, f"sin conexión con www.carroya.com ({exc})", "Revise el wifi"


def _mac() -> list[tuple[str, str, str]]:
    from .paso4_programacion import TAREAS, etiqueta

    filas = []
    uid = os.getuid()
    for tarea in TAREAS:
        cargada = subprocess.run(["launchctl", "print", f"gui/{uid}/{etiqueta(tarea)}"],
                                 capture_output=True, text=True).returncode == 0
        filas.append((OK, f"tarea {etiqueta(tarea)} programada", "") if cargada else
                     (AVISO, f"la tarea {tarea} todavía no está programada", "Ejecute: python taller.py programar"))
    programado = subprocess.run(["pmset", "-g", "sched"], capture_output=True, text=True).stdout.lower()
    filas.append((OK, "el Mac tiene un despertar programado (pmset)", "") if "wake" in programado else
                 (AVISO, "el Mac no tiene un despertar programado",
                  "Ejecute: sudo pmset repeat wakeorpoweron MTWRFSU 07:55:00"))
    ajustes = subprocess.run(["pmset", "-g", "custom"], capture_output=True, text=True).stdout
    reposo = None
    seccion = None
    for linea in ajustes.splitlines():
        if linea.strip().endswith("Power:"):
            seccion = linea.strip()
        partes = linea.split()
        if seccion == "AC Power:" and len(partes) >= 2 and partes[0] == "sleep":
            reposo = partes[1]
    filas.append((OK, "con el cargador el Mac no entra en reposo (sleep 0)", "") if reposo == "0" else
                 (AVISO, f"con el cargador el Mac se duerme a los {reposo} min" if reposo else
                  "no se pudo leer el ajuste de reposo",
                  "Ejecute: sudo pmset -c sleep 0  (o en Ajustes del Sistema, Batería, Opciones, active la opción "
                  "que evita el reposo automático con el adaptador de corriente)"))
    return filas


def verificar(raiz: Path = config.RAIZ_PROYECTO, red: bool = True, navegador: bool = True) -> list[tuple[str, str, str]]:
    filas = [_python(), _entorno(), _librerias()]
    if navegador:
        filas.append(_chromium())
    filas += [_env(raiz), _carpeta(raiz), _zona_horaria()]
    if red:
        filas.append(_internet())
    if sys.platform == "darwin":
        filas += _mac()
    return filas


def resumen_periodo() -> str:
    hoy = config.hoy()
    modo = config.modo_programado(hoy)
    if hoy < config.PERIODO_INICIO:
        faltan = (config.PERIODO_INICIO - hoy).days
        return (f"Hoy es {config.fecha_larga(hoy)}. Faltan {faltan} día(s) para el periodo oficial. "
                f"Las ejecuciones programadas de hoy corren en modo {modo}.")
    if modo == "oficial":
        return f"Hoy es {config.fecha_larga(hoy)}, día {(hoy - config.PERIODO_INICIO).days + 1} de 6 del periodo oficial."
    return f"Hoy es {config.fecha_larga(hoy)}. El periodo oficial terminó; ya puede correr 'python taller.py desprogramar'."

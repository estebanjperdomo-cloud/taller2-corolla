"""Paso 4 del taller (10 %). Ejecución automática diaria en el Mac con launchd.

macOS trae launchd, el programador de tareas del propio sistema (cumple el papel de
cron). Este módulo crea dos tareas independientes en ~/Library/LaunchAgents

  co.uniandes.taller2corolla.recoleccion   todos los días a las 8:00 (pasos 1, 3 y 6)
  co.uniandes.taller2corolla.correo        todos los días a las 11:00 (paso 7)

Cada tarea ejecuta, con rutas absolutas,
  /usr/bin/caffeinate -i -s  .venv/bin/python  taller.py  recolectar|correo  --programado

caffeinate impide que el Mac se duerma mientras la tarea corre. Con --programado el
programa decide el modo por la fecha. Antes del 16 de noviembre es una prueba, del 16
al 21 es oficial y después del 21 no hace nada (ver configuracion.modo_programado).

Condiciones para que funcione (también están en la guía)
  * el Mac encendido, conectado a la corriente y con la sesión de usuario iniciada
    (puede tener la pantalla bloqueada, pero no apagado ni con la sesión cerrada),
  * que no se duerma a esas horas, o que se despierte solo antes (pmset),
  * conexión a internet,
  * la carpeta del proyecto fuera de Documentos, Escritorio y Descargas, porque macOS
    no deja que las tareas programadas lean esas carpetas.
Si a las 8:00 el Mac estaba dormido, launchd corre la tarea apenas el Mac se despierte.
"""
from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from . import configuracion as config

PREFIJO = "co.uniandes.taller2corolla"
# tarea -> (comando de taller.py, hora de Bogotá)
TAREAS = {
    "recoleccion": ("recolectar", config.HORA_RECOLECCION),
    "correo": ("correo", config.HORA_CORREO),
}


def etiqueta(tarea: str) -> str:
    return f"{PREFIJO}.{tarea}"


def ruta_plist(tarea: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{etiqueta(tarea)}.plist"


def carpeta_salidas(raiz: Path = config.RAIZ_PROYECTO) -> Path:
    """Donde launchd escribe lo que cada tarea imprime (evidencia de las ejecuciones programadas)."""
    return raiz / "datos" / "launchd"


def python_del_proyecto(raiz: Path = config.RAIZ_PROYECTO) -> Path:
    """El Python del entorno virtual. No se resuelve el enlace simbólico a propósito,
    porque el enlace es el que hace que se usen las librerías del .venv."""
    candidato = raiz / ".venv" / "bin" / "python"
    return candidato if candidato.exists() else Path(sys.executable)


def hora_local(tarea: str) -> tuple[int, int]:
    """launchd usa la hora del Mac. Si el Mac no está en hora de Bogotá, se convierte."""
    hora = TAREAS[tarea][1]
    en_bogota = datetime.combine(config.PERIODO_INICIO, hora, tzinfo=config.ZONA_HORARIA)
    local = en_bogota.astimezone()  # zona horaria del sistema
    return local.hour, local.minute


def contenido_plist(tarea: str, raiz: Path = config.RAIZ_PROYECTO, python: Path | None = None) -> dict:
    comando = TAREAS[tarea][0]
    hora, minuto = hora_local(tarea)
    salida = carpeta_salidas(raiz) / f"{tarea}.log"
    return {
        "Label": etiqueta(tarea),
        "ProgramArguments": ["/usr/bin/caffeinate", "-i", "-s", str(python or python_del_proyecto(raiz)),
                             str(raiz / "taller.py"), comando, "--programado"],
        "WorkingDirectory": str(raiz),
        "StartCalendarInterval": {"Hour": hora, "Minute": minuto},
        "StandardOutPath": str(salida),
        "StandardErrorPath": str(salida),
        "EnvironmentVariables": {
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
        },
        "RunAtLoad": False,
    }


def _launchctl(*argumentos: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *argumentos], capture_output=True, text=True)


def _dominio() -> str:
    """Las tareas del usuario que tiene la sesión abierta viven en el dominio gui/<uid>."""
    return f"gui/{os.getuid() if hasattr(os, 'getuid') else 0}"


def _exigir_mac() -> None:
    if sys.platform != "darwin":
        raise RuntimeError("La programación con launchd solo funciona en macOS. Este computador es "
                           f"'{sys.platform}'. La ejecución diaria se hace en el Mac de la pareja.")


def instalar(raiz: Path = config.RAIZ_PROYECTO, registrar=print) -> list[Path]:
    """Crea (o reemplaza) las dos tareas y las carga en launchd."""
    _exigir_mac()
    carpeta_salidas(raiz).mkdir(parents=True, exist_ok=True)
    creados = []
    for tarea in TAREAS:
        ruta = ruta_plist(tarea)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        _launchctl("bootout", f"{_dominio()}/{etiqueta(tarea)}")  # si ya existía, se descarga primero
        with open(ruta, "wb") as archivo:
            plistlib.dump(contenido_plist(tarea, raiz), archivo)
        resultado = _launchctl("bootstrap", _dominio(), str(ruta))
        if resultado.returncode != 0:
            raise RuntimeError(f"launchctl no pudo cargar {ruta.name}: {(resultado.stderr or resultado.stdout).strip()}")
        hora, minuto = hora_local(tarea)
        registrar(f"Tarea {etiqueta(tarea)} cargada. Corre todos los días a las {hora:02d}:{minuto:02d} "
                  f"(hora del Mac) el comando '{TAREAS[tarea][0]} --programado'.")
        creados.append(ruta)
    return creados


def desinstalar(registrar=print) -> None:
    """Descarga las tareas de launchd y borra sus archivos .plist."""
    _exigir_mac()
    for tarea in TAREAS:
        _launchctl("bootout", f"{_dominio()}/{etiqueta(tarea)}")
        ruta = ruta_plist(tarea)
        if ruta.exists():
            ruta.unlink()
        registrar(f"Tarea {etiqueta(tarea)} quitada.")


def _leer_campo(texto: str, campo: str) -> str | None:
    for linea in texto.splitlines():
        linea = linea.strip()
        if linea.startswith(campo + " = "):
            return linea.split(" = ", 1)[1].strip()
    return None


def estado(raiz: Path = config.RAIZ_PROYECTO) -> list[dict]:
    """Para cada tarea, si está cargada, cuántas veces ha corrido y cómo terminó la última vez."""
    _exigir_mac()
    filas = []
    for tarea in TAREAS:
        info = _launchctl("print", f"{_dominio()}/{etiqueta(tarea)}")
        cargada = info.returncode == 0
        salida = carpeta_salidas(raiz) / f"{tarea}.log"
        ultimas = salida.read_text(encoding="utf-8", errors="replace").splitlines()[-8:] if salida.exists() else []
        filas.append({
            "tarea": etiqueta(tarea),
            "plist": str(ruta_plist(tarea)) if ruta_plist(tarea).exists() else None,
            "cargada": cargada,
            "estado": _leer_campo(info.stdout, "state") if cargada else None,
            "veces_ejecutada": _leer_campo(info.stdout, "runs") if cargada else None,
            "ultimo_codigo_salida": _leer_campo(info.stdout, "last exit code") if cargada else None,
            "hora_local": "%02d:%02d" % hora_local(tarea),
            "archivo_salida": str(salida),
            "ultimas_lineas": ultimas,
        })
    return filas


def probar(tarea: str, registrar=print) -> None:
    """Pide a launchd que corra la tarea ya mismo, igual que lo haría a su hora."""
    _exigir_mac()
    resultado = _launchctl("kickstart", f"{_dominio()}/{etiqueta(tarea)}")
    if resultado.returncode != 0:
        raise RuntimeError(f"No se pudo lanzar {etiqueta(tarea)}: {(resultado.stderr or resultado.stdout).strip()}. "
                           "¿Ya corrió 'python taller.py programar'?")
    registrar(f"Tarea {etiqueta(tarea)} lanzada. Lo que imprime queda en {carpeta_salidas() / (tarea + '.log')}")


def proximas_ejecuciones(desde: datetime | None = None, cantidad: int = 4) -> list[str]:
    """Texto con las próximas ejecuciones y el modo que tendrá cada una."""
    desde = desde or config.ahora()
    eventos = []
    dia = desde.date()
    while len(eventos) < cantidad and dia <= config.PERIODO_FIN + timedelta(days=1):
        for tarea, (comando, hora) in TAREAS.items():
            momento = datetime.combine(dia, hora, tzinfo=config.ZONA_HORARIA)
            if momento > desde:
                modo = config.modo_programado(dia)
                que = f"modo {modo}" if modo else "no hace nada (fuera del periodo)"
                eventos.append(f"{config.fecha_larga(dia)} a las {hora:%H:%M}, {comando} en {que}")
        dia += timedelta(days=1)
    return eventos[:cantidad]

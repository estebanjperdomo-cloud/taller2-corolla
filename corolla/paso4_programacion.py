"""Paso 4 del taller (10 %). Ejecución automática diaria en el Mac con launchd.

macOS trae launchd, el programador de tareas del propio sistema (cumple el papel de
cron). Este módulo crea tres tareas independientes en ~/Library/LaunchAgents

  co.uniandes.taller2corolla.recoleccion   todos los días a las 8:00 (pasos 1, 3 y 6)
  co.uniandes.taller2corolla.correo        todos los días a las 11:00 (paso 7)
  co.uniandes.taller2corolla.reintento     cada 30 minutos de 11:30 a 23:30. Envía el correo
                                           del día solo si todavía no ha salido (por ejemplo,
                                           si a las 11:00 la red bloqueó el envío o el Mac
                                           estaba dormido)

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
Por eso el correo programado
  * espera a que termine la recolección si la encuentra corriendo (máximo una hora),
  * no se repite si el correo de ese día ya salió,
  * y si arranca antes de las 11:00 es una tarea que el Mac se perdió ayer, así que envía
    el correo de ayer (solo si no había salido) y no el de hoy.
"""
from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from datetime import datetime, time, timedelta
from pathlib import Path

from . import configuracion as config

PREFIJO = "co.uniandes.taller2corolla"
# Reintentos del correo: cada 30 minutos de 11:30 a 23:30 (solo envían si falta el del día)
HORAS_REINTENTO = tuple(time(h, m) for h in range(11, 24) for m in (0, 30) if time(h, m) >= time(11, 30))
# tarea -> (comando de taller.py, horas de Bogotá)
TAREAS = {
    "recoleccion": ("recolectar", (config.HORA_RECOLECCION,)),
    "correo": ("correo", (config.HORA_CORREO,)),
    "reintento": ("correo", HORAS_REINTENTO),
}
PRINCIPALES = ("recoleccion", "correo")


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


def horas_locales(tarea: str) -> list[tuple[int, int]]:
    """launchd usa la hora del Mac. Si el Mac no está en hora de Bogotá, se convierte."""
    salida = []
    for hora in TAREAS[tarea][1]:
        en_bogota = datetime.combine(config.PERIODO_INICIO, hora, tzinfo=config.ZONA_HORARIA)
        local = en_bogota.astimezone()  # zona horaria del sistema
        salida.append((local.hour, local.minute))
    return salida


def hora_local(tarea: str) -> tuple[int, int]:
    """La primera hora de la tarea en la hora del Mac."""
    return horas_locales(tarea)[0]


def describir_horas(tarea: str) -> str:
    horas = horas_locales(tarea)
    if len(horas) == 1:
        return "%02d:%02d" % horas[0]
    return "cada 30 min de %02d:%02d a %02d:%02d" % (horas[0] + horas[-1])


def contenido_plist(tarea: str, raiz: Path = config.RAIZ_PROYECTO, python: Path | None = None) -> dict:
    comando = TAREAS[tarea][0]
    horas = [{"Hour": h, "Minute": m} for h, m in horas_locales(tarea)]
    salida = carpeta_salidas(raiz) / f"{tarea}.log"
    return {
        "Label": etiqueta(tarea),
        "ProgramArguments": ["/usr/bin/caffeinate", "-i", "-s", str(python or python_del_proyecto(raiz)),
                             str(raiz / "taller.py"), comando, "--programado"],
        "WorkingDirectory": str(raiz),
        "StartCalendarInterval": horas[0] if len(horas) == 1 else horas,
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
    """Crea (o reemplaza) las tres tareas y las carga en launchd."""
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
        registrar(f"Tarea {etiqueta(tarea)} cargada. Corre todos los días ({describir_horas(tarea)}, hora del Mac) "
                  f"el comando '{TAREAS[tarea][0]} --programado'.")
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
            "hora_local": describir_horas(tarea),
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
        for tarea in PRINCIPALES:
            comando, hora = TAREAS[tarea][0], TAREAS[tarea][1][0]
            momento = datetime.combine(dia, hora, tzinfo=config.ZONA_HORARIA)
            if momento > desde:
                modo = config.modo_programado(dia)
                que = f"modo {modo}" if modo else "no hace nada (fuera del periodo)"
                eventos.append(f"{config.fecha_larga(dia)} a las {hora:%H:%M}, {comando} en {que}")
        dia += timedelta(days=1)
    return eventos[:cantidad]

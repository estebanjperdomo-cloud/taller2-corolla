"""Avisos en la pantalla del Mac (notificaciones del sistema). En otros sistemas no hace nada.

Los usan las tareas programadas para avisar cuándo empieza y termina la recolección
(para no cerrar la tapa a mitad de camino) y si el correo del día no se pudo enviar.
"""
from __future__ import annotations

import subprocess
import sys


def notificar(titulo: str, texto: str) -> None:
    if sys.platform != "darwin":
        return

    def comillas(valor: str) -> str:
        return valor.replace("\\", "\\\\").replace('"', '\\"')

    orden = f'display notification "{comillas(texto)}" with title "{comillas(titulo)}" sound name "Glass"'
    try:
        subprocess.run(["osascript", "-e", orden], capture_output=True, timeout=15)
    except Exception:
        pass  # un aviso que no sale nunca debe interrumpir el trabajo

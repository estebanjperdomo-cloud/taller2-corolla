"""Formato de números al estilo colombiano: $116.900.000, 14,7 %, 35.000 km."""
from __future__ import annotations

import math


def _nulo(valor) -> bool:
    try:
        return valor is None or (isinstance(valor, float) and math.isnan(valor))
    except TypeError:
        return False


def miles(numero) -> str:
    if _nulo(numero):
        return "sin dato"
    return f"{int(round(float(numero))):,}".replace(",", ".")


def pesos(numero) -> str:
    return "sin dato" if _nulo(numero) else f"${miles(numero)}"


def decimal(numero, decimales: int = 1) -> str:
    if _nulo(numero):
        return "sin dato"
    texto = f"{float(numero):,.{decimales}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


def millones(numero, decimales: int = 1, sufijo: str = " millones") -> str:
    return "sin dato" if _nulo(numero) else f"${decimal(float(numero) / 1e6, decimales)}{sufijo}"


def porcentaje(fraccion, decimales: int = 1) -> str:
    return "sin dato" if _nulo(fraccion) else f"{decimal(float(fraccion) * 100, decimales)} %"


def kilometros(numero) -> str:
    return "sin dato" if _nulo(numero) else f"{miles(numero)} km"


def bytes_legibles(numero) -> str:
    if _nulo(numero):
        return "sin dato"
    numero = float(numero)
    for unidad in ("B", "KB", "MB", "GB"):
        if numero < 1024 or unidad == "GB":
            return f"{decimal(numero, 0 if unidad == 'B' else 1)} {unidad}"
        numero /= 1024
    return f"{numero} B"

"""Paso 1 del taller. Convierte las respuestas JSON de Carroya en filas limpias.

Son funciones puras: reciben diccionarios y devuelven diccionarios, sin
conectarse a internet. Por eso se pueden probar sin conexión (ver tests/).

Regla de oro del taller: si un dato no aparece, queda vacío (None). Nunca se
inventa ni se convierte en cero.
"""
from __future__ import annotations

import math
import re
import unicodedata
from typing import Any

from . import configuracion as config

VACIOS = {"", "null", "none", "undefined", "nan", "n/a", "na", "-"}


# --- Utilidades de texto y números ---------------------------------------------
def sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def normalizar(texto: Any) -> str:
    """Minúsculas, sin tildes y con espacios simples. Útil para comparar."""
    if texto is None:
        return ""
    return re.sub(r"\s+", " ", sin_tildes(str(texto)).lower()).strip()


def slug(texto: Any) -> str:
    """'MEDELLÍN' -> 'medellin'. Así arma Carroya las direcciones de las fichas."""
    return re.sub(r"[^a-z0-9]+", "-", normalizar(texto)).strip("-")


def texto_o_nada(valor: Any) -> str | None:
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, float) and math.isnan(valor):
        return None
    texto = re.sub(r"\s+", " ", str(valor)).strip()
    return None if texto.lower() in VACIOS else texto


def numero_o_nada(valor: Any) -> int | float | None:
    """Convierte a número sin inventar: lo que no es número queda en None."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float):
        if math.isnan(valor):
            return None
        return int(valor) if valor.is_integer() else valor
    texto = texto_o_nada(valor)
    if texto is None:
        return None
    texto = texto.replace("$", "").replace(" ", "")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", texto):        # 116.900.000
        texto = texto.replace(".", "")
    elif re.fullmatch(r"\d+,\d+", texto):                 # 1,8
        texto = texto.replace(",", ".")
    else:
        texto = texto.replace(",", "")
    try:
        numero = float(texto)
    except ValueError:
        return None
    return int(numero) if numero.is_integer() else numero


def moneda_normalizada(valor: Any) -> str | None:
    texto = texto_o_nada(valor)
    if texto is None:
        return None
    clave = normalizar(texto)
    if clave in {"peso", "pesos", "cop", "$", "peso colombiano"}:
        return "COP"
    if clave in {"dolar", "dolares", "usd", "us$"}:
        return "USD"
    return texto.upper()


# --- Resultado de búsqueda ------------------------------------------------------
def _parece_anuncio(objeto: Any) -> bool:
    return (isinstance(objeto, dict) and objeto.get("id")
            and ("price" in objeto or "cprecioint" in objeto)
            and ("brand" in objeto or "cidmarca" in objeto))


def anuncios_de_busqueda(respuesta: dict) -> list[dict]:
    """Saca los anuncios de una página de resultados, sin repetirlos.

    La API devuelve en 'results' varias listas: los filtros de la columna
    izquierda y los anuncios (hoy en 'superHighlights'; a veces también en
    'megaHighlights' o 'latestReleases'). Para no depender del nombre exacto,
    se toma cualquier lista cuyos elementos tengan forma de anuncio.
    """
    resultados = (respuesta or {}).get("results") or {}
    vistos, salida = set(), []
    for valor in resultados.values():
        if not isinstance(valor, list):
            continue
        for item in valor:
            if _parece_anuncio(item) and str(item["id"]) not in vistos:
                vistos.add(str(item["id"]))
                salida.append(item)
    return salida


def url_detalle(item: dict, plantilla: str = config.URL_DETALLE) -> str:
    """Dirección pública de la ficha, igual a la que usa Carroya en sus tarjetas."""
    anio = numero_o_nada(item.get("year")) or numero_o_nada(item.get("cmodeloint")) or 0
    return plantilla.format(
        estado=slug(item.get("status")) or "usado",
        marca=slug(item.get("brand")) or "toyota",
        linea=slug(item.get("model")) or "corolla",
        anio=anio,
        ciudad=slug(item.get("city")) or "colombia",
        id=str(item["id"]).strip(),
    )


def resumen_tarjeta(item: dict, plantilla_detalle: str = config.URL_DETALLE) -> dict:
    """Lo poco que se necesita de la tarjeta del resultado de búsqueda."""
    anio = item.get("year") if item.get("year") is not None else item.get("cmodeloint")
    return {
        "id_anuncio": str(item["id"]).strip(),
        "url": url_detalle(item, plantilla_detalle),
        "marca": texto_o_nada(item.get("brand")),
        "linea": texto_o_nada(item.get("model")),
        "anio": numero_o_nada(anio),
        # La moneda solo viene en la tarjeta de búsqueda (la ficha no la trae).
        "moneda": moneda_normalizada(item.get("ctipomoneda")),
        "precio_tarjeta": numero_o_nada(item.get("price")),
    }


def verificar_criterios(marca: Any, linea: Any, anio: Any) -> tuple[bool, str | None]:
    """¿El anuncio es un Toyota Corolla modelo 2022 a 2026?"""
    if normalizar(marca) != normalizar(config.MARCA):
        return False, f"marca distinta ({marca})"
    if normalizar(linea) != normalizar(config.LINEA):
        return False, f"línea distinta ({linea})"
    anio = numero_o_nada(anio)
    if anio is None:
        return False, "sin año del modelo"
    if not config.ANIO_MIN <= anio <= config.ANIO_MAX:
        return False, f"año fuera de rango ({anio})"
    return True, None


# --- Ficha del anuncio ----------------------------------------------------------
PATRON_SUNROOF = re.compile(
    r"sun\s*-?\s*roof|moon\s*roof|quemacocos|techo\s+(corredizo|solar|panoramico|electrico)",
    re.IGNORECASE,
)


def detectar_sunroof(accesorios: list[str], *otros_textos: tuple[str, Any]) -> tuple[bool | None, str]:
    """Devuelve (presencia, fuente).

    True  si se menciona en accesorios, versión, título o comentarios.
    False si el vendedor llenó la lista de accesorios y el sunroof no está.
    None  si no hay lista de accesorios ni mención (dato faltante).
    """
    for accesorio in accesorios:
        if PATRON_SUNROOF.search(sin_tildes(accesorio)):
            return True, "accesorios"
    for fuente, texto in otros_textos:
        if texto and PATRON_SUNROOF.search(sin_tildes(str(texto))):
            return True, fuente
    if accesorios:
        return False, "no aparece en la lista de accesorios"
    return None, "sin lista de accesorios"


NIVELES = ("GR-S", "SEG", "XEI", "XLI")


def nivel_version(version: Any) -> str:
    """Agrupa las versiones escritas a mano en niveles de equipamiento.

    '1.8 CVT SEG' y 'SE-G Automatico' -> SEG; '1.8 XE-i Automatico' -> XEI;
    '1.8 XL-i' -> XLI; 'GR-S 2.0' -> GR-S. Lo que no se reconoce queda
    'sin identificar' (no se adivina).
    """
    texto = normalizar(version)
    if not texto:
        return "sin identificar"
    if re.search(r"\bgr[\s-]?s\b|\bgr\b", texto):
        return "GR-S"
    if re.search(r"\bse[\s-]?g\b", texto):
        return "SEG"
    if re.search(r"\bxe[\s-]?i", texto):
        return "XEI"
    if re.search(r"\bxl[\s-]?i", texto):
        return "XLI"
    return "sin identificar"


def campos_detalle(respuesta: dict, id_esperado: str, tarjeta: dict | None = None) -> dict:
    """Extrae los campos del vehículo de la respuesta de 'find-vehicle-detail'.

    Lanza ValueError si la respuesta no trae datos o es de otro anuncio.
    """
    datos = respuesta.get("data") if isinstance(respuesta, dict) else None
    if not isinstance(datos, dict) or not datos:
        raise ValueError("la respuesta no trae datos del anuncio")
    id_recibido = texto_o_nada(datos.get("id") or datos.get("code_carroya"))
    if id_recibido and id_recibido != id_esperado:
        raise ValueError(f"la respuesta corresponde a otro anuncio ({id_recibido})")

    accesorios = [a.strip() for a in (datos.get("accessories") or []) if isinstance(a, str) and a.strip()]
    version = texto_o_nada(datos.get("version"))
    sunroof, fuente_sunroof = detectar_sunroof(
        accesorios,
        ("versión", version),
        ("título", datos.get("title")),
        ("comentarios del vendedor", datos.get("comments")),  # se usan, pero no se guardan
    )
    fila = {
        "marca": texto_o_nada(datos.get("brand")),
        "linea": texto_o_nada(datos.get("model")),
        "anio": numero_o_nada(datos.get("year")),
        "version": version,
        "precio": numero_o_nada(datos.get("price")),
        "moneda": (tarjeta or {}).get("moneda"),
        "kilometraje": numero_o_nada(datos.get("kilometers")),
        "transmision": texto_o_nada(datos.get("box")),
        "ciudad": texto_o_nada(datos.get("city")),
        "sunroof": sunroof,
        "sunroof_fuente": fuente_sunroof,
        "combustible": texto_o_nada(datos.get("fuel")),
        "color": texto_o_nada(datos.get("color")),
        "cilindraje": numero_o_nada(datos.get("cylindrical")),
        "estado_vehiculo": texto_o_nada(datos.get("status")),
        "vendido": texto_o_nada(datos.get("sold")),
        "estado_publicacion": texto_o_nada(datos.get("publicationStatus")),
        "fecha_publicacion_carroya": texto_o_nada(datos.get("fechapublicacion")),
        "n_accesorios": len(accesorios),
        "accesorios": "; ".join(accesorios) or None,
    }
    cumple, motivo = verificar_criterios(fila["marca"], fila["linea"], fila["anio"])
    fila["cumple_criterios"] = cumple
    fila["motivo_no_cumple"] = motivo
    return fila


# --- Privacidad de lo que se guarda en crudo -------------------------------------
CLAVES_PRIVADAS = re.compile(
    r"seller|email|placa|plate|direcc|adress|address|coment|comments|telefono|phone|"
    r"whatsapp|clienteid|nombreempresa|micrositio|logincontact|concessionaire|idcompany|"
    r"^images|image4seo|imagen|multimedia",
    re.IGNORECASE,
)


def sanitizar(objeto: Any) -> Any:
    """Quita datos personales (vendedor, placa, contacto, comentarios) y fotos.

    Las respuestas originales se guardan para trazabilidad, pero sin nada que
    identifique a una persona: el taller no lo necesita.
    """
    if isinstance(objeto, dict):
        return {k: sanitizar(v) for k, v in objeto.items() if not CLAVES_PRIVADAS.search(str(k))}
    if isinstance(objeto, list):
        return [sanitizar(v) for v in objeto]
    return objeto


def recortar_busqueda(respuesta: dict) -> dict:
    """Versión liviana de una página de resultados: totales y anuncios, sin filtros."""
    return {
        "count": (respuesta or {}).get("count"),
        "pages": (respuesta or {}).get("pages"),
        "anuncios": [sanitizar(item) for item in anuncios_de_busqueda(respuesta)],
    }

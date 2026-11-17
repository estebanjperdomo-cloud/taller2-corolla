"""Paso 6 del taller (20 %). Distribución de precios y detección de posibles gangas.

El método, en palabras simples (más detalle en el README):

1. Se usa una sola observación por anuncio: la descargada ese día con un precio
   válido (en pesos y dentro de un rango plausible).
2. Un modelo de precios hedónico calcula el "precio esperado" de cada carro a
   partir de tres cosas: año del modelo, kilometraje y grupo de versión. El grupo
   junta el nivel de equipamiento (XLI, XEI, SEG, GR-S) con el motor (híbrido o
   gasolina), porque en el Corolla una cosa determina la otra. Es una regresión
   del logaritmo del precio, así que cada efecto se lee en porcentaje. Se ajusta
   dos veces; la segunda sin los precios extremos, para que un error de
   digitación o una ganga no muevan la referencia de los demás.
3. Un anuncio es POSIBLE GANGA si cumple las tres condiciones a la vez:
     a. su precio está al menos 12 % por debajo del esperado;
     b. esa diferencia es grande frente a la variación típica del día
        (puntaje z robusto de -2 o menos);
     c. tiene al menos 3 anuncios parecidos (mismo grupo de versión, misma caja,
        año a ±1) y está al menos 8 % por debajo de la mediana de ellos.
   Si la rebaja supera 45 %, se reporta como PRECIO SOSPECHOSAMENTE BAJO, porque
   puede ser un error de digitación, una cuota inicial o un anuncio engañoso.
"""
from __future__ import annotations

import json
import math
from contextlib import closing
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from . import configuracion as config, formato
from . import paso1_extraccion as extraccion
from .paso2_base_de_datos import conectar

# --- Umbrales del método -----------------------------------------------------------------
PRECIO_MIN = 20_000_000          # un Corolla 2022+ no se vende por menos; es un error de digitación
PRECIO_MAX = 400_000_000
KM_MAX = 400_000
KM_PISO = 1_000                  # para que un carro con 0 o 50 km no distorsione el logaritmo
ANIO_REFERENCIA = 2024
KM_REFERENCIA = 30_000           # el kilometraje se centra aquí para que el modelo sea estable
DESCUENTO_MINIMO = 0.12
Z_LIMITE = -2.0
DESCUENTO_VS_COMPARABLES = 0.08
DESCUENTO_SOSPECHOSO = 0.45
MIN_COMPARABLES = 3
MAX_COMPARABLES = 6
MIN_POR_GRUPO = 3
MIN_PARA_MODELO = 15
MIN_PARA_MODELO_SIMPLE = 10
ESCALA_MINIMA = 0.03

POSIBLE_GANGA = "posible ganga"
SOSPECHOSO = "precio sospechosamente bajo"
SIN_RESPALDO = "señal sin suficientes comparables"
NORMAL = "dentro de lo esperado"
ALTO = "por encima de lo esperado"
NO_EVALUABLE = "no evaluable"
INVALIDO = "precio inválido"
ALERTAS = (POSIBLE_GANGA, SOSPECHOSO)


def _nulo(valor) -> bool:
    return valor is None or (isinstance(valor, float) and math.isnan(valor)) or valor is pd.NA


# --- Carga de datos --------------------------------------------------------------------
def cargar_dia(ruta_bd: Path, fecha: date) -> tuple[pd.DataFrame, dict]:
    """Observaciones descargadas ese día, una por anuncio, y conteos de contexto."""
    dia = fecha.isoformat()
    with closing(conectar(ruta_bd)) as con:
        tabla = pd.read_sql_query(
            """SELECT o.*, a.primera_fecha_visto
               FROM observaciones o JOIN anuncios a ON a.id_anuncio = o.id_anuncio
               WHERE o.fecha = ? AND o.disponibilidad = 'encontrado' AND o.estado_descarga = 'descargado'
               ORDER BY o.id_anuncio""", con, params=(dia,))
        contexto = {
            "encontrados_hoy": con.execute("SELECT COUNT(*) FROM observaciones WHERE fecha = ? "
                                           "AND disponibilidad = 'encontrado'", (dia,)).fetchone()[0],
            "dias_previos": con.execute("SELECT COUNT(DISTINCT fecha) FROM observaciones WHERE fecha < ?",
                                        (dia,)).fetchone()[0],
            "cambios_precio": [dict(f) for f in con.execute(
                """SELECT c.*, a.url, a.anio, a.version, a.kilometraje, a.ciudad, a.disponibilidad_actual
                   FROM cambios c JOIN anuncios a ON a.id_anuncio = c.id_anuncio
                   WHERE c.fecha = ? AND c.campo = 'precio'""", (dia,))],
        }
    tabla["es_nuevo"] = tabla["primera_fecha_visto"] == dia
    return tabla, contexto


# --- Validación y variables ------------------------------------------------------------
def motivo_precio_invalido(precio, moneda) -> str | None:
    if _nulo(precio):
        return "sin precio publicado"
    if _nulo(moneda):
        return "moneda no informada"
    if moneda != "COP":
        return f"moneda {moneda}, no comparable con pesos"
    if precio < PRECIO_MIN:
        return f"menor a {formato.millones(PRECIO_MIN, 0)}, probable error de digitación"
    if precio > PRECIO_MAX:
        return f"mayor a {formato.millones(PRECIO_MAX, 0)}, fuera de lo plausible"
    return None


def clasificar_transmision(texto) -> float:
    t = extraccion.normalizar(texto)
    if not t:
        return np.nan
    if "mecan" in t or "manual" in t:
        return 0.0
    if any(p in t for p in ("autom", "cvt", "secuencial", "tiptronic")):
        return 1.0
    return np.nan


def es_hibrido(texto) -> float:
    t = extraccion.normalizar(texto)
    if not t:
        return np.nan
    return 1.0 if ("hibrid" in t or "hybrid" in t) else 0.0


def _grupo(nivel: str, hibrido: float) -> str:
    """'SEG híbrido', 'GR-S gasolina'... Nivel de equipamiento y motor en un solo grupo."""
    if _nulo(hibrido):
        return f"{nivel} (combustible sin dato)"
    return f"{nivel} {'híbrido' if hibrido == 1 else 'gasolina'}"


def preparar(tabla: pd.DataFrame) -> pd.DataFrame:
    d = tabla.copy()
    d["precio"] = pd.to_numeric(d["precio"], errors="coerce")
    d["anio"] = pd.to_numeric(d["anio"], errors="coerce")
    km = pd.to_numeric(d["kilometraje"], errors="coerce")
    d["kilometraje"] = km
    d["nivel"] = [extraccion.nivel_version(v if not _nulo(v) else None) for v in d["version"]]
    d["hibrido"] = [es_hibrido(c if not _nulo(c) else None) for c in d["combustible"]]
    d["automatica"] = [clasificar_transmision(t if not _nulo(t) else None) for t in d["transmision"]]
    d["km_valido"] = km.notna() & (km > 0) & (km <= KM_MAX)
    d["ln_km"] = np.log(np.maximum(km.where(d["km_valido"]), KM_PISO) / KM_REFERENCIA)
    d["grupo"] = [_grupo(n, h) for n, h in zip(d["nivel"], d["hibrido"])]
    d["anio_c"] = d["anio"] - ANIO_REFERENCIA
    d["ln_precio"] = np.log(d["precio"].where(d["precio"] > 0))
    d["motivo_invalido"] = [motivo_precio_invalido(p, m if not _nulo(m) else None)
                            for p, m in zip(d["precio"], d["moneda"])]
    d["precio_valido"] = d["motivo_invalido"].isna()
    return d


# --- Estadísticas ------------------------------------------------------------------------
def estadisticas(precios: pd.Series) -> dict | None:
    precios = pd.to_numeric(precios, errors="coerce").dropna()
    if precios.empty:
        return None
    q1, mediana, q3 = np.percentile(precios, [25, 50, 75])
    return {
        "n": int(len(precios)),
        "media": float(precios.mean()),
        "desviacion": float(precios.std(ddof=1)) if len(precios) > 1 else 0.0,
        "minimo": float(precios.min()),
        "q1": float(q1),
        "mediana": float(mediana),
        "q3": float(q3),
        "maximo": float(precios.max()),
        "rango_intercuartil": float(q3 - q1),
    }


# --- Modelo de precios -----------------------------------------------------------------------
OTRAS = "otras versiones"


@dataclass
class Modelo:
    beta: np.ndarray
    escala: float                 # dispersión robusta de los residuos (en logaritmo)
    n: int
    n_atipicos: int
    r2: float
    grupo_base: str
    grupos: list                  # grupos con variable propia (todos menos el base)
    simplificado: bool
    notas: list = field(default_factory=list)

    def nombres(self) -> list[str]:
        return (["intercepto", "año del modelo", "logaritmo del kilometraje"]
                + [f"grupo {g}" for g in self.grupos])

    def matriz(self, d: pd.DataFrame) -> np.ndarray:
        columnas = [np.ones(len(d)), d["anio_c"].to_numpy(float), d["ln_km"].to_numpy(float)]
        columnas += [(d["grupo_modelo"] == g).to_numpy(float) for g in self.grupos]
        return np.column_stack(columnas)

    def predecir(self, d: pd.DataFrame) -> np.ndarray:
        return self.matriz(d) @ self.beta

    def efectos(self) -> list[str]:
        """Los coeficientes traducidos a frases (para el resumen y el correo)."""
        b = dict(zip(self.nombres(), self.beta))

        def cambio(factor: float) -> tuple[str, str]:
            variacion = factor - 1
            return formato.porcentaje(abs(variacion)), ("sube" if variacion >= 0 else "baja")

        pct, verbo = cambio(math.exp(b["año del modelo"]))
        frases = [f"Cada año más nuevo {verbo} el precio {pct}."]
        pct, verbo = cambio(2 ** b["logaritmo del kilometraje"])
        frases.append(f"Duplicar el kilometraje {verbo} el precio {pct}.")
        for g in self.grupos:
            variacion = math.exp(b[f"grupo {g}"]) - 1
            sujeto = "El grupo de otras versiones" if g == OTRAS else f"La versión {g}"
            frases.append(f"{sujeto} cuesta {formato.porcentaje(abs(variacion))} "
                          f"{'más' if variacion >= 0 else 'menos'} que la versión {self.grupo_base}.")
        return frases


def _mad(valores: np.ndarray) -> float:
    return float(1.4826 * np.median(np.abs(valores - np.median(valores))))


def _ajustar(X: np.ndarray, y: np.ndarray):
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return beta, y - X @ beta


# --- Evaluación de cada anuncio ---------------------------------------------------------------
def evaluar(tabla: pd.DataFrame) -> tuple[pd.DataFrame, Modelo | None, list[str]]:
    """Calcula precio esperado, descuento, z y clasificación de cada anuncio del día."""
    d = preparar(tabla)
    notas: list[str] = []
    d["motivo_no_evaluable"] = None
    sin_requisitos = [
        (~d["precio_valido"], "precio inválido"),
        (d["anio"].isna(), "sin año del modelo"),
        (~d["km_valido"], "kilometraje no informado o no válido"),
    ]
    for mascara, motivo in sin_requisitos:
        d.loc[mascara & d["motivo_no_evaluable"].isna(), "motivo_no_evaluable"] = motivo
    candidatos = d["motivo_no_evaluable"].isna()

    # Grupos de versión con menos de 3 anuncios se juntan en "otras versiones";
    # si ese grupo también queda con menos de 3, esos anuncios no se pueden evaluar.
    conteo = d.loc[candidatos, "grupo"].value_counts()
    pequenos = set(conteo[conteo < MIN_POR_GRUPO].index)
    d["grupo_modelo"] = [(OTRAS if g in pequenos else g) for g in d["grupo"]]
    if pequenos:
        notas.append(f"Versiones con menos de {MIN_POR_GRUPO} anuncios se agrupan como '{OTRAS}' "
                     f"({', '.join(sorted(pequenos))}).")
    if 0 < (d.loc[candidatos, "grupo_modelo"] == OTRAS).sum() < MIN_POR_GRUPO:
        mascara = candidatos & (d["grupo_modelo"] == OTRAS)
        d.loc[mascara, "motivo_no_evaluable"] = "versión con muy pocos anuncios para compararla"
        candidatos &= ~mascara

    conteo = d.loc[candidatos, "grupo_modelo"].value_counts()
    grupo_base = conteo.idxmax() if not conteo.empty else "XEI híbrido"
    grupos = sorted(set(conteo.index) - {grupo_base})
    n = int(candidatos.sum())
    simplificado = False
    if n < max(MIN_PARA_MODELO, 4 * (3 + len(grupos))):
        simplificado, grupos = True, []
        notas.append(f"Con {n} anuncios evaluables se usa un modelo simplificado (solo año y kilometraje); "
                     "la versión se tiene en cuenta al elegir los comparables.")
    if n < MIN_PARA_MODELO_SIMPLE:
        d.loc[candidatos, "motivo_no_evaluable"] = (f"hoy solo hay {n} anuncios válidos, muy pocos para "
                                                    "estimar un precio de referencia")
        return _completar(d, None), None, notas + ["No se estimó modelo por falta de datos."]
    notas.append("La transmisión no entra al modelo porque casi todos los Corolla 2022 a 2026 son automáticos; "
                 "se usa al elegir los anuncios comparables.")

    modelo = Modelo(beta=np.zeros(0), escala=0.0, n=n, n_atipicos=0, r2=float("nan"),
                    grupo_base=grupo_base, grupos=grupos, simplificado=simplificado, notas=notas)
    X = modelo.matriz(d[candidatos])
    y = d.loc[candidatos, "ln_precio"].to_numpy(float)
    beta, residuos = _ajustar(X, y)
    escala = max(_mad(residuos), ESCALA_MINIMA)
    normales = np.abs(residuos) <= 3 * escala
    if (~normales).any() and normales.sum() >= X.shape[1] + 5:
        beta, _ = _ajustar(X[normales], y[normales])
    residuos_normales = y[normales] - X[normales] @ beta
    modelo.beta = beta
    modelo.escala = max(_mad(residuos_normales), ESCALA_MINIMA)
    modelo.n_atipicos = int((~normales).sum())
    total = np.sum((y[normales] - y[normales].mean()) ** 2)
    modelo.r2 = float(1 - np.sum(residuos_normales ** 2) / total) if total > 0 else float("nan")

    evaluables = d["motivo_no_evaluable"].isna()
    d.loc[evaluables, "ln_esperado"] = modelo.predecir(d[evaluables])
    return _completar(d, modelo), modelo, notas


def _completar(d: pd.DataFrame, modelo: Modelo | None) -> pd.DataFrame:
    """Agrega comparables, clasificación y explicación a cada anuncio."""
    for columna in ("ln_esperado", "precio_esperado", "descuento", "z", "n_comparables",
                    "mediana_comparables", "descuento_vs_comparables"):
        if columna not in d:
            d[columna] = np.nan
    d["precio_esperado"] = np.exp(d["ln_esperado"])
    d["descuento"] = 1 - d["precio"] / d["precio_esperado"]
    if modelo is not None:
        d["z"] = (d["ln_precio"] - d["ln_esperado"]) / modelo.escala
    d["clasificacion"] = None
    d["explicacion"] = None
    d["comparables_desc"] = None
    d["es_el_mas_barato"] = False

    evaluables = d[d["motivo_no_evaluable"].isna() & d["ln_esperado"].notna()]
    for indice, fila in d.iterrows():
        if not fila["precio_valido"]:
            d.at[indice, "clasificacion"] = INVALIDO
            d.at[indice, "explicacion"] = f"No se analiza porque el precio es inválido ({fila['motivo_invalido']})."
            continue
        if not _nulo(fila["motivo_no_evaluable"]) or modelo is None:
            d.at[indice, "clasificacion"] = NO_EVALUABLE
            d.at[indice, "explicacion"] = f"No se puede evaluar ({fila['motivo_no_evaluable']})."
            continue
        comparables = _comparables(fila, evaluables)
        n_comp = len(comparables)
        d.at[indice, "n_comparables"] = n_comp
        if n_comp:
            mediana = float(comparables["precio"].median())
            d.at[indice, "mediana_comparables"] = mediana
            d.at[indice, "descuento_vs_comparables"] = 1 - fila["precio"] / mediana
            d.at[indice, "es_el_mas_barato"] = bool(fila["precio"] < comparables["precio"].min())
            d.at[indice, "comparables_desc"] = _describir_grupo(comparables, fila)
        d.at[indice, "clasificacion"] = clasificar(d.loc[indice])
        d.at[indice, "explicacion"] = explicar(d.loc[indice], modelo)
    return d


def _comparables(fila: pd.Series, pool: pd.DataFrame) -> pd.DataFrame:
    """Los anuncios más parecidos: mismo grupo de versión, misma caja (si se conoce)
    y año a ±1, ordenados por cercanía en año y kilometraje. Máximo 6."""
    c = pool[(pool["id_anuncio"] != fila["id_anuncio"])
             & (pool["grupo_modelo"] == fila["grupo_modelo"])
             & ((pool["anio"] - fila["anio"]).abs() <= 1)]
    if not _nulo(fila["automatica"]):
        c = c[c["automatica"] == fila["automatica"]]
    distancia = (c["anio"] - fila["anio"]).abs() + (c["ln_km"] - fila["ln_km"]).abs()
    return c.assign(distancia=distancia).nsmallest(MAX_COMPARABLES, "distancia")


def clasificar(fila: pd.Series) -> str:
    regla_modelo = fila["descuento"] >= DESCUENTO_MINIMO and fila["z"] <= Z_LIMITE
    if regla_modelo:
        if _nulo(fila["n_comparables"]) or fila["n_comparables"] < MIN_COMPARABLES:
            return SIN_RESPALDO
        if fila["descuento_vs_comparables"] < DESCUENTO_VS_COMPARABLES:
            return NORMAL
        return SOSPECHOSO if fila["descuento"] > DESCUENTO_SOSPECHOSO else POSIBLE_GANGA
    if fila["z"] >= -Z_LIMITE:
        return ALTO
    return NORMAL


# --- Explicaciones en lenguaje sencillo ------------------------------------------------------------
def describir_carro(fila: pd.Series) -> str:
    partes = [f"Corolla {int(fila['anio']) if not _nulo(fila['anio']) else 'sin año'}"]
    partes[0] += f" {fila['version']}" if not _nulo(fila["version"]) else " sin versión informada"
    if not _nulo(fila.get("combustible")):
        partes.append(str(fila["combustible"]).lower())
    if not _nulo(fila.get("transmision")):
        partes.append(f"caja {str(fila['transmision']).lower()}")
    if not _nulo(fila.get("kilometraje")):
        partes.append(formato.kilometros(fila["kilometraje"]))
    if not _nulo(fila.get("ciudad")):
        partes.append(str(fila["ciudad"]).title())
    return ", ".join(partes)


def _describir_grupo(comparables: pd.DataFrame, fila: pd.Series) -> str:
    anios = comparables["anio"].dropna().astype(int)
    kms = comparables["kilometraje"].dropna()
    rango_anios = f"modelo {anios.min()}" if anios.min() == anios.max() else f"modelos {anios.min()} a {anios.max()}"
    grupo = fila["grupo_modelo"]
    nivel_txt = OTRAS if grupo == OTRAS else f"versión {grupo}"
    return (f"{nivel_txt}, {rango_anios}, entre {formato.miles(kms.min())} y "
            f"{formato.kilometros(kms.max())}")


def explicar(fila: pd.Series, modelo: Modelo) -> str:
    esperado = fila["precio_esperado"]
    descuento = fila["descuento"]
    direccion = "por debajo" if descuento >= 0 else "por encima"
    texto = (f"Está publicado en {formato.millones(fila['precio'])}. Para un carro con ese año, "
             f"kilometraje y versión, el modelo de precios del día espera unos {formato.millones(esperado)}, "
             f"así que este anuncio está {formato.porcentaje(abs(descuento))} {direccion}.")
    clasificacion = fila["clasificacion"]
    if clasificacion in ALERTAS or clasificacion == SIN_RESPALDO:
        texto += (f" Esa diferencia equivale a {formato.decimal(abs(fila['z']))} veces la variación típica "
                  f"entre anuncios de hoy, algo poco común.")
    n_comp = 0 if _nulo(fila["n_comparables"]) else int(fila["n_comparables"])
    if n_comp:
        palabra = "anuncio más parecido" if n_comp == 1 else f"{n_comp} anuncios más parecidos"
        verbo = "tiene" if n_comp == 1 else "tienen una mediana de"
        texto += (f" {'Su' if n_comp == 1 else 'Sus'} {palabra} ({fila['comparables_desc']}) "
                  f"{verbo} {formato.millones(fila['mediana_comparables'])}")
        texto += " y este es el más barato del grupo." if fila["es_el_mas_barato"] else "."
    if clasificacion == SIN_RESPALDO:
        texto += (f" No se emite alerta porque hay menos de {MIN_COMPARABLES} anuncios parecidos para "
                  "confirmar que el precio es inusual.")
    if clasificacion == SOSPECHOSO:
        texto += (" La rebaja es tan grande que puede ser un error de digitación, un precio de cuota "
                  "inicial o un anuncio engañoso. Conviene verificarlo antes de confiar en él.")
    if clasificacion in ALERTAS and fila.get("sunroof") in (1, True, 1.0):
        texto += " Además declara sunroof."
    return texto


# --- Orquestación del análisis del día --------------------------------------------------------------
COLUMNAS_SALIDA = [
    "id_anuncio", "url", "es_nuevo", "anio", "version", "grupo_modelo", "kilometraje", "transmision",
    "combustible", "ciudad", "sunroof", "precio", "precio_valido", "motivo_invalido",
    "motivo_no_evaluable", "precio_esperado", "descuento", "z", "n_comparables",
    "mediana_comparables", "descuento_vs_comparables", "clasificacion", "explicacion",
]


def _a_json(valor):
    if isinstance(valor, (np.integer,)):
        return int(valor)
    if isinstance(valor, (np.floating, float)):
        return None if math.isnan(valor) else float(valor)
    if isinstance(valor, (np.bool_,)):
        return bool(valor)
    if valor is pd.NA:
        return None
    return valor


def _registro(fila: pd.Series) -> dict:
    return {c: _a_json(fila.get(c)) for c in COLUMNAS_SALIDA + ["comparables_desc", "es_el_mas_barato"]}


def analizar_dia(ruta_bd: Path, fecha: date, carpeta: Path) -> dict:
    """Corre todo el paso 6 para un día y deja en 'carpeta' el CSV, el resumen y la gráfica."""
    from . import paso6_grafica as graficas  # import diferido: matplotlib solo se carga si hace falta

    carpeta.mkdir(parents=True, exist_ok=True)
    tabla, contexto = cargar_dia(ruta_bd, fecha)
    dia = fecha.isoformat()
    excluidos = int((tabla["cumple_criterios"] == 0).sum()) if not tabla.empty else 0
    tabla = tabla[tabla["cumple_criterios"] == 1] if not tabla.empty else tabla

    resumen = {
        "fecha": dia,
        "generado_en": config.iso(config.ahora()),
        "primera_ejecucion": contexto["dias_previos"] == 0,
        "anuncios_encontrados_hoy": contexto["encontrados_hoy"],
        "anuncios_descargados": int(len(tabla)) + excluidos,
        "excluidos_por_criterios": excluidos,
        "umbrales": {"descuento_minimo": DESCUENTO_MINIMO, "z_limite": Z_LIMITE,
                     "descuento_vs_comparables": DESCUENTO_VS_COMPARABLES,
                     "descuento_sospechoso": DESCUENTO_SOSPECHOSO, "min_comparables": MIN_COMPARABLES,
                     "precio_min": PRECIO_MIN, "precio_max": PRECIO_MAX},
    }
    if tabla.empty:
        resumen.update(precios_validos=0, estadisticas=None, por_anio=[], modelo=None, evaluables=0,
                       no_evaluables={}, precios_invalidos=[], alertas=[], alertas_nuevas=[],
                       senales_sin_respaldo=0, grafica=None,
                       motivo_sin_grafica="no hay anuncios descargados con datos para este día")
    else:
        d, modelo, notas = evaluar(tabla)
        validos = d[d["precio_valido"]]
        resumen["precios_validos"] = int(len(validos))
        resumen["estadisticas"] = estadisticas(validos["precio"])
        resumen["por_anio"] = [
            {"anio": int(anio), "n": int(len(g)), "mediana": float(g["precio"].median())}
            for anio, g in validos.dropna(subset=["anio"]).groupby("anio")]
        resumen["precios_invalidos"] = [
            {"id_anuncio": f["id_anuncio"], "url": f["url"], "precio": _a_json(f["precio"]),
             "motivo": f["motivo_invalido"]} for _, f in d[~d["precio_valido"]].iterrows()]
        resumen["modelo"] = None if modelo is None else {
            "tipo": "simplificado" if modelo.simplificado else "completo",
            "n": modelo.n, "variables": modelo.nombres()[1:], "grupo_base": modelo.grupo_base,
            "efectos": modelo.efectos(), "r2": _a_json(modelo.r2),
            "variacion_tipica_pct": _a_json(math.exp(modelo.escala) - 1),
            "atipicos_excluidos_del_ajuste": modelo.n_atipicos,
        }
        resumen["notas_modelo"] = notas
        resumen["evaluables"] = int(d["motivo_no_evaluable"].isna().sum()) if modelo else 0
        resumen["no_evaluables"] = {k: int(v) for k, v in d["motivo_no_evaluable"].value_counts().items()}
        # Primero las posibles gangas (de mayor a menor descuento) y al final las que hay que verificar.
        alertas = (d[d["clasificacion"].isin(ALERTAS)]
                   .assign(orden=lambda x: x["clasificacion"] == SOSPECHOSO)
                   .sort_values(["orden", "descuento"], ascending=[True, False]))
        resumen["alertas"] = [{**_registro(f), "descripcion": describir_carro(f)} for _, f in alertas.iterrows()]
        resumen["alertas_nuevas"] = [a for a in resumen["alertas"] if a["es_nuevo"]]
        resumen["senales_sin_respaldo"] = int((d["clasificacion"] == SIN_RESPALDO).sum())

        salida = d[COLUMNAS_SALIDA].sort_values(["clasificacion", "descuento"], ascending=[True, False])
        salida.to_csv(carpeta / f"analisis_{dia}.csv", index=False, encoding="utf-8")
        d[d["clasificacion"].isin(ALERTAS)][COLUMNAS_SALIDA].to_csv(
            carpeta / f"gangas_{dia}.csv", index=False, encoding="utf-8")

        if len(validos) >= 3:
            ruta_png = carpeta / f"distribucion_precios_{dia}.png"
            graficas.distribucion_precios(validos, resumen["estadisticas"], fecha, ruta_png)
            resumen["grafica"], resumen["motivo_sin_grafica"] = ruta_png.name, None
        else:
            resumen["grafica"] = None
            resumen["motivo_sin_grafica"] = f"solo hay {len(validos)} anuncios con precio válido; se necesitan 3"

    resumen["bajadas_precio"], resumen["subidas_precio"] = _cambios_de_precio(contexto["cambios_precio"])
    (carpeta / f"resumen_{dia}.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2, default=_a_json), encoding="utf-8")
    return resumen


def _cambios_de_precio(cambios: list[dict]) -> tuple[list[dict], int]:
    bajadas, subidas = [], 0
    for c in cambios:
        try:
            antes, ahora = float(c["valor_anterior"]), float(c["valor_nuevo"])
        except (TypeError, ValueError):
            continue
        if ahora < antes:
            bajadas.append({
                "id_anuncio": c["id_anuncio"], "url": c["url"], "precio_anterior": antes,
                "precio_nuevo": ahora, "variacion": ahora / antes - 1, "fecha_anterior": c["fecha_anterior"],
                "descripcion": f"Corolla {c['anio']} {c['version'] or ''}".strip() + (
                    f", {formato.kilometros(c['kilometraje'])}" if c.get("kilometraje") else ""),
            })
        elif ahora > antes:
            subidas += 1
    return sorted(bajadas, key=lambda b: b["variacion"]), subidas

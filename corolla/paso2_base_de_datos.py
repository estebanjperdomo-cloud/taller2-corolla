"""Paso 2 del taller (15 %). Diseño de la base de datos consolidada.

Qué pide el taller
  Poder consultar los anuncios únicos, la información más reciente de cada uno,
  sus observaciones diarias y cambios, la primera y la última fecha en que se vio
  y su disponibilidad con la fecha y hora de cada descarga.

Qué escogimos
  SQLite, un solo archivo (datos/<modo>/consolidado/corolla.sqlite) que Python
  maneja sin instalar nada más, con SQL y transacciones. La comparación con otras
  alternativas está en el README.

Tablas
  anuncios               una fila por anuncio único, con la primera y la última fecha
                         en que se vio, la disponibilidad actual y la información más
                         reciente. Se reconstruye siempre desde 'observaciones'.
  observaciones          una fila por anuncio y por día (llave id_anuncio + fecha). Es el
                         historial con la disponibilidad observada, el estado y la hora
                         de la descarga y los datos del vehículo de ese día.
  cambios                una fila por cada campo que cambió frente a la observación anterior.
  archivos_procesados    huella SHA-256 de los archivos de cada día, para no duplicar.
  posibles_duplicados    parejas de anuncios que podrían ser el mismo vehículo.

Identificador estable
  El UUID que Carroya asigna a cada publicación, que es el último segmento de la URL
  de la ficha (campo 'id' de la respuesta). No se usa la URL completa porque lleva la
  ciudad y el año, que el vendedor puede editar.

Las funciones que llenan estas tablas están en paso3_actualizacion.py.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

ENCONTRADO = "encontrado"
NO_ENCONTRADO = "no_encontrado"     # no apareció en una búsqueda COMPLETA
DESCONOCIDA = "desconocida"         # no apareció, pero la búsqueda tuvo errores

CAMPOS_VEHICULO = [
    "marca", "linea", "anio", "version", "precio", "moneda", "kilometraje", "transmision",
    "ciudad", "sunroof", "sunroof_fuente", "combustible", "color", "cilindraje",
    "estado_vehiculo", "vendido", "estado_publicacion", "fecha_publicacion_carroya",
    "n_accesorios", "accesorios",
]
# Campos cuyo cambio se registra en la tabla 'cambios'.
CAMPOS_COMPARADOS = [
    "precio", "kilometraje", "anio", "version", "transmision", "combustible", "ciudad",
    "color", "sunroof", "moneda", "vendido", "estado_publicacion",
]

ESQUEMA = """
CREATE TABLE IF NOT EXISTS observaciones (
    id_anuncio              TEXT NOT NULL,
    fecha                   TEXT NOT NULL,            -- AAAA-MM-DD (día de la recolección)
    run_id                  TEXT,
    url                     TEXT,
    disponibilidad          TEXT NOT NULL CHECK (disponibilidad IN ('encontrado','no_encontrado','desconocida')),
    estado_descarga         TEXT,                     -- descargado | fallido | sin intentar | NULL si no se encontró
    fecha_hora_descarga     TEXT,                     -- ISO 8601 con -05:00
    motivo_error            TEXT,
    cumple_criterios        INTEGER,
    motivo_no_cumple        TEXT,
    marca TEXT, linea TEXT, anio INTEGER, version TEXT, precio REAL, moneda TEXT,
    kilometraje REAL, transmision TEXT, ciudad TEXT, sunroof INTEGER, sunroof_fuente TEXT,
    combustible TEXT, color TEXT, cilindraje REAL, estado_vehiculo TEXT, vendido TEXT,
    estado_publicacion TEXT, fecha_publicacion_carroya TEXT, n_accesorios INTEGER, accesorios TEXT,
    PRIMARY KEY (id_anuncio, fecha)
);
CREATE INDEX IF NOT EXISTS idx_observaciones_fecha ON observaciones (fecha);

CREATE TABLE IF NOT EXISTS cambios (
    id_anuncio      TEXT NOT NULL,
    fecha           TEXT NOT NULL,     -- día en que se detectó el cambio
    campo           TEXT NOT NULL,
    valor_anterior  TEXT,
    valor_nuevo     TEXT,
    fecha_anterior  TEXT,              -- día de la observación con la que se comparó
    PRIMARY KEY (id_anuncio, fecha, campo)
);

CREATE TABLE IF NOT EXISTS anuncios (
    id_anuncio                  TEXT PRIMARY KEY,
    url                         TEXT,
    primera_fecha_visto         TEXT,
    ultima_fecha_visto          TEXT,
    dias_encontrado             INTEGER,
    dias_no_encontrado          INTEGER,
    dias_desconocida            INTEGER,
    disponibilidad_actual       TEXT,
    fecha_ultima_observacion    TEXT,
    primera_descarga            TEXT,
    ultima_descarga             TEXT,
    descargas_exitosas          INTEGER,
    descargas_fallidas          INTEGER,
    fecha_datos                 TEXT,          -- día de la información más reciente
    cumple_criterios            INTEGER,
    marca TEXT, linea TEXT, anio INTEGER, version TEXT, precio REAL, moneda TEXT,
    kilometraje REAL, transmision TEXT, ciudad TEXT, sunroof INTEGER, sunroof_fuente TEXT,
    combustible TEXT, color TEXT, cilindraje REAL, estado_vehiculo TEXT, vendido TEXT,
    estado_publicacion TEXT, fecha_publicacion_carroya TEXT, n_accesorios INTEGER, accesorios TEXT,
    precio_primera_observacion  REAL
);

CREATE TABLE IF NOT EXISTS archivos_procesados (
    fecha           TEXT PRIMARY KEY,
    archivo_datos   TEXT,
    huella_sha256   TEXT,
    procesado_en    TEXT,
    run_id          TEXT,
    filas           INTEGER
);

CREATE TABLE IF NOT EXISTS posibles_duplicados (
    id_a            TEXT NOT NULL,
    id_b            TEXT NOT NULL,
    criterio        TEXT,
    fecha_deteccion TEXT,
    PRIMARY KEY (id_a, id_b)
);
"""

SQL_RECONSTRUIR_ANUNCIOS = f"""
DELETE FROM anuncios;
INSERT INTO anuncios (
    id_anuncio, url, primera_fecha_visto, ultima_fecha_visto, dias_encontrado,
    dias_no_encontrado, dias_desconocida, disponibilidad_actual, fecha_ultima_observacion,
    primera_descarga, ultima_descarga, descargas_exitosas, descargas_fallidas, fecha_datos,
    cumple_criterios, {", ".join(CAMPOS_VEHICULO)}, precio_primera_observacion)
WITH resumen AS (
    SELECT id_anuncio,
           MIN(CASE WHEN disponibilidad = 'encontrado' THEN fecha END)              AS primera_fecha_visto,
           MAX(CASE WHEN disponibilidad = 'encontrado' THEN fecha END)              AS ultima_fecha_visto,
           SUM(disponibilidad = 'encontrado')                                       AS dias_encontrado,
           SUM(disponibilidad = 'no_encontrado')                                    AS dias_no_encontrado,
           SUM(disponibilidad = 'desconocida')                                      AS dias_desconocida,
           MIN(CASE WHEN estado_descarga = 'descargado' THEN fecha_hora_descarga END) AS primera_descarga,
           MAX(CASE WHEN estado_descarga = 'descargado' THEN fecha_hora_descarga END) AS ultima_descarga,
           SUM(estado_descarga = 'descargado')                                      AS descargas_exitosas,
           SUM(estado_descarga = 'fallido')                                         AS descargas_fallidas
    FROM observaciones GROUP BY id_anuncio
),
ultima AS (
    SELECT id_anuncio, fecha, disponibilidad, url,
           ROW_NUMBER() OVER (PARTITION BY id_anuncio ORDER BY fecha DESC) AS orden
    FROM observaciones
),
dato AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY id_anuncio ORDER BY fecha DESC) AS orden
    FROM observaciones WHERE estado_descarga = 'descargado'
),
primer_dato AS (
    SELECT id_anuncio, precio, ROW_NUMBER() OVER (PARTITION BY id_anuncio ORDER BY fecha ASC) AS orden
    FROM observaciones WHERE estado_descarga = 'descargado'
)
SELECT r.id_anuncio, COALESCE(d.url, u.url), r.primera_fecha_visto, r.ultima_fecha_visto,
       r.dias_encontrado, r.dias_no_encontrado, r.dias_desconocida, u.disponibilidad, u.fecha,
       r.primera_descarga, r.ultima_descarga, r.descargas_exitosas, r.descargas_fallidas,
       d.fecha, d.cumple_criterios, {", ".join("d." + c for c in CAMPOS_VEHICULO)}, p.precio
FROM resumen r
JOIN ultima u ON u.id_anuncio = r.id_anuncio AND u.orden = 1
LEFT JOIN dato d ON d.id_anuncio = r.id_anuncio AND d.orden = 1
LEFT JOIN primer_dato p ON p.id_anuncio = r.id_anuncio AND p.orden = 1;
"""

COLUMNAS_OBSERVACION = (["id_anuncio", "fecha", "run_id", "url", "disponibilidad", "estado_descarga",
                         "fecha_hora_descarga", "motivo_error", "cumple_criterios", "motivo_no_cumple"]
                        + CAMPOS_VEHICULO)


# --- Conexión ---------------------------------------------------------------------------
def conectar(ruta_bd: Path) -> sqlite3.Connection:
    ruta_bd = Path(ruta_bd)
    ruta_bd.parent.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(ruta_bd)
    conexion.row_factory = sqlite3.Row
    conexion.executescript(ESQUEMA)
    return conexion


def ids_conocidos(ruta_bd: Path, antes_de: date) -> set[str]:
    """Anuncios que el sistema ya había encontrado antes de esa fecha."""
    if not Path(ruta_bd).exists():
        return set()
    with closing(conectar(ruta_bd)) as con:
        filas = con.execute("SELECT DISTINCT id_anuncio FROM observaciones "
                            "WHERE fecha < ? AND disponibilidad = 'encontrado'", (antes_de.isoformat(),))
        return {fila[0] for fila in filas}


# --- Las consultas que pide el paso 2 ---------------------------------------------------
# Las mismas consultas están en consultas.sql para correrlas con otro programa.
CONSULTAS = {
    "1. Anuncios únicos encontrados en el periodo": """
        SELECT id_anuncio, primera_fecha_visto, anio, version, precio, ciudad
        FROM anuncios ORDER BY primera_fecha_visto, id_anuncio""",
    "2. Información más reciente de cada anuncio": """
        SELECT id_anuncio, fecha_datos, anio, version, precio, moneda, kilometraje,
               transmision, ciudad, sunroof, disponibilidad_actual
        FROM anuncios ORDER BY precio""",
    "3a. Observaciones diarias": """
        SELECT fecha, id_anuncio, disponibilidad, estado_descarga, precio, kilometraje
        FROM observaciones ORDER BY id_anuncio, fecha""",
    "3b. Cambios detectados": """
        SELECT fecha, id_anuncio, campo, valor_anterior, valor_nuevo, fecha_anterior
        FROM cambios ORDER BY fecha, id_anuncio, campo""",
    "4. Primera y última fecha en que se observó cada anuncio": """
        SELECT id_anuncio, primera_fecha_visto, ultima_fecha_visto, dias_encontrado,
               dias_no_encontrado, dias_desconocida
        FROM anuncios ORDER BY primera_fecha_visto, id_anuncio""",
    "5. Disponibilidad observada y fecha y hora de cada descarga": """
        SELECT fecha, id_anuncio, disponibilidad, estado_descarga, fecha_hora_descarga, motivo_error
        FROM observaciones ORDER BY fecha, id_anuncio""",
}


def consultar(ruta_bd: Path, id_anuncio: str | None = None) -> dict:
    """Corre las consultas del paso 2 y devuelve {título: tabla de pandas}.

    Con id_anuncio, las consultas de observaciones y cambios se limitan a ese anuncio.
    """
    import pandas as pd

    resultados = {}
    with closing(conectar(ruta_bd)) as con:
        for titulo, sql in CONSULTAS.items():
            parametros: tuple = ()
            if id_anuncio:
                sql = f"SELECT * FROM ({sql}) WHERE id_anuncio = ?"
                parametros = (id_anuncio,)
            resultados[titulo] = pd.read_sql_query(sql, con, params=parametros)
    return resultados


# --- Exportación para revisar la base sin SQL ----------------------------------------
def exportar(ruta_bd: Path, destino: Path) -> list[Path]:
    """Exporta cada tabla a CSV y todas juntas a un Excel, para revisar sin SQL."""
    import pandas as pd

    destino.mkdir(parents=True, exist_ok=True)
    archivos = []
    with closing(conectar(ruta_bd)) as con:
        tablas = {
            "anuncios": "SELECT * FROM anuncios ORDER BY primera_fecha_visto, id_anuncio",
            "observaciones": "SELECT * FROM observaciones ORDER BY fecha, id_anuncio",
            "cambios": "SELECT * FROM cambios ORDER BY fecha, id_anuncio, campo",
            "posibles_duplicados": "SELECT * FROM posibles_duplicados",
            "archivos_procesados": "SELECT * FROM archivos_procesados ORDER BY fecha",
        }
        hojas = {nombre: pd.read_sql_query(sql, con) for nombre, sql in tablas.items()}
    for nombre, tabla in hojas.items():
        ruta = destino / f"{nombre}.csv"
        tabla.to_csv(ruta, index=False, encoding="utf-8")
        archivos.append(ruta)
    ruta_excel = destino / "base_consolidada.xlsx"
    with pd.ExcelWriter(ruta_excel) as libro:
        for nombre, tabla in hojas.items():
            tabla.to_excel(libro, sheet_name=nombre[:31], index=False)
    archivos.append(ruta_excel)
    return archivos

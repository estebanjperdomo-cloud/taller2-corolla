-- Consultas del paso 2 sobre la base consolidada (datos/oficial/consolidado/corolla.sqlite).
-- Las mismas se ven en la terminal con: python taller.py consultar --modo oficial
-- Se pueden correr con DB Browser for SQLite, con `sqlite3` o desde Python con pandas.read_sql_query.

-- 1. Anuncios únicos encontrados durante el periodo
SELECT COUNT(*) AS anuncios_unicos FROM anuncios;

-- 2. Información más reciente de cada anuncio
SELECT id_anuncio, url, fecha_datos, anio, version, precio, moneda, kilometraje, transmision,
       ciudad, sunroof, disponibilidad_actual
FROM anuncios
ORDER BY precio;

-- 3. Observaciones diarias de un anuncio y los cambios detectados
SELECT fecha, disponibilidad, estado_descarga, fecha_hora_descarga, precio, kilometraje, motivo_error
FROM observaciones
WHERE id_anuncio = 'PEGUE_AQUI_EL_ID'
ORDER BY fecha;

SELECT fecha, campo, valor_anterior, valor_nuevo, fecha_anterior
FROM cambios
ORDER BY fecha, id_anuncio, campo;

-- 4. Primera y última fecha en que se observó cada anuncio
SELECT id_anuncio, primera_fecha_visto, ultima_fecha_visto, dias_encontrado
FROM anuncios
ORDER BY primera_fecha_visto, id_anuncio;

-- 5. Disponibilidad observada y fecha y hora de cada descarga
SELECT id_anuncio, fecha, disponibilidad, estado_descarga, fecha_hora_descarga
FROM observaciones
ORDER BY fecha, id_anuncio;

-- Extra. Bajadas de precio en el periodo
SELECT c.fecha, c.id_anuncio, a.anio, a.version,
       CAST(c.valor_anterior AS REAL) AS precio_antes,
       CAST(c.valor_nuevo AS REAL) AS precio_despues,
       ROUND(100.0 * (CAST(c.valor_nuevo AS REAL) / CAST(c.valor_anterior AS REAL) - 1), 1) AS variacion_pct
FROM cambios c JOIN anuncios a USING (id_anuncio)
WHERE c.campo = 'precio' AND CAST(c.valor_nuevo AS REAL) < CAST(c.valor_anterior AS REAL)
ORDER BY variacion_pct;

-- Extra. Anuncios que podrían ser el mismo vehículo publicado dos veces
SELECT * FROM posibles_duplicados;

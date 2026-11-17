---
name: revisar-dia
description: Revisa cómo le fue hoy al monitor (recolección de las 8:00 y correo de las 11:00) y explica en palabras simples qué funcionó, qué falló y qué hacer. Úsala cuando pregunten si corrió el monitor, si llegó el correo o qué pasó hoy.
---

# Revisar el día

1. Mira la fecha de hoy. Del 16 al 21 de noviembre de 2026 lo importante es el modo `oficial`; antes o después, el modo `prueba`.
2. Corre `python taller.py log`. Muestra los logs de hoy de los dos modos. Fíjate en la línea `ejecucion_completa` (estado general, enlaces, nuevos, descargas, registros) y en la etapa `correo` (`correo_estado`).
3. Lee `datos/<modo>/estado/ejecucion_<AAAA-MM-DD>.json` para ver el estado de cada etapa, el origen (`programado` o `manual`) y los errores.
4. Si el computador es un Mac, corre `python taller.py estado-programacion` para ver si las tareas están cargadas, cuántas veces corrieron, el último código de salida y las últimas líneas de `datos/launchd/*.log`.
5. Responde con máximo seis viñetas.
   * Si la recolección corrió a las 8:00 y si fue programada.
   * Enlaces encontrados, anuncios nuevos y descargas exitosas y fallidas.
   * Si la búsqueda fue completa.
   * Si el correo salió y a qué hora.
   * Errores, explicados en palabras simples.
   * Qué hacer, según la parte 7 de GUIA_PASO_A_PASO.md.
6. No corras comandos con `--modo oficial` ni reenvíes correos sin que los estudiantes lo confirmen. Si hubo una incidencia, propón el texto para anotarla en `docs/incidentes.md`.

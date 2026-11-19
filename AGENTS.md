# Reglas del proyecto para el agente de programación

Este repositorio es el Taller 2 de Programación Aplicada en Python (Uniandes) y lo trabaja una pareja de estudiantes que todavía está aprendiendo Python. Responde siempre en español sencillo y explica el porqué de cada cosa, porque ellos deben poder explicar el código y las decisiones en la sustentación.

## Qué hace el proyecto

Un monitor que todos los días a las 8:00 (hora de Bogotá) busca en Carroya los Toyota Corolla modelo 2022 a 2026, descarga cada anuncio, actualiza una base SQLite y prepara un análisis de precios con posibles gangas. A las 11:00 envía un correo con el resultado y, si no sale, una tercera tarea lo reintenta cada 30 minutos hasta las 23:30 sin repetirlo nunca. Corre del 16 al 21 de noviembre de 2026 en el Mac de uno de los estudiantes, programado con launchd. Desde el 19 de noviembre sigue también el Mazda 3 y el Kia K3 como modelos adicionales (`MODELOS_EXTRA` en `corolla/configuracion.py`), en `datos/modelos/`, después del Corolla y sin tocar sus evidencias. La guía para los estudiantes está en GUIA_PASO_A_PASO.md y las decisiones de diseño en README.md.

## Mapa del código

| Paso del taller | Archivos |
|---|---|
| 1. Enlaces y datos | corolla/paso1_navegador.py, corolla/paso1_extraccion.py, corolla/paso1_recoleccion.py |
| 2. Base consolidada | corolla/paso2_base_de_datos.py, consultas.sql |
| 3. Actualización | corolla/paso3_actualizacion.py |
| 4. Automatización | corolla/paso4_programacion.py y la opción --programado de taller.py |
| 5. Logs | corolla/paso5_bitacora.py, corolla/estado.py |
| 6. Precios y gangas | corolla/paso6_analisis.py, corolla/paso6_grafica.py |
| 7. Correo | corolla/paso7_correo.py, corolla/plantillas/correo.html |
| 8. Entrega | corolla/paso8_entrega.py |
| Orquestación, comandos y avisos del Mac | corolla/flujo.py, taller.py, corolla/avisos.py |
| Pruebas y demostración | corolla/simulacion.py, tests/ |

## Comandos útiles

* `source .venv/bin/activate` antes de cualquier comando de Python (en Windows `.venv\Scripts\activate`).
* `python -m pytest -q` corre todas las pruebas sin internet (con `python -m` se usa el pytest del entorno y no el de Anaconda).
* `python taller.py --help` lista los comandos.
* `python taller.py demo` simula seis días sin internet.
* `python taller.py log` resume los logs de hoy y `python taller.py verificar` revisa la instalación.
* `python taller.py probar-modelos` muestra qué anuncios reconoce en las páginas de los modelos adicionales.

## Reglas

* Nunca escribas contraseñas ni claves en el código, en los commits ni en las respuestas. Las credenciales viven solo en `.env`, que está en `.gitignore`. No muestres el contenido de `.env`.
* No llames directamente a la API interna de Carroya ni inventes encabezados o cambies el user agent. La lectura de Carroya se hace solo con `corolla/paso1_navegador.py`, que abre las páginas públicas en Chromium y lee la respuesta que la propia página recibe.
* No guardes datos personales de los vendedores (nombre, teléfono, correo, dirección, placa). `paso1_extraccion.sanitizar` los quita.
* No modifiques a mano nada dentro de `datos/oficial` ni de `datos/modelos/*/oficial`. Son las evidencias de la entrega.
* Las ejecuciones manuales van en modo prueba, que es el modo por defecto. Usa `--modo oficial` solo para recuperar un día que falló y pide permiso antes.
* No ejecutes `python taller.py programar`, `desprogramar`, `probar-programacion`, comandos con `sudo`, `git push` ni nada que envíe correos sin que los estudiantes lo pidan.
* Después de cualquier cambio en `corolla/` o en `taller.py`, corre `python -m pytest -q` y muestra el resultado.
* Mantén el estilo del código. Nombres en español, funciones cortas y comentarios que explican el porqué.
* Si un cambio afecta una decisión del taller (identificador, almacenamiento, actualización, automatización o detección de gangas), actualiza también README.md y dilo en tu respuesta.
* Del 16 al 21 de noviembre cualquier cambio de código llega a la ejecución del día siguiente. Durante esos días prefiere no cambiar código salvo que haya una falla, y si hay que hacerlo, corre las pruebas antes.

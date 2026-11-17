# Esqueleto del documento de una página

El enunciado pide un documento de máximo una página con el diagrama de arquitectura, el funcionamiento de cada parte y las decisiones principales sobre identificación, almacenamiento, actualización, automatización y detección de gangas. Este esqueleto dice qué poner en cada bloque. Escríbanlo con sus palabras (Antigravity puede ayudar con la skill `preparar-entrega`), péguenlo en Google Docs o Word con el diagrama `docs/arquitectura.png`, revisen que quepa en una página y expórtenlo como `entrega/documento_una_pagina.pdf`.

## Título y autores
Monitor de Toyota Corolla en Carroya, Taller 2, nombres de la pareja y fecha.

## Diagrama
Inserten `docs/arquitectura.png` a todo el ancho de la página.

## Funcionamiento (tres o cuatro frases)
* El Mac corre a las 8:00 la recolección (pasos 1, 3 y 6) y a las 11:00 el correo (paso 7), como dos tareas independientes de launchd.
* El paso 1 abre las páginas públicas de Carroya con Chromium y lee el JSON que la página recibe, recorre todas las páginas y descarga cada ficha.
* Los archivos diarios alimentan la base SQLite, el análisis y el correo. Cada etapa deja una línea de log con hora de Bogotá.

## Decisiones
* Identificación. UUID de Carroya como identificador estable, por qué no la URL completa, y posibles duplicados solo marcados.
* Almacenamiento. SQLite con observaciones por día, cambios y anuncios; una ventaja y una desventaja frente a CSV y frente a Parquet.
* Actualización. procesar_dia en una transacción, huella SHA-256 para la idempotencia, y la diferencia entre encontrado, no encontrado y desconocida.
* Automatización. launchd en el Mac, modo según la fecha, caffeinate, y las condiciones (encendido, con corriente, sesión iniciada, internet, carpeta fuera de Documentos).
* Gangas. Precio esperado por año, kilometraje y grupo de versión; regla de 12 %, z de menos dos y 8 % frente a comparables; manejo de faltantes; una limitación importante.

## Resultados del periodo (una o dos frases)
Anuncios únicos, días completos, correos enviados y gangas encontradas. Si algo falló, qué pasó (ver `docs/incidentes.md`).

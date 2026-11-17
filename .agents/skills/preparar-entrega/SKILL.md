---
name: preparar-entrega
description: Acompaña la preparación del zip para Bloque Neón (paso 8), revisa que no falte nada y que no haya credenciales. Úsala el 22 o 23 de noviembre o cuando pidan armar la entrega.
---

# Preparar la entrega

1. Confirma que el periodo terminó (después del 21 de noviembre de 2026 a las 11:00). Si no, avisa y no sigas.
2. Revisa que existan los seis días en `datos/oficial/diarios` (enlaces y datos del 16 al 21) y la base `datos/oficial/consolidado/corolla.sqlite`.
3. Revisa `entrega/correos_recibidos`. Deben estar los seis correos oficiales exportados con fecha y hora. Si faltan, explica cómo exportarlos (GUIA_PASO_A_PASO.md, parte 6).
4. Revisa que exista `entrega/documento_una_pagina.pdf`. Si no, ayuda a redactarlo a partir de `docs/esqueleto_documento_una_pagina.md` y README.md, en una sola página.
5. Lee `docs/incidentes.md`. Si algún día falló, el documento o el README deben explicarlo.
6. Pide permiso y corre `python taller.py entregar`. Lee la lista de lo que falta y ayuda a resolverlo.
7. Revisa el zip con `unzip -l entrega_taller2_corolla.zip`. No debe aparecer `.env`, ni `.venv`, ni `datos/demo`.
8. Recuerda que el zip se sube a Bloque Neón antes del 23 de noviembre de 2026 a las 11:59 p. m.

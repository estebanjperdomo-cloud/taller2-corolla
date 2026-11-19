# Cambios por versión

Cada versión lista lo que se agregó, lo que cambió y lo que se corrigió. El porqué de cada cambio, las opciones que se descartaron y cómo se comprobó están en [DECISIONES.md](DECISIONES.md).

## Versión 1.1 · 18 de noviembre de 2026

Corre desde el 19 de noviembre. Commits [6e716d0](https://github.com/estebanjperdomo-cloud/taller2-corolla/commit/6e716d06cff59b532908ae59c3cdf7afe84bcd59) y [a0c0105](https://github.com/estebanjperdomo-cloud/taller2-corolla/commit/a0c0105cab21cd2e5696d548d98eaf83eea2bd6d), más el de esta documentación.

### Agregado
* Mazda 3 y Kia K3 2022 a 2026 como modelos adicionales, leídos de sus páginas públicas en Carroya. Cada uno tiene su carpeta en `datos/modelos/` y su propia base (`mazda_3.sqlite` y `kia_k3.sqlite`).
* Sección "Otros modelos monitoreados" al final del correo, con el resumen del día y hasta tres posibles gangas por modelo.
* Comandos `probar-modelos` y `modelos`, y la opción `--solo-corolla` de `recolectar`.
* Tarea `co.uniandes.taller2corolla.reintento`, que intenta el correo cada 30 minutos de 11:30 a 23:30 solo si el del día no ha salido.
* Avisos en la pantalla del Mac cuando empieza y termina la recolección y cuando el correo no pudo salir.
* Niveles de versión de Mazda (Prime, Touring, Grand Touring, Carbon Edition, Signature) y de Kia (GT Line, Zenith, Vibrant, Desire) en el modelo de precios.
* [DECISIONES.md](DECISIONES.md), este archivo y el diagrama del flujo del correo (`docs/flujo_correo.png`).

### Cambiado
* El correo prueba el puerto 587 cuando la red no deja conectar al 465. Un error de contraseña no cambia de puerto.
* La espera de conexión del correo acepta cualquiera de los dos puertos, en lugar de esperar cinco minutos al 465.
* El correo programado no se repite, espera a la recolección si la encuentra corriendo (máximo una hora) y, si arranca antes de las 11:00, envía el de ayer cuando no había salido.
* La recolección deja un candado mientras trabaja, para que el correo sepa que debe esperarla.
* `python taller.py log` muestra también los modelos adicionales.
* El diagrama de arquitectura incluye los modelos adicionales y la tarea de reintento.

### Corregido
* La revisión de si el correo del día ya salió usa la fecha del reporte y no la fecha del nombre del log, que es la del día en que corrió.

### Pruebas
* Pasaron de 72 a 113. Las nuevas cubren los criterios de cada modelo, las carpetas separadas, el cambio al puerto 587, el error de contraseña, los reintentos sin correos repetidos, la espera a la recolección y el correo de ayer.

## Versión 1.0 · 14 de noviembre de 2026

Commit [5db06cd](https://github.com/estebanjperdomo-cloud/taller2-corolla/commit/5db06cd3ce8c5648e1e702ac62a383ead6867750). Corrió el 17 y el 18 de noviembre.

* Recolección diaria del Toyota Corolla 2022 a 2026 en Carroya con Playwright (paso 1).
* Base consolidada en SQLite con una observación por anuncio y día y el registro de cada cambio (pasos 2 y 3).
* Dos tareas de launchd, a las 8:00 y a las 11:00, con el modo según la fecha (paso 4).
* Logs JSONL por etapa con la hora de Bogotá (paso 5).
* Modelo de precios y regla de posibles gangas con una explicación para cada alerta (paso 6).
* Correo diario con gráfica, resumen y gangas, que sale aunque algo falle (paso 7).
* Exportaciones y zip de entrega sin credenciales (paso 8).
* Demostración de seis días sin internet y 72 pruebas automáticas.

# Incidencias del periodo

Anoten aquí cualquier cosa que haya fallado o que hayan hecho a mano entre el 16 y el 21 de noviembre. El enunciado pide explicar lo que ocurrió si alguna ejecución o correo falló.

| Fecha | Qué pasó | Qué hicimos | Evidencia |
|---|---|---|---|
| | | | |
| 16 de noviembre | El monitor todavía no estaba instalado y no corrieron la recolección de las 8:00 ni el correo de las 11:00 | No fue posible recuperar ese día. El sistema se instaló y se probó el 17 | No hay archivos del 16 |
| 17 de noviembre | La instalación terminó después de las 8:00 | La recolección se lanzó con la tarea programada del Mac (launchd) a las 11:53 y el correo hacia las 12:10. Desde el 18 corren solas a las 8:00 y a las 11:00 | datos/oficial/logs, datos/launchd y correo_2026-11-17.pdf |
| 18 de noviembre | La recolección arrancó a las 8:00 pero tardó cerca de dos horas, porque la tapa del Mac se cerró mientras corría y el Mac se durmió. Terminó con 60 anuncios. El correo de las 11:00 no salió (ConnectionRefusedError) porque la red del trabajo bloquea el puerto 465 de Gmail, y un intento a mano a las 13:51 falló por lo mismo | A las 19:23 se envió a mano el correo del 18 por el puerto 587 (`SMTP_PORT=587 python taller.py correo --modo oficial`). Después se agregó el cambio automático al puerto 587, una tarea que reintenta el correo cada 30 minutos sin repetirlo y avisos en el Mac para no cerrar la tapa durante la recolección | datos/oficial/logs (COR-20261118-110005 y COR-20261118-135109 fallidos, COR-20261118-192319 enviado) y datos/launchd/correo.log |

# Guía paso a paso del Taller 2

Esta guía dice qué hacer con el código, en orden, desde instalarlo hasta entregarlo. Está escrita para la pareja. **Persona A** es quien tiene el Mac donde el monitor va a correr todos los días. **Persona B** es el compañero, que trabaja desde su propio computador.

Todo lo que aparece en un recuadro gris es un comando. Se copia, se pega en la Terminal y se oprime Enter. Debajo de cada comando importante está lo que debe salir, para que sepan si funcionó.

## Contenido

* Parte 0. Qué hace cada herramienta y el calendario
* Parte 1. Instalar y probar en el Mac de la Persona A
* Parte 2. Subir a GitHub, invitar al compañero y abrir el proyecto en Antigravity
* Parte 3. Programar la ejecución diaria (paso 4) y la prueba del domingo
* Parte 4. Rutina diaria del 16 al 21 de noviembre
* Parte 5. Entender el código, paso por paso del taller
* Parte 6. Entrega en Bloque Neón
* Parte 7. Problemas frecuentes

## Parte 0. Qué hace cada herramienta y el calendario

* **Claude** escribió la primera versión del código.
* **Antigravity** es el agente de programación (coding agent) con el que ustedes revisan, corren, explican y ajustan el código. El enunciado pide usar un coding agent, revisar lo que genera, comprobar que funciona y poder explicar las decisiones, y la parte 5 de esta guía trae las preguntas para hacerle en cada paso. Es gratis con una cuenta personal de Google, con un límite semanal de uso.
* **El Mac de la Persona A** ejecuta el programa solo, todos los días a las 8:00 y a las 11:00, con launchd, el programador de tareas que trae macOS. Antigravity no sirve para esto, porque un agente solo trabaja cuando alguien le escribe y el monitor tiene que correr aunque nadie esté frente al computador.
* **GitHub** guarda el código para los dos.

Sobre cuál agente usar, Antigravity está bien para este taller y no cuesta. Claude Code o Cursor también sirven (Claude Code lee las mismas reglas gracias al archivo `CLAUDE.md`), aunque Claude Code necesita un plan pago de Claude. Lo que no conviene es meter un modelo de IA dentro del proceso diario, porque agrega costo y una forma más de fallar a algo que debe correr solo seis días seguidos, y porque una regla estadística se explica mejor en la sustentación que la opinión de un modelo.

### Calendario

| Cuándo | Qué | Quién |
|---|---|---|
| Sábado 14 en la noche o domingo 15 antes de las 8:00 | Partes 1, 2 y 3 | Persona A, y la Persona B clona el repositorio |
| Domingo 15, 8:00 y 11:00 | El Mac corre solo una prueba completa, marcada como PRUEBA | El Mac |
| Domingo 15 después de las 11:00 | Revisar la prueba (parte 3.5) | Los dos |
| Lunes 16 a sábado 21 | Ejecución oficial y revisión diaria (parte 4) | El Mac, y los dos revisan |
| Domingo 22 | Quitar la programación, exportar correos, documento y zip (parte 6) | Los dos |
| Lunes 23 antes de las 11:59 p. m. | Subir el zip a Bloque Neón | Cualquiera de los dos |

Si no alcanzan a dejar todo listo antes del domingo a las 8:00, no pasa nada grave. Hacen la parte 3.4 el domingo y esa es su prueba completa. Lo único que no se puede mover es que el Mac esté listo el lunes 16 antes de las 8:00.

## Parte 1. Instalar y probar en el Mac de la Persona A

### 1.1 Abrir la Terminal

Oprima Cmd y Espacio, escriba Terminal y oprima Enter. Cuando un comando empiece con `sudo`, la Terminal pide la contraseña del Mac. Al escribirla no se ve nada; es normal, escríbala y oprima Enter.

### 1.2 Instalar Homebrew, Python, Git y GitHub CLI

Revise primero si ya tiene Homebrew.

```bash
brew --version
```

Si sale `command not found`, instálelo. Tarda unos minutos y pide la contraseña del Mac.

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Al final Homebrew muestra unas líneas bajo **Next steps**. En los Mac con chip Apple (M1, M2, M3 o M4) son estas dos, que dejan `brew` disponible siempre.

```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

Ahora instale Python 3.12, Git y la herramienta de GitHub.

```bash
brew install python@3.12 git gh
python3.12 --version
```

Debe salir `Python 3.12.` seguido de un número.

### 1.3 Poner el proyecto en la carpeta personal

El proyecto **no puede quedar** en Documentos, Escritorio ni Descargas, porque macOS no deja que las tareas programadas lean esas carpetas y el monitor fallaría a las 8:00 sin avisar. Va en la carpeta personal, como `~/taller2-corolla`.

Si el zip quedó en Descargas sin descomprimir, ejecute esto.

```bash
cd ~
unzip -q ~/Downloads/taller2-corolla.zip -d ~
```

Si el navegador ya lo descomprimió y en Descargas hay una carpeta `taller2-corolla`, muévala.

```bash
mv ~/Downloads/taller2-corolla ~/
```

Revise que quedó bien.

```bash
cd ~/taller2-corolla
ls
```

Debe salir algo así.

```
AGENTS.md  CLAUDE.md  GUIA_PASO_A_PASO.md  README.md  consultas.sql  corolla  docs  requirements.txt  taller.py  tests
```

### 1.4 Crear el entorno virtual e instalar las librerías

El entorno virtual (`.venv`) es una carpeta con un Python propio del proyecto y sus librerías, para no mezclarlas con las de otros proyectos.

```bash
cd ~/taller2-corolla
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

El último comando descarga Chromium, el navegador que usa el programa (unos 150 MB). Desde ahora la línea de la Terminal empieza con `(.venv)`. **Cada vez que abran una Terminal nueva** hay que entrar a la carpeta y activar el entorno.

```bash
cd ~/taller2-corolla && source .venv/bin/activate
```

### 1.5 Correr las pruebas automáticas

```bash
pytest -q
```

Debe terminar con `72 passed`. Las pruebas no usan internet ni envían correos. Usan un Carroya simulado con la misma forma de datos que el real y, en una de ellas, levantan un Carroya de mentira en el propio Mac para probar el navegador de verdad.

### 1.6 Ver la demostración

La demostración simula los seis días del periodo, sin internet, para que vean qué produce el programa antes de usarlo de verdad.

```bash
python taller.py demo
```

Debe salir una línea por día, por ejemplo `2026-11-16 · recolección completada · 62 enlaces · 62 nuevos · 2 gangas nuevas`. Abra el correo simulado del primer día y el del tercero, que tuvo una página que no cargó.

```bash
open datos/demo/correos/2026-11-16/*.html
open datos/demo/correos/2026-11-18/*.html
```

Fíjense en el estado general, la tabla de ejecución, la gráfica y las explicaciones de las gangas. Eso mismo llegará a su correo cada día a las 11:00.

### 1.7 Configurar el correo

El programa envía el correo desde una cuenta de Gmail con una **contraseña de aplicación**, que es distinta de la contraseña normal. Usen una cuenta personal de Gmail; las cuentas de la universidad a veces no permiten crear contraseñas de aplicación.

* Entren a https://myaccount.google.com/security y activen la **Verificación en dos pasos** si no está activa.
* Entren a https://myaccount.google.com/apppasswords, escriban un nombre como `taller2 corolla` y opriman Crear.
* Google muestra 16 letras en cuatro grupos. Cópienlas; no se vuelven a mostrar.

Ahora creen el archivo `.env` a partir de la plantilla y ábranlo.

```bash
cp .env.example .env
open -e .env
```

Llenen tres valores y guarden con Cmd S.

* `SMTP_USER` es la cuenta de Gmail que envía.
* `SMTP_PASSWORD` son las 16 letras (los espacios no importan).
* `EMAIL_TO` son los correos de los dos, separados por una coma y sin espacios.

El archivo `.env` nunca se sube a GitHub ni entra en la entrega, porque está en `.gitignore`. Comprueben que el correo funciona.

```bash
python taller.py probar-correo
```

Debe salir `Correo de prueba enviado: a ... en el intento 1` y llegar un correo con asunto `[PRUEBA] Monitor Corolla · prueba de envío`. Si no aparece, revisen la carpeta de spam y márquenlo como no spam.

### 1.8 Primera recolección real, un paso del taller a la vez

Estos comandos corren cada paso por separado, en **modo prueba**. Todo queda en `datos/prueba` y los correos llevan `[PRUEBA]` en el asunto, así nunca se mezclan con las evidencias oficiales del 16 al 21.

**Paso 1, versión corta.** Descarga solo cinco anuncios, para ver en un minuto los tres estados que pide el taller.

```bash
python taller.py paso1 --max-anuncios 5
```

Al final debe salir algo como esto (los números dependen del día).

```
Paso 1 en modo prueba. Carroya reporta 60 anuncios en 3 páginas; se leyeron 3.
Búsqueda completa: sí
Enlaces que cumplen los criterios: 60 (60 nuevos para el sistema, 0 descartados por no cumplir).
Descargas: {'sin intentar': 55, 'descargado': 5, 'fallido': 0}
```

Abran la carpeta y miren los dos archivos del día con Numbers o Excel.

```bash
open datos/prueba/diarios/
```

En `enlaces_<fecha>.csv` y `datos_<fecha>.csv` hay 5 filas `descargado` y 55 `sin intentar`, y estas últimas tienen vacía la hora del intento. Así se ve la consistencia entre los dos archivos que evalúa el taller.

**Paso 1 completo.** Ahora la búsqueda y la descarga de todos los anuncios. Tarda entre 5 y 10 minutos porque abre las fichas una por una, con pausas para no cargar el sitio.

```bash
python taller.py paso1
```

Durante la ejecución salen líneas como `Página 2: 20 anuncios sin repetir (van 40 de 60 que reporta Carroya).` y `Descargados 30 de 60 anuncios.`. Al final, `Búsqueda completa: sí` y casi todas las descargas en `descargado`. Los archivos de la versión corta no se borran, quedan en `datos/prueba/diarios/reemplazados/`.

Si sale `Búsqueda completa: no` porque no se pudo leer la primera página, prueben con la ventana del navegador visible y vean qué muestra Carroya.

```bash
python taller.py paso1 --visible
```

Si con la ventana visible sí funciona, pongan `NAVEGADOR_VISIBLE=1` en el `.env`. El programa ya intenta solo con la ventana visible cuando falla la primera página, pero así se ahorra el primer intento.

**Paso 3.** Procesa los archivos del día en la base consolidada.

```bash
python taller.py paso3
```

Sale un resumen con `"registros_agregados": 60`, `"anuncios_unicos": 60` y `"ya_procesado": false`. **Córranlo otra vez.** Ahora dice `"ya_procesado": true` y nada cambia. Eso es la idempotencia que pide el paso 3.

**Paso 2.** Las consultas que pide el diseño de la base.

```bash
python taller.py consultar
```

Salen seis tablas, una por cada pregunta del enunciado (anuncios únicos, información más reciente, observaciones, cambios, primera y última fecha, disponibilidad y hora de cada descarga). El primer día la tabla de cambios está vacía, porque no hay con qué comparar.

**Paso 6.** Distribución de precios y posibles gangas.

```bash
python taller.py paso6
open datos/prueba/reportes/$(date +%F)/*.png
```

Sale la cantidad de precios válidos con la mediana y los cuartiles, las posibles gangas con su explicación y la gráfica. Puede que hoy no haya ninguna ganga. Eso también es un resultado válido y el correo lo dice.

**Paso 7.** Arma y envía el correo.

```bash
python taller.py paso7
```

Debe llegar un correo con asunto `[PRUEBA] Corolla 2022 a 2026 · <fecha> · ...` con todo lo del día.

**Paso 5.** El resumen de los logs de hoy.

```bash
python taller.py log
```

Sale una línea por etapa (busqueda, descarga, consolidacion, analisis, ejecucion_completa y correo) con su hora, estado, duración y métricas.

### 1.9 Revisión general

```bash
python taller.py verificar
```

Todo debe salir `[OK]`, salvo los avisos de la programación y de la energía del Mac, que se arreglan en la parte 3.

## Parte 2. Subir a GitHub, invitar al compañero y abrir el proyecto en Antigravity

### 2.1 Persona A crea el repositorio privado y sube el código

Si nunca han usado Git en este Mac, configuren su nombre y el correo de su cuenta de GitHub.

```bash
git config --global user.name "Nombre Apellido"
git config --global user.email "correo_de_su_cuenta_de_github@ejemplo.com"
```

Inicien sesión en GitHub desde la Terminal. Escojan GitHub.com, HTTPS, Yes y Login with a web browser; copien el código que aparece y péguenlo en la página que se abre.

```bash
gh auth login
```

Creen el repositorio local y revisen qué se va a subir.

```bash
cd ~/taller2-corolla
git init -b main
git add .
git status
```

En la lista **no deben aparecer** `.env`, `.venv` ni `datos`. Si aparecen, no sigan y revisen que el archivo `.gitignore` esté en la carpeta. Si todo está bien, hagan el primer commit y suban el repositorio como privado.

```bash
git commit -m "Código inicial del monitor de Corolla"
gh repo create taller2-corolla --private --source=. --remote=origin --push
```

Al final sale la dirección del repositorio, algo como `https://github.com/usuario_a/taller2-corolla`.

### 2.2 Invitar al compañero

Cambien `USUARIO_DE_B` por el usuario de GitHub del compañero.

```bash
gh api -X PUT "repos/{owner}/{repo}/collaborators/USUARIO_DE_B" -f permission=push
```

También se puede desde la página del repositorio en Settings, Collaborators, Add people.

### 2.3 Persona B clona el proyecto en su computador

La Persona B acepta la invitación (llega por correo o aparece en https://github.com/notifications). Luego, en un Mac y después de instalar lo de la parte 1.2, ejecuten estos comandos.

```bash
cd ~
gh repo clone USUARIO_DE_A/taller2-corolla
cd taller2-corolla
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
pytest -q
python taller.py demo
```

En Windows, con Python 3.12 y Git instalados desde python.org y git-scm.com, los comandos van en PowerShell. Allí las pruebas que dependen del Mac aparecen como `skipped`, y eso es normal.

```powershell
git clone https://github.com/USUARIO_DE_A/taller2-corolla.git
cd taller2-corolla
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
pytest -q
python taller.py demo
```

La Persona B no programa nada en su computador. La ejecución diaria ocurre solo en el Mac de la Persona A.

### 2.4 Cómo trabajar los dos sin pisarse

* Antes de empezar a trabajar, `git pull` para traer lo último.
* Después de un cambio, `pytest -q` y luego `git add -A`, `git commit -m "Paso 6, explica mejor la referencia"` y `git push`.
* Si la Persona B cambia código durante el periodo, la Persona A hace `git pull` en el Mac y la siguiente ejecución usa el código nuevo. Por eso, del 16 al 21 solo se cambia código si algo falla.
* Reparto sugerido. La Persona A se encarga del Mac, de la ejecución diaria y de los pasos 1 y 4. La Persona B revisa con Antigravity los pasos 2, 3 y 6, exporta los correos y arma el documento de una página. Los dos deben poder explicar todo.

### 2.5 Abrir el proyecto en Antigravity

* Descarguen Antigravity desde https://antigravity.google e inicien sesión con su cuenta de Google.
* Abran la carpeta del proyecto (`~/taller2-corolla` en el Mac).
* Antigravity lee automáticamente el archivo `AGENTS.md`, que le explica el proyecto y le pone reglas (no tocar las credenciales, no modificar `datos/oficial`, correr las pruebas después de cada cambio, no ejecutar comandos delicados sin permiso).
* En `.agents/skills` hay tres habilidades del proyecto. `revisar-dia` revisa cómo le fue al monitor hoy, `explicar-paso` explica el código de un paso y prepara preguntas de sustentación, y `preparar-entrega` acompaña el paso 8. Se usan escribiendo `/revisar-dia` en el chat del agente o pidiéndole que use esa habilidad.
* Configuren el agente para que pida permiso antes de ejecutar comandos en la Terminal, y lean lo que propone antes de aceptarlo.

Una buena primera pregunta para Antigravity es esta.

> Lee AGENTS.md y README.md y explícame en diez viñetas cómo funciona este proyecto, qué archivo corresponde a cada paso del taller y qué pasa cada día a las 8:00 y a las 11:00.

## Parte 3. Programar la ejecución diaria (paso 4) y la prueba del domingo

### 3.1 Dejar el Mac listo para trabajar solo

Primero anoten cómo está configurada la energía, para dejarla igual el 22. Tomen una foto de la pantalla con Cmd Shift 4 o copien el texto.

```bash
pmset -g custom
```

Eviten que el Mac entre en reposo cuando está conectado al cargador.

```bash
sudo pmset -c sleep 0
```

Programen que se despierte solo todos los días a las 7:55, por si acaso.

```bash
sudo pmset repeat wakeorpoweron MTWRFSU 07:55:00
pmset -g sched
```

Debe salir una línea como `wakepoweron at 7:55AM every day`.

Además, durante toda la semana, cuiden esto.

* El Mac conectado a la corriente y, si es un portátil, **con la tapa abierta**. Con la tapa cerrada se duerme aunque esté conectado.
* La sesión iniciada. Pueden bloquear la pantalla con Ctrl Cmd Q, pero no cierren sesión ni apaguen el Mac.
* Wifi encendido.
* Las actualizaciones automáticas de macOS apagadas, para que no reinicie el Mac de noche. Están en Ajustes del Sistema, General, Actualización de software, en el botón de información junto a Actualizaciones automáticas.

### 3.2 Crear las tres tareas

```bash
cd ~/taller2-corolla && source .venv/bin/activate
python taller.py programar
```

Debe salir esto.

```
Tarea co.uniandes.taller2corolla.recoleccion cargada. Corre todos los días (08:00, hora del Mac) el comando 'recolectar --programado'.
Tarea co.uniandes.taller2corolla.correo cargada. Corre todos los días (11:00, hora del Mac) el comando 'correo --programado'.
Tarea co.uniandes.taller2corolla.reintento cargada. Corre todos los días (cada 30 min de 11:30 a 23:30, hora del Mac) el comando 'correo --programado'.
------------------------------------------------------------------------
Próximas ejecuciones:
  * domingo 15 de noviembre de 2026 a las 08:00, recolectar en modo prueba
  * domingo 15 de noviembre de 2026 a las 11:00, correo en modo prueba
  * lunes 16 de noviembre de 2026 a las 08:00, recolectar en modo oficial
  * lunes 16 de noviembre de 2026 a las 11:00, correo en modo oficial
Revise con: python taller.py estado-programacion
```

Fíjense en que el domingo corre en modo prueba y desde el lunes en modo oficial. Eso lo decide la fecha, no hay que cambiar nada el lunes. Después del 21 las tareas no hacen nada.

La tercera tarea, `reintento`, se agregó el 18 de noviembre. Vuelve a intentar el correo cada 30 minutos, pero solo lo envía si el del día todavía no ha salido, así que nunca llegan dos correos del mismo día.

macOS puede mostrar un aviso de que se agregaron ítems en segundo plano. Es normal. **No los desactiven** en Ajustes del Sistema, General, Ítems de inicio (en algunas versiones se llama Ítems de inicio y extensiones), porque entonces las tareas no corren.

### 3.3 Revisar las tareas

```bash
python taller.py estado-programacion
```

Las tres tareas deben decir `cargada=sí`. Hasta que corran por primera vez, `veces ejecutada` sale en 0.

### 3.4 Probar la programación ya mismo

Este comando le pide a launchd que corra la tarea de las 8:00 en este momento, exactamente como lo hará cada mañana. Como hoy es antes del 16, corre en modo prueba.

```bash
python taller.py probar-programacion recolectar
```

Para ver lo que va haciendo, usen este comando en la misma Terminal. Con Ctrl C dejan de mirar y la tarea sigue.

```bash
tail -f datos/launchd/recoleccion.log
```

Cuando termine (unos 20 minutos, porque después del Corolla recorre los modelos adicionales), revisen.

```bash
python taller.py estado-programacion
python taller.py log
```

`último código de salida=0` significa que terminó bien. En el log aparece una ejecución `PRUEBA-REC-...` con la etapa `ejecucion_completa`. Luego prueben la tarea del correo.

```bash
python taller.py probar-programacion correo
```

Debe llegar un correo `[PRUEBA]` y en su tabla de ejecución la fila **Cómo se inició** debe decir `automática, programada en el Mac (launchd)`.

### 3.5 La prueba completa del domingo 15

El enunciado pide una prueba completa antes del 16. Si dejaron todo listo el sábado, el domingo el Mac corre solo la recolección a las 8:00 y el correo a las 11:00, los dos en modo prueba. Después de las 11:00 revisen.

* Que llegó el correo `[PRUEBA]` del domingo.
* `python taller.py log --fecha 2026-11-15` muestra la recolección y el correo del domingo.
* `python taller.py estado-programacion` muestra `veces ejecutada` mayor que cero.

Guarden ese correo como PDF en `entrega/correos_prueba/` (cómo se hace está en la parte 6.1). Es la evidencia de la prueba y queda separada de los correos oficiales.

## Parte 4. Rutina diaria del 16 al 21 de noviembre

### Cada día

* **Antes de dormir.** Mac conectado, tapa abierta, sesión iniciada y wifi encendido.
* **En la mañana, si se llevan el Mac.** A las 8:00 sale el aviso "Empezó la recolección del día". No cierren la tapa hasta que salga el aviso "Terminó la recolección... Ya puedes cerrar la tapa" (puede tardar media hora). Con la tapa cerrada el Mac se duerme y la recolección se detiene hasta que lo abran.
* **A las 8:30 o cuando puedan.** La Persona A revisa con los comandos de abajo que la recolección corrió. Debe aparecer una ejecución `REC-<fecha>-08...` con la etapa `ejecucion_completa` en `ok` o `con_advertencias`. También pueden escribir `/revisar-dia` en Antigravity.
* **A las 11:10.** Los dos revisan que llegó el correo (sin `[PRUEBA]` en el asunto). Si a las 11:00 el Mac estaba cerrado o la red no dejó enviar, el correo sale solo apenas el Mac esté abierto y con una red que lo permita, en el siguiente reintento (cada 30 minutos, hasta las 23:30). Ese mismo día lo exportan como PDF a `entrega/correos_recibidos/correo_2026-11-DD.pdf` (parte 6.1), así al final no hay que buscarlos. Esa carpeta no se sube a GitHub porque los correos tienen sus direcciones, y llega a Bloque Neón dentro del zip.
* **Si algo falló**, sigan la tabla y anoten lo que pasó en `docs/incidentes.md`.

```bash
cd ~/taller2-corolla && source .venv/bin/activate
python taller.py log --modo oficial
```

### Qué hacer si algo falla

| Lo que ven | Qué hacer |
|---|---|
| A las 8:30 no hay ninguna ejecución del día | El Mac estaba dormido o apagado. Enciéndanlo e inicien sesión. Si estaba dormido, launchd corre la tarea apenas despierta. Si a las 9:30 sigue sin correr, ejecútenla a mano con `python taller.py recolectar --modo oficial` y anótenlo. |
| `ejecucion_completa` en `error` y el error dice que no se pudo leer la primera página | Revisen el wifi y abran carroya.com en el navegador. Prueben `python taller.py paso1 --visible`. Si funciona con la ventana visible, pongan `NAVEGADOR_VISIBLE=1` en el `.env` y repitan con `python taller.py recolectar --modo oficial` antes de las 11:00. Los archivos del intento fallido quedan en `diarios/reemplazados/`. |
| Algunas descargas fallidas o búsqueda incompleta | Puede pasar. Queda registrado y el correo lo explica. No repitan el día salvo que haya fallado la mayoría de los anuncios. |
| No llegó el correo a las 11:10 | Revisen spam. Si el Mac estuvo cerrado o en una red que bloquea el correo, ábranlo en otra red (la de la casa sirve) y esperen el siguiente reintento, o láncenlo ya con `python taller.py probar-programacion reintento`. Si `python taller.py log --modo oficial` dice `SMTPAuthenticationError`, el problema es la contraseña del `.env`, no la red. |
| A las 11:00 la recolección seguía en curso | El correo programado la espera hasta una hora y sale cuando termina. Si después de una hora sigue corriendo, el correo sale igual y lo dice. No hay que hacer nada. |
| Salió el aviso "No se pudo enviar el correo" | No hay que hacer nada si después van a estar en una red que deje enviar. El Mac lo intenta solo cada 30 minutos hasta que salga. |
| `datos/launchd/recoleccion.log` dice `Operation not permitted` | El proyecto quedó dentro de Documentos, Escritorio o Descargas. Vean la parte 7. |
| `estado-programacion` dice `cargada=no` | Ejecuten `python taller.py programar` otra vez. |

No modifiquen a mano nada dentro de `datos/oficial`. Son las evidencias de la entrega.

### Modelos adicionales (desde el 19)

Desde el 19 de noviembre la recolección de las 8:00 sigue también el Mazda 3 y el Kia K3, después del Corolla y con el mismo método. Quedan en `datos/modelos/` y aparecen al final del correo, en la sección Otros modelos monitoreados. El Corolla sigue siendo lo oficial del taller y si un modelo adicional falla no lo afecta. Para revisar que Carroya se lee bien, usen este comando.

```bash
python taller.py probar-modelos
```

Debe decir `SÍ` junto a Mazda 3 y junto a KIA K3 y terminar con `Todo bien.`

## Parte 5. Entender el código, paso por paso del taller

Para cada paso está lo que pide el enunciado, dónde está el código, cómo funciona, cómo correrlo solo, qué revisar y qué preguntarle a Antigravity. La explicación completa de las decisiones está en `README.md`.

### Paso 1. Recolectar los enlaces y descargar los datos (20 %)

* **Qué pide.** Recorrer todas las páginas de la búsqueda, verificar los criterios (Toyota, Corolla, 2022 a 2026) y guardar cada día un archivo de enlaces y uno de datos con los estados `sin intentar`, `descargado` y `fallido`, sin inventar datos faltantes.
* **Dónde está.** `corolla/paso1_navegador.py`, `corolla/paso1_extraccion.py` y `corolla/paso1_recoleccion.py`.
* **Cómo funciona.** Carroya es una aplicación de JavaScript; el HTML llega sin anuncios y es la página la que los pide en JSON. `NavegadorCarroya` abre las páginas públicas en Chromium y se queda con ese JSON (`obtener_busqueda` y `obtener_detalle`). `buscar_enlaces` lee la página 1 para saber cuántas hay, recorre todas, reintenta las que fallan y hace una segunda pasada si vio menos anuncios de los que Carroya reporta. Cada anuncio pasa por `verificar_criterios` y un Corolla Cross queda descartado. `descargar_anuncios` abre cada ficha con hasta tres intentos y `campos_detalle` saca los campos; lo que no aparece queda vacío (`numero_o_nada` devuelve vacío, nunca cero). `detectar_sunroof` devuelve sí, no o vacío. `sanitizar` quita los datos del vendedor antes de guardar las respuestas originales.
* **Córranlo solo.** `python taller.py paso1 --max-anuncios 5` y luego `python taller.py paso1`.
* **Qué revisar.** Que los dos CSV tengan las mismas filas y los mismos estados, que los `sin intentar` tengan la hora vacía y que el manifiesto diga `"busqueda_completa": true`.
* **Pregúntenle a Antigravity.** "Lee corolla/paso1_recoleccion.py y explícame en español sencillo qué hace buscar_enlaces, por qué hace una segunda pasada y qué pasa si falla la página 2. Muéstrame en el CSV de hoy un ejemplo de cada estado."
* **Prepárense para explicar.** Por qué un navegador y no requests, cómo saben que vieron todas las páginas, qué pasa con un dato que no aparece y por qué no se guardan datos del vendedor.

### Paso 2. Diseñar la base de datos consolidada (15 %)

* **Qué pide.** Poder consultar los anuncios únicos, su información más reciente, las observaciones diarias y los cambios, la primera y la última fecha en que se vio cada uno y su disponibilidad con la hora de cada descarga. Un identificador estable y la justificación frente a otras dos alternativas.
* **Dónde está.** `corolla/paso2_base_de_datos.py` (las tablas están en `ESQUEMA`) y `consultas.sql`.
* **Cómo funciona.** SQLite en un solo archivo. `observaciones` tiene una fila por anuncio y día (llave `id_anuncio` más `fecha`), `cambios` una fila por campo que cambió y `anuncios` una fila por anuncio único, que se reconstruye siempre desde `observaciones` con la consulta `SQL_RECONSTRUIR_ANUNCIOS`. El identificador es el UUID que Carroya pone al final de la URL de cada ficha.
* **Córranlo solo.** `python taller.py consultar`, o `python taller.py consultar --id <un id_anuncio>` para seguir un solo anuncio.
* **Qué revisar.** Que el número de anuncios únicos no crezca cuando el mismo anuncio aparece otro día.
* **Pregúntenle a Antigravity.** "Con corolla/paso2_base_de_datos.py dibújame las tablas y sus llaves y explícame por qué la llave de observaciones es id_anuncio más fecha y por qué no usamos la URL completa como identificador."
* **Prepárense para explicar.** Por qué SQLite y no CSV o Parquet, cómo se reconoce un posible duplicado y por qué solo se marca.

### Paso 3. Implementar las funciones de actualización (10 %)

* **Qué pide.** Funciones que reciban los archivos diarios y actualicen la base, sin duplicar al procesar dos veces el mismo archivo, distinguiendo encontrado, no encontrado en una búsqueda completa y disponibilidad desconocida por un error.
* **Dónde está.** `corolla/paso3_actualizacion.py`, función `procesar_dia`.
* **Cómo funciona.** Calcula la huella SHA-256 de los archivos del día; si ya la tiene registrada, no hace nada. Si no, en una sola transacción borra las observaciones de ese día, inserta una por cada anuncio encontrado, agrega como `no_encontrado` (búsqueda completa) o `desconocida` (búsqueda con errores) los anuncios conocidos que no aparecieron, recalcula los cambios, reconstruye `anuncios`, marca posibles duplicados y guarda la huella. Un anuncio encontrado cuya descarga falló queda `encontrado` sin datos ese día.
* **Córranlo solo.** `python taller.py paso3` dos veces seguidas. La segunda dice `"ya_procesado": true`. `python taller.py reconstruir` borra la base y la rehace desde los archivos diarios con los mismos números.
* **Pregúntenle a Antigravity.** "Explícame procesar_dia por partes y muéstrame con un ejemplo qué pasa si proceso dos veces el mismo archivo y qué pasa si un anuncio no aparece en una búsqueda incompleta."
* **Prepárense para explicar.** Por qué un fallo de descarga no significa que el carro se vendió y por qué las métricas se calculan desde la base y no con contadores.

### Paso 4. Automatizar la ejecución diaria (10 %)

* **Qué pide.** Inicio automático a las 8:00 con búsqueda, descarga, consolidación y preparación del análisis, el correo programado aparte a las 11:00, las condiciones para que funcione y una prueba completa antes del 16.
* **Dónde está.** `corolla/paso4_programacion.py`, la opción `--programado` de `taller.py` y `modo_programado` en `corolla/configuracion.py`.
* **Cómo funciona.** `instalar` escribe tres archivos `.plist` en `~/Library/LaunchAgents` y los carga con `launchctl`. Cada uno ejecuta `caffeinate -i -s .venv/bin/python taller.py recolectar|correo --programado` con rutas absolutas. El tercero es el reintento del correo, cada 30 minutos de 11:30 a 23:30, que solo envía si el correo del día no ha salido (`correo_ya_enviado` en `corolla/paso7_correo.py`). `modo_programado` decide por la fecha (prueba antes del 16, oficial del 16 al 21, nada después). Al empezar, el programa espera hasta diez minutos a que haya internet (`esperar_conexion`).
* **Córranlo solo.** `python taller.py programar`, `python taller.py estado-programacion` y `python taller.py probar-programacion recolectar`.
* **Qué revisar.** `datos/launchd/*.log`, la palabra `programado` en el log y la fila Cómo se inició del correo. Son la evidencia de las ejecuciones programadas.
* **Pregúntenle a Antigravity.** "Explícame corolla/paso4_programacion.py, qué es launchd, qué hace caffeinate y qué condiciones necesita el Mac para que las tareas corran."
* **Prepárense para explicar.** Las condiciones (encendido, con corriente, sesión iniciada, sin reposo, internet, carpeta fuera de Documentos) y por qué escogieron el Mac propio.

### Paso 5. Registrar el funcionamiento del workflow (10 %)

* **Qué pide.** Logs de cada etapa con identificador de ejecución, inicio, fin, duración, estado, enlaces, nuevos, descargas, registros, anuncios únicos, tamaño de la base, errores y estado del correo, en una zona horaria explícita.
* **Dónde está.** `corolla/paso5_bitacora.py` (la clase `Bitacora` y su método `etapa`) y `corolla/estado.py`.
* **Cómo funciona.** Cada etapa se envuelve en `with bitacora.etapa("nombre")`, que mide el tiempo, atrapa los errores sin detener el flujo y escribe una línea JSON en `datos/<modo>/logs/<run_id>.jsonl`. Los mensajes legibles van a `workflow.log`. Todas las horas llevan `-05:00`.
* **Córranlo solo.** `python taller.py log` y `python taller.py exportar`.
* **Pregúntenle a Antigravity.** "Toma el log de hoy y reconstruye qué pasó en la recolección, etapa por etapa, con sus horas y sus números."
* **Prepárense para explicar.** Por qué un archivo por ejecución y por qué la etapa sigue aunque una falle.

### Paso 6. Analizar los precios y detectar posibles gangas (20 %)

* **Qué pide.** Distribución diaria con una observación por anuncio, gráfica, cantidad, mediana y cuartiles, y un método para detectar precios anormalmente bajos que considere las características del carro, con una explicación comprensible para cada alerta.
* **Dónde está.** `corolla/paso6_analisis.py` y `corolla/paso6_grafica.py`.
* **Cómo funciona.** `cargar_dia` toma los anuncios descargados ese día. `motivo_precio_invalido` aparta los precios vacíos, en otra moneda o fuera de 20 a 400 millones. `evaluar` estima un precio esperado con una regresión del logaritmo del precio contra año, kilometraje y grupo de versión, ajustada dos veces para que los extremos no muevan la referencia. `clasificar` marca posible ganga cuando el precio está 12 % o más por debajo del esperado, la diferencia es inusual (z robusto de menos dos o menor) y hay al menos tres comparables con una mediana 8 % mayor. `explicar` escribe la explicación en palabras.
* **Córranlo solo.** `python taller.py paso6`. Las tablas quedan en `datos/prueba/reportes/<fecha>/`.
* **Pregúntenle a Antigravity.** "Toma una fila de analisis_<fecha>.csv y explícame paso a paso cómo se calculó su precio esperado, su puntaje z y su clasificación."
* **Prepárense para explicar.** Qué características usan y por qué, contra qué comparan, la regla, cómo manejan faltantes y pocos comparables, y las limitaciones.

### Paso 7. Crear y enviar el correo diario (5 %)

* **Qué pide.** Correo a las 11:00 con fecha y estado, enlaces, nuevos, descargas, errores y etapas pendientes, gráfica y resumen, y las gangas nuevas con enlace, características, precio, referencia y explicación. Debe salir aunque algo falle.
* **Dónde está.** `corolla/paso7_correo.py` y `corolla/plantillas/correo.html`.
* **Cómo funciona.** `reunir` junta lo que exista a esa hora (estado del día, manifiesto y resumen del análisis), `construir` llena la plantilla y pega la gráfica, `enviar` lo manda por Gmail con tres intentos, por el puerto 465 o, si la red lo bloquea, por el 587, y `guardar_copia` deja una copia. Si el armado falla, `mensaje_minimo` envía una versión corta con el error.
* **Córranlo solo.** `python taller.py paso7 --sin-enviar` arma el correo sin enviarlo y dice cómo abrir la copia.
* **Pregúntenle a Antigravity.** "Muéstrame qué dice el correo cuando la recolección sigue en curso a las 11:00 y dónde está ese caso en el código."

### Paso 8. Entregar los resultados en Bloque Neón (10 %)

* **Dónde está.** `corolla/paso8_entrega.py`.
* **Cómo funciona.** `python taller.py entregar` exporta la base y el log consolidado, copia las tareas de launchd, revisa que la contraseña del correo no aparezca en ningún archivo, arma el zip sin `.env`, sin `.venv` y sin la demostración, y lista lo que falta. Ver la parte 6.

## Parte 6. Entrega en Bloque Neón

### 6.1 Exportar los correos recibidos

En Gmail, en el navegador, abran el correo de cada día, opriman los tres puntos junto a Responder, escojan Imprimir y en el cuadro de impresión escojan Guardar como PDF. El PDF conserva la fecha y la hora del correo. Guárdenlos con estos nombres en `~/taller2-corolla/entrega/correos_recibidos/`. El 16 no tiene correo porque ese día el monitor no estaba instalado, y está contado en `docs/incidentes.md`.

```
correo_2026-11-17.pdf  correo_2026-11-18.pdf  correo_2026-11-19.pdf
correo_2026-11-20.pdf  correo_2026-11-21.pdf
```

### 6.2 Quitar la programación y devolver la energía como estaba (domingo 22)

```bash
cd ~/taller2-corolla && source .venv/bin/activate
python taller.py desprogramar
sudo pmset repeat cancel
```

Devuelvan el reposo al valor que anotaron en la parte 3.1 (por ejemplo `sudo pmset -c sleep 10`) y vuelvan a activar las actualizaciones automáticas.

### 6.3 Comparación de los tres modelos y documento de una página

`python taller.py comparar` muestra la comparación del Corolla con el Mazda 3 y el Kia K3 y guarda la tabla y la gráfica en `entrega/comparacion/`. El zip la incluye sola.

Partan de `docs/esqueleto_documento_una_pagina.md`, que dice qué poner en cada bloque. Escríbanlo con sus palabras en Google Docs o Word, inserten `docs/arquitectura.png`, revisen que quepa en una página y expórtenlo como `entrega/documento_una_pagina.pdf`. Si algún día falló, cuéntenlo en una frase usando `docs/incidentes.md`.

### 6.4 Armar el zip

En el Mac de la Persona A, primero `git pull` para traer los correos y el documento que haya subido la Persona B, y luego el comando de la entrega.

```bash
cd ~/taller2-corolla && source .venv/bin/activate
git pull
python taller.py entregar
```

Sale el tamaño del zip, el 16 como incidente documentado y la lista de lo que falta. Corrijan y repitan hasta que diga `La lista de revisión está completa.` Revisen el contenido.

```bash
unzip -l entrega_taller2_corolla.zip | less
```

(Q para salir.) No debe aparecer `.env`. Deben estar `datos/oficial` con los días del 17 al 21, `datos/modelos`, `datos/prueba`, `datos/launchd`, `entrega/` con la comparación y el código.

### 6.5 Subir

Suban `entrega_taller2_corolla.zip` a Bloque Neón antes del lunes 23 de noviembre a las 11:59 p. m.

## Parte 7. Problemas frecuentes

| Problema | Solución |
|---|---|
| `command not found: python` | Falta activar el entorno. `cd ~/taller2-corolla && source .venv/bin/activate` |
| `ModuleNotFoundError` | `pip install -r requirements.txt` con el entorno activado |
| `Executable doesn't exist` o Chromium no abre | `python -m playwright install chromium` |
| `Operation not permitted` en `datos/launchd/*.log` | El proyecto está en Documentos, Escritorio o Descargas. Muévanlo con `mv <carpeta> ~/taller2-corolla`, entren a la carpeta, borren y creen de nuevo el entorno (`rm -rf .venv`, `python3.12 -m venv .venv`, `source .venv/bin/activate`, `pip install -r requirements.txt`) y ejecuten `python taller.py programar` otra vez |
| `SMTPAuthenticationError` o `535` | La contraseña no es de aplicación o tiene un error. Creen otra en la parte 1.7 y péguenla en el `.env` |
| `ConnectionRefusedError` o `timed out` al enviar el correo | La red no deja enviar correo (pasa en algunas oficinas). El programa prueba solo el puerto 587, y si tampoco puede, el reintento lo envía cuando el Mac esté en otra red |
| No aparecen los avisos del Mac | En Ajustes del Sistema, Notificaciones, busquen Editor de Scripts (Script Editor) y permitan sus notificaciones. Los avisos son una ayuda; el programa funciona igual sin ellos |
| El correo llega a spam | Márquenlo como no spam y agreguen la cuenta que envía a sus contactos |
| `pmset` dice `must be run as root` | Le faltó `sudo` al comienzo del comando |
| En Windows, PowerShell no deja activar el entorno | Ejecuten una vez `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, respondan que sí y vuelvan a activar |
| `launchctl no pudo cargar` al programar | `python taller.py desprogramar` y luego `python taller.py programar` |
| La hora del Mac no es la de Colombia | No es grave. `programar` convierte las 8:00 y 11:00 de Bogotá a la hora del Mac. Mejor aún, en Ajustes del Sistema, General, Fecha y hora, pongan la zona de Bogotá |
| La búsqueda devuelve 0 anuncios | Abran la búsqueda en el navegador y miren si Carroya cambió algo. Corran `python taller.py paso1 --visible` y pidan ayuda a Antigravity con el log de ese día |

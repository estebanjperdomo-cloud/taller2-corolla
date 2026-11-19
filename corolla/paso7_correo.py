"""Paso 7 del taller (5 %). Plantilla y envío del correo diario de las 11:00.

El correo se arma con lo que haya a esa hora: el archivo de estado de la
recolección, el manifiesto de la búsqueda y el resumen del análisis. Si algo
falta (la recolección sigue en curso, falló o no hubo datos para la gráfica),
el correo lo dice en lugar de dejar de enviarse.

Credenciales SMTP por variables de entorno (nunca en el código):
  SMTP_HOST (por defecto smtp.gmail.com), SMTP_PORT (465), SMTP_USER,
  SMTP_PASSWORD (clave de aplicación de Gmail), EMAIL_TO, EMAIL_FROM (opcional).
"""
from __future__ import annotations

import base64
import collections
import json
import os
import smtplib
import ssl
import time
from contextlib import contextmanager
from datetime import date, datetime
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import configuracion as config, estado as estado_mod, formato
from . import paso6_analisis as analisis
from .paso1_recoleccion import FALLIDO, leer_csv

PLANTILLAS = Path(__file__).parent / "plantillas"

ESTILOS_ESTADO = {
    "completada": ("Proceso completo", "✓", "#e7f5e7", "#0b5d0b"),
    "completada_con_advertencias": ("Completado con advertencias", "⚠", "#fff3d6", "#5c4200"),
    "en_curso": ("Recolección todavía en curso", "⏳", "#fff3d6", "#5c4200"),
    "fallida": ("La recolección falló", "✕", "#fbe5e5", "#8c1f1f"),
    "sin_ejecucion": ("Sin recolección registrada hoy", "✕", "#fbe5e5", "#8c1f1f"),
}
NOMBRES_ETAPA = {"busqueda": "búsqueda", "descarga": "descarga", "consolidacion": "consolidación",
                 "analisis": "análisis"}


def _leer_json(ruta: Path) -> dict | None:
    try:
        return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
    except json.JSONDecodeError:
        return None


def _hora(marca: str | None) -> str:
    if not marca:
        return "sin dato"
    try:
        return datetime.fromisoformat(marca).astimezone(config.ZONA_HORARIA).strftime("%H:%M:%S")
    except ValueError:
        return marca


def _duracion(inicio: str | None, fin: str | None) -> str:
    if not inicio or not fin:
        return "sin dato"
    segundos = (datetime.fromisoformat(fin) - datetime.fromisoformat(inicio)).total_seconds()
    minutos, segundos = divmod(int(segundos), 60)
    return f"{minutos} min {segundos} s"


def _numero(valor) -> str:
    return "sin dato" if valor is None else formato.miles(valor)


# --- Reunir la información del día ---------------------------------------------------------------
def tarjeta_ganga(a: dict, modelo: str) -> dict:
    """Lo que muestra el correo de una posible ganga (Corolla o modelo adicional)."""
    sospechoso = a["clasificacion"] == analisis.SOSPECHOSO
    sunroof = {True: "Sunroof sí", False: "Sunroof no"}.get(a.get("sunroof"), "Sunroof sin dato")
    if a.get("sunroof") in (1, 1.0):
        sunroof = "Sunroof sí"
    elif a.get("sunroof") in (0, 0.0):
        sunroof = "Sunroof no"
    rasgos = [str(a["anio"]) if a.get("anio") else "año sin dato",
              a.get("version") or "versión sin dato", formato.kilometros(a.get("kilometraje")),
              a.get("transmision") or "caja sin dato", a.get("combustible") or "combustible sin dato",
              (a.get("ciudad") or "ciudad sin dato").title(), sunroof]
    return {
        "sospechoso": sospechoso,
        "etiqueta": "Precio sospechosamente bajo, verificar" if sospechoso else "Posible ganga",
        "titulo": f"{modelo} {a.get('anio') or ''} {a.get('version') or ''}".strip(),
        "url": a["url"],
        "caracteristicas": rasgos,
        "precio": formato.pesos(a["precio"]),
        "esperado": formato.pesos(round(a["precio_esperado"], -5)),
        "diferencia": f"{formato.porcentaje(a['descuento'])} menos",
        "comparables": (f"Se comparó con el precio esperado según año, kilometraje y versión, y con la mediana "
                        f"de {int(a['n_comparables'])} anuncios parecidos, que es "
                        f"{formato.pesos(a['mediana_comparables'])}."),
        "explicacion": a["explicacion"],
    }


def otros_modelos(modo: str, fecha: date) -> list[dict]:
    """Resumen de los modelos adicionales para el correo. Nunca hace fallar el correo del Corolla."""
    salida = []
    for busqueda in config.MODELOS_EXTRA:
        try:
            rutas = config.rutas_modelo(busqueda, modo)
            est = estado_mod.leer(rutas, fecha)
            resumen = _leer_json(rutas.reporte(fecha) / f"resumen_{fecha.isoformat()}.json")
            if est is None and resumen is None:
                continue
            metricas = (est or {}).get("metricas") or {}
            partes = [f"{formato.miles(metricas.get('enlaces_encontrados') or 0)} anuncios",
                      f"{formato.miles(metricas.get('anuncios_nuevos') or 0)} nuevos para el sistema"]
            st = (resumen or {}).get("estadisticas")
            if st:
                partes.append(f"mediana {formato.pesos(st['mediana'])} (entre {formato.pesos(st['q1'])} y "
                              f"{formato.pesos(st['q3'])} está la mitad central)")
            codigo = (est or {}).get("estado", "sin_ejecucion")
            estado_txt = {"completada": "completa", "completada_con_advertencias": "con advertencias",
                          "en_curso": "en curso", "fallida": "fallida"}.get(codigo, codigo)
            gangas = [tarjeta_ganga(a, busqueda.nombre) for a in (resumen or {}).get("alertas_nuevas") or []][:3]
            bajadas = len((resumen or {}).get("bajadas_precio") or [])
            if bajadas:
                partes.append(f"{bajadas} bajada{'s' if bajadas > 1 else ''} de precio")
            salida.append({"nombre": busqueda.nombre, "estado": estado_txt,
                           "resumen": ", ".join(partes) + ".", "gangas": gangas,
                           "sin_gangas": "Sin posibles gangas nuevas hoy." if not gangas else ""})
        except Exception as exc:
            salida.append({"nombre": busqueda.nombre, "estado": "sin datos",
                           "resumen": f"No se pudo leer el resumen ({type(exc).__name__}).", "gangas": [],
                           "sin_gangas": ""})
    return salida


@contextmanager
def candado_correo(rutas: config.Rutas, fecha: date):
    """Evita que dos envíos del mismo día corran a la vez (por ejemplo, el de las 11:00 y un
    reintento que arrancan juntos cuando el Mac se despierta). En Windows no hace falta."""
    rutas.crear()
    try:
        import fcntl
    except ImportError:
        yield
        return
    with open(rutas.estado / f"correo_{fecha.isoformat()}.lock", "w") as archivo:
        fcntl.flock(archivo, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(archivo, fcntl.LOCK_UN)


def correo_ya_enviado(rutas: config.Rutas, fecha: date) -> bool:
    """¿Algún correo de ese día ya quedó enviado? Lo usan el envío de las 11:00 y los reintentos."""
    for archivo in rutas.logs.glob(f"*COR-{fecha:%Y%m%d}-*.jsonl"):
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            try:
                registro = json.loads(linea)
            except ValueError:
                continue
            if registro.get("etapa") == "correo" and registro.get("correo_estado") == "enviado":
                return True
    return False


def reunir(rutas: config.Rutas, fecha: date, run_id_correo: str) -> dict:
    est = estado_mod.leer(rutas, fecha)
    manifiesto = _leer_json(rutas.manifiesto(fecha))
    resumen = _leer_json(rutas.reporte(fecha) / f"resumen_{fecha.isoformat()}.json")
    metricas = dict((est or {}).get("metricas") or {})

    codigo = "sin_ejecucion" if est is None else est.get("estado", "en_curso")
    etiqueta, icono, fondo, texto = ESTILOS_ESTADO.get(codigo, ESTILOS_ESTADO["completada_con_advertencias"])
    # La hora real de inicio, por si un día la recolección se corrió más tarde a mano
    inicio = _hora((est or {}).get("inicio"))[:5] if (est or {}).get("inicio") else "8:00"
    descripciones = {
        "completada": f"La recolección de hoy, iniciada a las {inicio}, terminó todas sus etapas sin errores.",
        "completada_con_advertencias": "La recolección terminó, pero con advertencias. Revise la lista de "
                                       "errores; las cifras pueden estar incompletas.",
        "en_curso": f"La recolección que empezó a las {inicio} todavía no termina. Este correo sale de todos "
                    "modos con la información disponible a esta hora, que está incompleta.",
        "fallida": "La recolección de hoy no pudo completarse. Abajo están los errores registrados.",
        "sin_ejecucion": "No hay registro de la recolección de hoy. El proceso de las 8:00 no se ejecutó o no "
                         "alcanzó a guardar su estado.",
    }

    # Errores y pendientes
    errores = list((est or {}).get("errores") or [])
    if manifiesto and est is None:      # con archivo de estado, esos errores ya vienen incluidos
        errores += list(manifiesto.get("errores_busqueda") or [])
    datos = rutas.datos(fecha)
    if datos.exists():
        errores = [e for e in errores if not (e.startswith("descarga, ") and "fallido" in e)]
        motivos = collections.Counter(f.get("motivo_error") or "sin motivo" for f in leer_csv(datos)
                                      if f.get("estado_descarga") == FALLIDO)
        for motivo, veces in motivos.most_common(3):
            errores.append(f"{veces} descarga(s) fallida(s) por {motivo}")
    if resumen and resumen.get("precios_invalidos"):
        errores.append(f"{len(resumen['precios_invalidos'])} anuncio(s) con precio inválido fuera del análisis "
                       f"({resumen['precios_invalidos'][0]['motivo']})")
    pendientes = []
    for etapa, info in ((est or {}).get("etapas") or {}).items():
        if info.get("estado") in ("pendiente", "error"):
            pendientes.append(f"{NOMBRES_ETAPA.get(etapa, etapa)} ({info.get('estado')})")
    if est is None:
        pendientes = [f"{nombre} (sin registro)" for nombre in NOMBRES_ETAPA.values()]

    descargas = (manifiesto or {}).get("descargas") or {}
    kpis = [
        {"valor": _numero(metricas.get("enlaces_encontrados", (manifiesto or {}).get("enlaces_que_cumplen_criterios"))),
         "etiqueta": "Enlaces encontrados"},
        {"valor": _numero(metricas.get("anuncios_nuevos", (manifiesto or {}).get("anuncios_nuevos_para_el_sistema"))),
         "etiqueta": "Anuncios nuevos para el sistema"},
        {"valor": _numero(metricas.get("descargas_exitosas", descargas.get("descargado"))),
         "etiqueta": "Descargas exitosas"},
        {"valor": _numero(metricas.get("descargas_fallidas", descargas.get("fallido"))),
         "etiqueta": "Descargas fallidas"},
    ]

    if manifiesto:
        completa = "Sí" if manifiesto.get("busqueda_completa") else f"No, {manifiesto.get('motivo_busqueda_incompleta')}"
        leidas, total = len(manifiesto.get("paginas_leidas") or []), manifiesto.get("paginas_esperadas")
        paginas = f"{leidas} de {total}" if total is not None else f"{leidas} (no se supo el total)"
    else:
        completa, paginas = "sin dato", "sin dato"
    ejecucion = [
        {"etiqueta": "Identificador de la recolección", "valor": (est or {}).get("run_id", "sin registro")},
        {"etiqueta": "Cómo se inició", "valor": {"programado": "automática, programada en el Mac (launchd)",
                                                  "manual": "manual, desde la terminal",
                                                  "demo": "demostración simulada"}.get(
            (est or {}).get("origen"), "sin dato")},
        {"etiqueta": "Inicio", "valor": _hora((est or {}).get("inicio"))},
        {"etiqueta": "Fin", "valor": _hora(est.get("fin")) if est and est.get("fin") else "todavía en curso" if est else "sin dato"},
        {"etiqueta": "Duración", "valor": _duracion((est or {}).get("inicio"), (est or {}).get("fin"))},
        {"etiqueta": "Páginas de resultados leídas", "valor": paginas},
        {"etiqueta": "Anuncios reportados por Carroya", "valor": _numero((manifiesto or {}).get("total_reportado_por_carroya"))},
        {"etiqueta": "Búsqueda completa", "valor": completa},
        {"etiqueta": "Descargas pendientes", "valor": _numero(metricas.get("descargas_pendientes", descargas.get("sin intentar")))},
        {"etiqueta": "Registros agregados · actualizados · sin cambios",
         "valor": " · ".join(_numero(metricas.get(k)) for k in
                             ("registros_agregados", "registros_actualizados", "registros_sin_cambios"))},
        {"etiqueta": "Anuncios únicos en la base", "valor": _numero(metricas.get("anuncios_unicos"))},
        {"etiqueta": "Tamaño de la base consolidada", "valor": formato.bytes_legibles(metricas.get("tamano_bd_bytes"))},
    ]

    # Distribución
    distribucion = {"grafica_ruta": None, "grafica_cid": None, "motivo": None, "filas": [], "por_anio": []}
    if resumen is None:
        distribucion["motivo"] = ("el análisis del día todavía no existe" if codigo == "en_curso"
                                  else "el análisis del día no se generó")
    else:
        if resumen.get("grafica"):
            ruta_png = rutas.reporte(fecha) / resumen["grafica"]
            if ruta_png.exists():
                distribucion["grafica_ruta"] = ruta_png
                distribucion["grafica_cid"] = make_msgid(domain="corolla.monitor")[1:-1]
        if not distribucion["grafica_ruta"]:
            distribucion["motivo"] = resumen.get("motivo_sin_grafica") or "no se encontró el archivo de la gráfica"
        st = resumen.get("estadisticas")
        if st:
            distribucion["filas"] = [
                {"etiqueta": "Anuncios con precio válido (una observación por anuncio)", "valor": formato.miles(st["n"])},
                {"etiqueta": "Mediana", "valor": formato.pesos(st["mediana"])},
                {"etiqueta": "Primer cuartil (Q1)", "valor": formato.pesos(st["q1"])},
                {"etiqueta": "Tercer cuartil (Q3)", "valor": formato.pesos(st["q3"])},
                {"etiqueta": "Mínimo", "valor": formato.pesos(st["minimo"])},
                {"etiqueta": "Máximo", "valor": formato.pesos(st["maximo"])},
                {"etiqueta": "Promedio", "valor": formato.pesos(st["media"])},
            ]
        distribucion["por_anio"] = [{"anio": a["anio"], "n": a["n"], "mediana": formato.pesos(a["mediana"])}
                                    for a in resumen.get("por_anio") or []]

    # Gangas nuevas
    gangas = [tarjeta_ganga(a, "Toyota Corolla") for a in (resumen or {}).get("alertas_nuevas") or []]
    if resumen is None:
        sin_gangas = "No se puede evaluar hoy porque el análisis del día no está disponible."
    elif resumen.get("modelo") is None:
        sin_gangas = ("No se evaluaron gangas hoy porque no hay datos suficientes para construir una referencia de "
                      "precios confiable.")
    else:
        sin_gangas = "Hoy no se detectaron anuncios nuevos con un precio anormalmente bajo para sus características."
    notas = []
    if resumen:
        viejas = len(resumen.get("alertas") or []) - len(resumen.get("alertas_nuevas") or [])
        if viejas > 0:
            notas.append(f"Además, {viejas} anuncio(s) que ya se conocían siguen cumpliendo la regla; "
                         "están en el archivo adjunto del análisis.")
        if resumen.get("senales_sin_respaldo"):
            notas.append(f"{resumen['senales_sin_respaldo']} anuncio(s) parecen baratos frente al modelo, pero no "
                         "tienen suficientes anuncios parecidos para confirmarlo, así que no se reportan como gangas.")

    bajadas = [{"descripcion": b["descripcion"], "url": b["url"], "antes": formato.pesos(b["precio_anterior"]),
                "ahora": formato.pesos(b["precio_nuevo"]), "variacion": formato.porcentaje(b["variacion"]),
                "fecha_anterior": b["fecha_anterior"]} for b in (resumen or {}).get("bajadas_precio", [])[:10]]

    metodo = [
        "Cada precio se compara con el precio esperado para su año, kilometraje y versión (nivel de equipamiento "
        "y motor), según un modelo estimado con los anuncios del mismo día.",
        f"Es posible ganga si está al menos {int(analisis.DESCUENTO_MINIMO * 100)} % por debajo del esperado, si esa "
        f"diferencia es inusual frente a la variación del día y si también está al menos "
        f"{int(analisis.DESCUENTO_VS_COMPARABLES * 100)} % por debajo de la mediana de mínimo "
        f"{analisis.MIN_COMPARABLES} anuncios parecidos.",
        f"Las rebajas de más de {int(analisis.DESCUENTO_SOSPECHOSO * 100)} % se marcan para verificar, porque suelen "
        "ser errores o anuncios engañosos.",
    ]
    if resumen and resumen.get("modelo"):
        metodo += resumen["modelo"]["efectos"][:3]

    modo = rutas.modo
    banner = None
    if modo == "prueba":
        banner = {"titulo": "Correo de PRUEBA",
                  "texto": "Se generó fuera del periodo evaluado o en una ejecución manual de prueba; "
                           "no hace parte de las evidencias del 16 al 21 de noviembre."}
    elif modo == "demo":
        banner = {"titulo": "Correo de DEMOSTRACIÓN",
                  "texto": "Los datos son simulados para mostrar el funcionamiento sin conexión a Carroya."}

    n_gangas = len(gangas)
    if codigo in ("fallida", "sin_ejecucion"):
        corto = "recolección fallida" if codigo == "fallida" else "sin recolección"
    elif codigo == "en_curso":
        corto = "recolección en curso"
    else:
        corto = ("sin gangas nuevas" if n_gangas == 0 else
                 f"{n_gangas} posible{'s' if n_gangas > 1 else ''} ganga{'s' if n_gangas > 1 else ''}")
    prefijo = {"prueba": "[PRUEBA] ", "demo": "[DEMO] "}.get(modo, "")
    asunto = f"{prefijo}Corolla 2022 a 2026 · {fecha:%d/%m/%Y} · {corto}"

    momento = config.ahora()
    pie = (f"Generado automáticamente el {config.fecha_larga(momento.date())} a las {momento:%H:%M:%S} "
           f"(hora de Colombia, {config.NOMBRE_ZONA}). Recolección {(est or {}).get('run_id', 'sin registro')} · "
           f"Correo {run_id_correo} · Modo {modo}. Datos de anuncios públicos de Carroya.com.")

    return {
        "otros_modelos": otros_modelos(modo, fecha) if modo in ("oficial", "prueba") else [],
        "asunto": asunto,
        "preheader": f"{kpis[0]['valor']} enlaces, {kpis[1]['valor']} nuevos, {corto}.",
        "fecha": fecha.isoformat(),
        "fecha_larga": config.fecha_larga(fecha),
        "modo": modo,
        "banner_modo": banner,
        "estado": {"codigo": codigo, "etiqueta": etiqueta, "icono": icono, "fondo": fondo, "texto": texto,
                   "descripcion": descripciones.get(codigo, "")},
        "kpis": kpis,
        "ejecucion": ejecucion,
        "errores": errores,
        "pendientes": pendientes,
        "distribucion": distribucion,
        "primera_ejecucion": bool((resumen or {}).get("primera_ejecucion")),
        "gangas": gangas,
        "sin_gangas": sin_gangas,
        "notas_alertas": " ".join(notas),
        "bajadas": bajadas,
        "metodo": metodo,
        "pie": pie,
        "adjuntos": [p for p in (rutas.reporte(fecha) / f"analisis_{fecha.isoformat()}.csv",
                                 rutas.reporte(fecha) / f"gangas_{fecha.isoformat()}.csv") if p.exists()],
    }


# --- Construcción del mensaje ------------------------------------------------------------------------
def texto_plano(c: dict) -> str:
    lineas = [c["asunto"], "", f"Reporte del {c['fecha_larga']}", f"Estado general · {c['estado']['etiqueta']}",
              c["estado"]["descripcion"], ""]
    if c["banner_modo"]:
        lineas += [f"{c['banner_modo']['titulo']}. {c['banner_modo']['texto']}", ""]
    lineas += [f"{k['etiqueta']} · {k['valor']}" for k in c["kpis"]] + [""]
    lineas += ["ESTADO DE LA EJECUCIÓN"] + [f"  {f['etiqueta']} · {f['valor']}" for f in c["ejecucion"]] + [""]
    lineas += ["ERRORES Y ETAPAS PENDIENTES"]
    lineas += [f"  * {e}" for e in c["pendientes"] + c["errores"]] or ["  Sin errores relevantes."]
    lineas += ["", "DISTRIBUCIÓN DE PRECIOS"]
    if c["distribucion"]["filas"]:
        lineas += [f"  {f['etiqueta']} · {f['valor']}" for f in c["distribucion"]["filas"]]
    if c["distribucion"]["motivo"]:
        lineas += [f"  Sin gráfica porque {c['distribucion']['motivo']}."]
    lineas += ["", "POSIBLES GANGAS ENTRE LOS ANUNCIOS NUEVOS"]
    for g in c["gangas"]:
        lineas += [f"  * {g['etiqueta']} · {g['titulo']}", f"    {g['url']}",
                   f"    {', '.join(g['caracteristicas'])}",
                   f"    Publicado {g['precio']} · esperado {g['esperado']} · {g['diferencia']}",
                   f"    {g['explicacion']}", ""]
    if not c["gangas"]:
        lineas += [f"  {c['sin_gangas']}"]
    if c["notas_alertas"]:
        lineas += [f"  {c['notas_alertas']}"]
    if c.get("otros_modelos"):
        lineas += ["", "OTROS MODELOS MONITOREADOS (ADICIONAL)"]
        for m in c["otros_modelos"]:
            lineas += [f"  {m['nombre']} · recolección {m['estado']} · {m['resumen']}"]
            for g in m["gangas"]:
                lineas += [f"    * {g['etiqueta']} · {g['titulo']} · {g['precio']} · {g['diferencia']}",
                           f"      {g['url']}", f"      {g['explicacion']}"]
            if m["sin_gangas"]:
                lineas += [f"    {m['sin_gangas']}"]
    if c["bajadas"]:
        lineas += ["", "BAJADAS DE PRECIO"] + [f"  * {b['descripcion']} · {b['antes']} a {b['ahora']} ({b['variacion']}) "
                                                f"{b['url']}" for b in c["bajadas"]]
    lineas += ["", "CÓMO SE DETECTAN LAS GANGAS"] + [f"  * {m}" for m in c["metodo"]] + ["", c["pie"]]
    return "\n".join(lineas)


def construir(c: dict) -> tuple[EmailMessage, str]:
    """Devuelve el mensaje listo para enviar y el HTML (con la gráfica embebida) para guardar copia."""
    entorno = Environment(loader=FileSystemLoader(PLANTILLAS), autoescape=select_autoescape(["html"]))
    html = entorno.get_template("correo.html").render(c=c)

    mensaje = EmailMessage()
    mensaje["Subject"] = c["asunto"]
    mensaje["From"] = os.environ.get("EMAIL_FROM") or os.environ.get("SMTP_USER") or "monitor-corolla@localhost"
    mensaje["To"] = os.environ.get("EMAIL_TO") or "sin-destinatario@localhost"
    mensaje["Date"] = format_datetime(config.ahora())
    mensaje["Message-ID"] = make_msgid(domain="corolla.monitor")
    mensaje.set_content(texto_plano(c))
    mensaje.add_alternative(html, subtype="html")

    html_copia = html
    ruta_png = c["distribucion"]["grafica_ruta"]
    if ruta_png:
        contenido = Path(ruta_png).read_bytes()
        mensaje.get_payload()[1].add_related(contenido, maintype="image", subtype="png",
                                             cid=f"<{c['distribucion']['grafica_cid']}>",
                                             filename=Path(ruta_png).name)
        incrustada = "data:image/png;base64," + base64.b64encode(contenido).decode()
        html_copia = html.replace(f"cid:{c['distribucion']['grafica_cid']}", incrustada)
    for adjunto in c["adjuntos"]:
        mensaje.add_attachment(Path(adjunto).read_bytes(), maintype="text", subtype="csv",
                               filename=Path(adjunto).name)
    return mensaje, html_copia


def mensaje_minimo(rutas: config.Rutas, fecha: date, run_id: str, error: Exception) -> tuple[EmailMessage, str, str]:
    """Correo de respaldo cuando el reporte completo no se pudo armar."""
    est = estado_mod.leer(rutas, fecha) or {}
    prefijo = {"prueba": "[PRUEBA] ", "demo": "[DEMO] "}.get(rutas.modo, "")
    texto = (f"Reporte del {config.fecha_larga(fecha)}.\n\n"
             f"No se pudo armar el reporte completo por un error interno ({type(error).__name__}: {error}).\n"
             f"Estado de la recolección según su archivo de estado: {est.get('estado', 'sin registro')}.\n"
             f"Métricas disponibles: {json.dumps(est.get('metricas') or {}, ensure_ascii=False)}\n\n"
             f"Correo {run_id}, generado a las {config.ahora():%H:%M:%S} ({config.NOMBRE_ZONA}).")
    mensaje = EmailMessage()
    mensaje["Subject"] = f"{prefijo}Corolla 2022 a 2026 · {fecha:%d/%m/%Y} · reporte incompleto"
    mensaje["From"] = os.environ.get("EMAIL_FROM") or os.environ.get("SMTP_USER") or "monitor-corolla@localhost"
    mensaje["To"] = os.environ.get("EMAIL_TO") or "sin-destinatario@localhost"
    mensaje["Date"] = format_datetime(config.ahora())
    mensaje["Message-ID"] = make_msgid(domain="corolla.monitor")
    mensaje.set_content(texto)
    html = "<pre style='font-family:sans-serif;white-space:pre-wrap'>" + texto.replace("<", "&lt;") + "</pre>"
    return mensaje, html, texto


def enviar(mensaje: EmailMessage, intentos: int = 3, espera_s: float = 20) -> tuple[str, str | None]:
    """Envía por SMTP. Devuelve (estado, detalle): enviado, fallido o no_enviado."""
    host = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    puerto = int(os.environ.get("SMTP_PORT") or 465)
    usuario = (os.environ.get("SMTP_USER") or "").strip()
    clave = (os.environ.get("SMTP_PASSWORD") or "").replace(" ", "")  # Gmail la muestra con espacios
    destinatarios = [d.strip() for d in (os.environ.get("EMAIL_TO") or "").split(",") if d.strip()]
    if not destinatarios:
        return "no_enviado", "falta la variable EMAIL_TO con el destinatario"
    local = host in ("localhost", "127.0.0.1")
    if not (usuario and clave) and not local:
        return "no_enviado", "faltan SMTP_USER o SMTP_PASSWORD"
    # Algunas redes (oficinas, universidades) bloquean el puerto 465. Si la conexión falla,
    # se prueba el otro puerto de Gmail (587, con STARTTLS) antes de dar el intento por perdido.
    puertos = [puerto] + [p for p in (465, 587) if p != puerto and not local]
    ultimo = None
    for intento in range(1, intentos + 1):
        for p in puertos:
            try:
                _enviar_por(host, p, usuario, clave, mensaje, destinatarios)
                extra = f" (puerto {p})" if p != puerto else ""
                return "enviado", f"a {', '.join(destinatarios)} en el intento {intento}{extra}"
            except smtplib.SMTPConnectError as exc:          # el servidor no aceptó la conexión
                ultimo = f"{type(exc).__name__}: {exc} (puerto {p})"
            except smtplib.SMTPResponseException as exc:     # respondió con un error, por ejemplo la contraseña
                ultimo = f"{type(exc).__name__}: {exc}"
                break
            except OSError as exc:                           # la red no dejó conectar: probar el otro puerto
                ultimo = f"{type(exc).__name__}: {exc} (puerto {p})"
            except Exception as exc:
                ultimo = f"{type(exc).__name__}: {exc}"
                break
        if intento < intentos:
            time.sleep(espera_s)
    return "fallido", ultimo


def _enviar_por(host: str, puerto: int, usuario: str, clave: str, mensaje: EmailMessage,
                destinatarios: list[str]) -> None:
    contexto = ssl.create_default_context()
    if puerto == 465:
        servidor = smtplib.SMTP_SSL(host, puerto, context=contexto, timeout=60)
    else:
        servidor = smtplib.SMTP(host, puerto, timeout=60)
    with servidor:
        if puerto != 465:
            servidor.ehlo()
            if servidor.has_extn("starttls"):
                servidor.starttls(context=contexto)
                servidor.ehlo()
        if usuario and clave:
            servidor.login(usuario, clave)
        servidor.send_message(mensaje, to_addrs=destinatarios)


def guardar_copia(rutas: config.Rutas, fecha: date, run_id: str, mensaje: EmailMessage,
                  html: str, texto: str) -> Path:
    """Copia de lo enviado (eml, html y txt), con la hora en el nombre: evidencia para la entrega."""
    carpeta = rutas.correos_dia(fecha)
    carpeta.mkdir(parents=True, exist_ok=True)
    base = carpeta / f"correo_{fecha.isoformat()}_{config.ahora():%H%M%S}_{run_id}"
    base.with_suffix(".eml").write_bytes(bytes(mensaje))
    base.with_suffix(".html").write_text(html, encoding="utf-8")
    base.with_suffix(".txt").write_text(texto, encoding="utf-8")
    return base.with_suffix(".eml")

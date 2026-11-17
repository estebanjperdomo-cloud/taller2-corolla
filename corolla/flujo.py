"""Orquestación del workflow diario (lo que el Mac ejecuta solo, ver paso4_programacion.py).

  8:00   ejecutar_recoleccion()   paso 1 (búsqueda y descarga), paso 3 (consolidación)
                                  y paso 6 (análisis listo para el correo)
  11:00  ejecutar_correo()        paso 7, arma y envía el correo con lo que exista a esa hora

Cada paso también se puede correr solo (python taller.py paso1, paso3, paso6, paso7).
Todos dejan su rastro en el archivo de estado del día (datos/<modo>/estado/) y en los
logs del paso 5 (datos/<modo>/logs/), así el correo sabe qué terminó y qué no.
"""
from __future__ import annotations

import os
import traceback
from contextlib import nullcontext
from datetime import date
from typing import Callable

from . import configuracion as config
from . import estado as estado_mod
from . import paso1_recoleccion as recoleccion
from . import paso2_base_de_datos as base
from . import paso3_actualizacion as actualizacion
from . import paso6_analisis as analisis
from . import paso7_correo as correo
from .paso1_navegador import FuenteNoDisponible, NavegadorCarroya, esperar_conexion
from .paso5_bitacora import Bitacora

VISIBLE = ("1", "si", "sí", "true")


class Dia:
    """Lo que comparten los pasos de una misma recolección: carpetas, fecha,
    identificador de ejecución, bitácora y archivo de estado."""

    def __init__(self, rutas: config.Rutas, fecha: date, origen: str = "manual",
                 consola: bool = True, nueva: bool = True):
        rutas.crear()
        self.rutas, self.fecha = rutas, fecha
        previo = None if nueva else estado_mod.leer(rutas, fecha)
        if previo:
            self.estado = previo
        else:
            self.estado = estado_mod.nuevo(fecha, config.nuevo_run_id("REC", rutas.modo), rutas.modo, origen)
        self.run_id = self.estado["run_id"]
        self.bitacora = Bitacora(rutas, self.run_id, "recoleccion", fecha, consola=consola)
        self.guardar()

    def guardar(self) -> None:
        estado_mod.guardar(self.rutas, self.fecha, self.estado)

    def anotar(self, nombre: str, etapa, prefijo: str) -> None:
        self.estado["etapas"][nombre] = {"estado": etapa.estado, "fin": config.iso(config.ahora())}
        self.estado["metricas"].update({k: v for k, v in etapa.metricas.items() if v is not None})
        self.estado["errores"] = [e for e in self.estado["errores"] if not e.startswith(prefijo + ",")]
        self.estado["errores"] += [f"{prefijo}, {e}" for e in etapa.errores]
        self.guardar()


def _abrir_fuente(crear_fuente: Callable[[], object]):
    try:
        fuente = crear_fuente()
    except Exception as exc:
        fuente = FuenteNoDisponible(f"no se pudo preparar el navegador: {exc}")
    return fuente if hasattr(fuente, "__enter__") else nullcontext(fuente)


# --- Paso 1 -------------------------------------------------------------------------------
def correr_paso1(dia: Dia, crear_fuente: Callable[[], object] | None = None,
                 crear_fuente_respaldo: Callable[[], object] | None = None,
                 max_anuncios: int | None = None,
                 espera_reintentos: tuple[float, float] = config.ESPERA_ENTRE_REINTENTOS_S,
                 plantilla_detalle: str = config.URL_DETALLE) -> dict:
    """Busca todos los enlaces y descarga cada anuncio. Devuelve el manifiesto del día.

    crear_fuente es la forma de leer Carroya. Por defecto es el navegador real; las
    pruebas y la demostración pasan un Carroya simulado. Si la primera página no se
    puede leer con el navegador invisible, se repite con el de respaldo (ventana visible).
    """
    conocidos = base.ids_conocidos(dia.rutas.bd, dia.fecha)
    if crear_fuente is None:  # ejecución real contra Carroya
        esperar_conexion(registrar=dia.bitacora.info)
        crear_fuente = lambda: NavegadorCarroya()  # noqa: E731
        if crear_fuente_respaldo is None and os.environ.get("NAVEGADOR_VISIBLE", "").lower() not in VISIBLE:
            crear_fuente_respaldo = lambda: NavegadorCarroya(con_ventana=True)  # noqa: E731

    def intentar(fabrica) -> dict:
        with _abrir_fuente(fabrica) as fuente:
            return recoleccion.ejecutar_paso_1(
                fuente, dia.rutas, dia.fecha, dia.run_id, dia.bitacora, conocidos, dia.estado, dia.guardar,
                max_anuncios=max_anuncios, espera_reintentos=espera_reintentos,
                plantilla_detalle=plantilla_detalle)

    manifiesto = intentar(crear_fuente)
    if manifiesto.get("paginas_esperadas") is None and crear_fuente_respaldo is not None:
        dia.bitacora.aviso("No se pudo leer la primera página. Se repite el paso 1 con el navegador "
                           "de respaldo (ventana visible).")
        dia.estado["metricas"]["uso_navegador_respaldo"] = True
        manifiesto = intentar(crear_fuente_respaldo)

    errores = [e for e in dia.estado["errores"] if not e.startswith(("búsqueda,", "descarga,"))]
    errores += [f"búsqueda, {e}" for e in manifiesto.get("errores_busqueda") or []]
    descargas = manifiesto.get("descargas") or {}
    if descargas.get(recoleccion.FALLIDO):
        errores.append(f"descarga, {descargas[recoleccion.FALLIDO]} anuncio(s) fallido(s)")
    if descargas.get(recoleccion.SIN_INTENTAR):
        errores.append(f"descarga, {descargas[recoleccion.SIN_INTENTAR]} anuncio(s) sin intentar")
    dia.estado["errores"] = errores
    dia.guardar()
    return manifiesto


# --- Paso 3 -------------------------------------------------------------------------------
def correr_paso3(dia: Dia) -> dict:
    """Recibe los archivos diarios del paso 1 y actualiza la base del paso 2."""
    metricas: dict = {}
    with dia.bitacora.etapa("consolidacion") as etapa:
        if not dia.rutas.datos(dia.fecha).exists():
            raise FileNotFoundError(f"no existe {dia.rutas.datos(dia.fecha).name}; primero corra el paso 1")
        metricas = actualizacion.procesar_dia(dia.rutas.bd, dia.rutas.datos(dia.fecha),
                                              dia.rutas.manifiesto(dia.fecha), dia.run_id)
        etapa.metricas.update(metricas)
        if metricas.get("ya_procesado"):
            dia.bitacora.info("Los archivos de este día ya estaban procesados; la base no cambió.")
    dia.anotar("consolidacion", etapa, "consolidación")
    return metricas


# --- Paso 6 -------------------------------------------------------------------------------
def correr_paso6(dia: Dia) -> dict:
    """Distribución de precios y posibles gangas del día, listas para el correo."""
    resumen: dict = {}
    with dia.bitacora.etapa("analisis") as etapa:
        resumen = analisis.analizar_dia(dia.rutas.bd, dia.fecha, dia.rutas.reporte(dia.fecha))
        etapa.metricas.update(
            anuncios_validos_analisis=resumen.get("precios_validos"),
            posibles_gangas=len(resumen.get("alertas") or []),
            posibles_gangas_nuevas=len(resumen.get("alertas_nuevas") or []),
            grafica=resumen.get("grafica"),
        )
        if resumen.get("motivo_sin_grafica"):
            etapa.error(f"sin gráfica porque {resumen['motivo_sin_grafica']}")
    dia.anotar("analisis", etapa, "análisis")
    return resumen


def cerrar_dia(dia: Dia) -> dict:
    """Decide el estado general del día y escribe la línea de log que resume la ejecución."""
    estado_mod.cerrar(dia.estado)
    dia.guardar()
    with dia.bitacora.etapa("ejecucion_completa") as etapa:
        etapa.metricas.update({k: dia.estado["metricas"].get(k) for k in (
            "paginas_esperadas", "paginas_recorridas", "busqueda_completa",
            "enlaces_encontrados", "anuncios_nuevos", "descargas_exitosas", "descargas_fallidas",
            "descargas_pendientes", "registros_agregados", "registros_actualizados",
            "registros_sin_cambios", "anuncios_unicos", "tamano_bd_bytes",
            "anuncios_validos_analisis", "posibles_gangas", "posibles_gangas_nuevas")})
        etapa.metricas["estado_general"] = dia.estado["estado"]
        etapa.metricas["origen"] = dia.estado.get("origen")
        etapa.errores = list(dia.estado["errores"])
        etapa.estado = {estado_mod.COMPLETADA: "ok", estado_mod.FALLIDA: "error"}.get(
            dia.estado["estado"], "con_advertencias")
    dia.bitacora.info(f"Recolección terminada con estado general '{dia.estado['estado']}'.")
    return dia.estado


# --- Lo que corre a las 8:00 ------------------------------------------------------------------
def ejecutar_recoleccion(rutas: config.Rutas, fecha: date,
                         crear_fuente: Callable[[], object] | None = None,
                         crear_fuente_respaldo: Callable[[], object] | None = None,
                         max_anuncios: int | None = None,
                         espera_reintentos: tuple[float, float] = config.ESPERA_ENTRE_REINTENTOS_S,
                         consola: bool = True, plantilla_detalle: str = config.URL_DETALLE,
                         origen: str = "manual") -> dict:
    """Paso 1, paso 3 y paso 6 seguidos. Devuelve el estado del día (también queda guardado)."""
    dia = Dia(rutas, fecha, origen=origen, consola=consola, nueva=True)
    dia.bitacora.info(f"Recolección del {fecha.isoformat()} en modo {rutas.modo} (origen {origen}).")
    try:
        correr_paso1(dia, crear_fuente, crear_fuente_respaldo, max_anuncios, espera_reintentos, plantilla_detalle)
        correr_paso3(dia)
        correr_paso6(dia)
        return cerrar_dia(dia)
    finally:
        dia.bitacora.cerrar()


# --- Lo que corre a las 11:00 -----------------------------------------------------------------
def ejecutar_correo(rutas: config.Rutas, fecha: date, enviar: bool = True, consola: bool = True,
                    origen: str = "manual") -> dict:
    """Paso 7. Sale siempre, aunque falte información o falle el armado del reporte."""
    rutas.crear()
    run_id = config.nuevo_run_id("COR", rutas.modo)
    bitacora = Bitacora(rutas, run_id, "correo", fecha, consola=consola)
    bitacora.info(f"Correo del {fecha.isoformat()} en modo {rutas.modo} (origen {origen}).")
    resultado = {"run_id": run_id, "estado": "no_enviado", "detalle": None, "copia": None, "asunto": None}
    with bitacora.etapa("correo") as etapa:
        try:
            contenido = correo.reunir(rutas, fecha, run_id)
            mensaje, html = correo.construir(contenido)
            texto = correo.texto_plano(contenido)
            resultado["asunto"] = contenido["asunto"]
            etapa.metricas.update(estado_recoleccion=contenido["estado"]["codigo"],
                                  posibles_gangas_nuevas=len(contenido["gangas"]))
        except Exception as exc:
            bitacora.logger.error("No se pudo armar el reporte completo\n%s", traceback.format_exc())
            etapa.error(f"no se pudo armar el reporte completo ({type(exc).__name__}: {exc}); "
                        "se envió una versión mínima")
            mensaje, html, texto = correo.mensaje_minimo(rutas, fecha, run_id, exc)
            resultado["asunto"] = mensaje["Subject"]
        if enviar:
            host = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
            if origen == "programado" and host not in ("localhost", "127.0.0.1"):
                esperar_conexion(host, int(os.environ.get("SMTP_PORT") or 465), max_espera_s=300,
                                 registrar=bitacora.info)
            resultado["estado"], resultado["detalle"] = correo.enviar(mensaje)
        else:
            resultado["detalle"] = "envío desactivado; solo se guardó la copia"
        resultado["copia"] = str(correo.guardar_copia(rutas, fecha, run_id, mensaje, html, texto))
        etapa.metricas.update(correo_estado=resultado["estado"], correo_detalle=resultado["detalle"],
                              asunto=resultado["asunto"], origen=origen)
        if resultado["estado"] == "fallido":
            etapa.error(f"el correo no se pudo enviar: {resultado['detalle']}")
        elif resultado["estado"] == "no_enviado" and enviar:
            etapa.error(f"el correo no se envió: {resultado['detalle']}")
    if etapa.estado == "error" and resultado["copia"] is None:
        resultado["estado"], resultado["detalle"] = "fallido", "; ".join(etapa.errores)
    bitacora.info(f"Correo {resultado['estado']} ({resultado['detalle']}).")
    bitacora.cerrar()
    return resultado

"""Paso 1 del taller. Lectura de Carroya con un navegador real (Playwright + Chromium).

Por qué un navegador y no requests + BeautifulSoup:
Carroya es una aplicación de JavaScript. El HTML que entrega el servidor no
trae los anuncios; es la página, ya cargada en el navegador, la que se los pide
a su API interna y los recibe en JSON. Abrimos las páginas públicas como lo
haría una persona y leemos esa respuesta JSON que la propia página recibe.

Ventajas: no inventamos encabezados ni credenciales, obtenemos datos ya
estructurados (precio, kilometraje, versión...) en lugar de raspar texto, y
si Carroya cambia detalles internos de la petición, el navegador los sigue
manejando. Si el sitio responde con error o no entrega los datos, se lanza
ErrorDescarga con un motivo legible, que queda registrado en los archivos.
"""
from __future__ import annotations

import json
import os
import random
import socket
import time

from . import configuracion as config


class ErrorDescarga(Exception):
    """La página no entregó los datos esperados. El mensaje explica el motivo."""


def pagina_de_la_peticion(cuerpo: str | None) -> int | None:
    """Número de página que pide la búsqueda (va en el cuerpo JSON del POST)."""
    if not cuerpo:
        return None
    try:
        parametros = json.loads(cuerpo).get("params") or {}
        return int(str(parametros.get("page") or "1").strip())
    except (ValueError, TypeError, AttributeError):
        return None


class NavegadorCarroya:
    """Fuente de datos real. Se usa como context manager:

        with NavegadorCarroya() as nav:
            pagina = nav.obtener_busqueda(1)
            ficha = nav.obtener_detalle(url, id_anuncio)

    Chromium se abre en la primera petición; si no se puede abrir, cada
    petición falla con ErrorDescarga y el resto del flujo lo registra.
    """

    def __init__(self, con_ventana: bool | None = None, ruta_chrome: str | None = None,
                 url_busqueda: str = config.URL_BUSQUEDA,
                 pausa: tuple[float, float] = config.PAUSA_ENTRE_PAGINAS_S,
                 tiempo_limite_ms: int = config.TIEMPO_LIMITE_MS):
        if con_ventana is None:  # NAVEGADOR_VISIBLE=1 en el .env abre una ventana normal de Chromium
            con_ventana = os.environ.get("NAVEGADOR_VISIBLE", "").strip().lower() in ("1", "si", "sí", "true")
        self.con_ventana = con_ventana
        self.ruta_chrome = ruta_chrome or os.environ.get("COROLLA_CHROME") or None
        self.url_busqueda = url_busqueda
        self.pausa = pausa
        self.tiempo_limite_ms = tiempo_limite_ms
        self._pw = self._navegador = self._contexto = self._pagina = None

    # -- ciclo de vida ------------------------------------------------------------
    def __enter__(self) -> "NavegadorCarroya":
        return self

    def __exit__(self, *exc) -> bool:
        self.cerrar()
        return False

    def _abrir(self) -> None:
        if self._pagina is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ErrorDescarga("Playwright no está instalado (pip install -r requirements.txt)") from exc
        try:
            self._pw = sync_playwright().start()
            opciones = {"headless": not self.con_ventana}
            if self.ruta_chrome:
                opciones["executable_path"] = self.ruta_chrome
            self._navegador = self._pw.chromium.launch(**opciones)
            self._contexto = self._navegador.new_context(
                locale="es-CO", timezone_id=config.NOMBRE_ZONA,
                viewport={"width": 1366, "height": 900},
            )
            # No descargamos fotos, videos ni fuentes: no hacen falta y así
            # cada visita pesa menos para nosotros y para el sitio.
            self._contexto.route("**/*", self._filtrar_recursos)
            self._pagina = self._contexto.new_page()
        except Exception as exc:
            self.cerrar()
            raise ErrorDescarga(
                f"no se pudo abrir Chromium ({str(exc).splitlines()[0][:160]}). "
                "Ejecute: python -m playwright install chromium") from exc

    def cerrar(self) -> None:
        for objeto in (self._contexto, self._navegador):
            try:
                if objeto is not None:
                    objeto.close()
            except Exception:
                pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        self._pw = self._navegador = self._contexto = self._pagina = None

    @staticmethod
    def _filtrar_recursos(route) -> None:
        if route.request.resource_type in ("image", "media", "font"):
            route.abort()
        else:
            route.continue_()

    # -- núcleo: abrir una página y quedarse con el JSON que ella recibe --------------
    def _abrir_y_capturar(self, url: str, es_la_respuesta) -> dict:
        from playwright.sync_api import Error as ErrorPlaywright
        from playwright.sync_api import TimeoutError as TiempoAgotado

        self._abrir()
        time.sleep(random.uniform(*self.pausa))

        def predicado(respuesta) -> bool:
            try:
                return bool(es_la_respuesta(respuesta))
            except Exception:
                return False

        try:
            with self._pagina.expect_response(predicado, timeout=self.tiempo_limite_ms) as info:
                self._pagina.goto(url, wait_until="domcontentloaded", timeout=self.tiempo_limite_ms)
            respuesta = info.value
        except TiempoAgotado as exc:
            raise ErrorDescarga("tiempo agotado: la página no pidió o no recibió los datos") from exc
        except ErrorPlaywright as exc:
            raise ErrorDescarga(f"error del navegador: {str(exc).splitlines()[0][:200]}") from exc

        if respuesta.status != 200:
            raise ErrorDescarga(f"la API de Carroya respondió HTTP {respuesta.status}")
        try:
            return respuesta.json()
        except Exception as exc:
            raise ErrorDescarga("la respuesta de la API no es JSON válido") from exc

    # -- lo que usa el recolector ----------------------------------------------------------
    def obtener_busqueda(self, pagina: int) -> dict:
        """Abre la página N de resultados y devuelve el JSON con los anuncios."""
        def es_la_busqueda(respuesta) -> bool:
            if config.API_BUSQUEDA not in respuesta.url or respuesta.request.method != "POST":
                return False
            pedida = pagina_de_la_peticion(respuesta.request.post_data)
            return pedida is None or pedida == pagina
        return self._abrir_y_capturar(self.url_busqueda.format(pagina=pagina), es_la_busqueda)

    def obtener_detalle(self, url: str, id_anuncio: str) -> dict:
        """Abre la ficha de un anuncio y devuelve el JSON con sus datos."""
        return self._abrir_y_capturar(url, lambda r: f"{config.API_DETALLE}{id_anuncio}" in r.url)


def esperar_conexion(host: str = "www.carroya.com", puerto: int | tuple[int, ...] = 443,
                     max_espera_s: float = config.ESPERA_INTERNET_MAX_S, intervalo_s: float = 15,
                     registrar=print) -> bool:
    """Espera a que haya internet antes de empezar.

    A las 8:00 el Mac puede venir de estar dormido y tardar unos segundos o minutos en
    conectarse al wifi. En lugar de fallar de inmediato, se intenta abrir una conexión
    con el sitio cada 'intervalo_s' segundos, hasta 'max_espera_s'. Devuelve True si hay conexión.
    'puerto' puede ser una lista de puertos. Basta con que uno conecte (el correo usa 465 o 587,
    porque algunas redes bloquean uno de los dos).
    """
    puertos = tuple(puerto) if isinstance(puerto, (tuple, list)) else (puerto,)
    inicio = time.monotonic()
    intento = 0
    while True:
        intento += 1
        error = None
        for p in puertos:
            try:
                with socket.create_connection((host, p), timeout=10):
                    if intento > 1:
                        registrar(f"Conexión con {host} lista después de {time.monotonic() - inicio:.0f} s.")
                    return True
            except OSError as exc:
                error = exc
        esperado = time.monotonic() - inicio
        if esperado >= max_espera_s:
            registrar(f"Sin conexión con {host} después de {esperado:.0f} s ({error}).")
            return False
        if intento == 1:
            registrar(f"Todavía no hay conexión con {host} ({error}); se reintenta cada {intervalo_s:.0f} s.")
        time.sleep(intervalo_s)


class FuenteNoDisponible:
    """Fuente que siempre falla. Sirve para registrar ordenadamente un día en que
    ni siquiera se pudo preparar el navegador."""

    def __init__(self, motivo: str):
        self.motivo = motivo

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def obtener_busqueda(self, pagina: int) -> dict:
        raise ErrorDescarga(self.motivo)

    def obtener_detalle(self, url: str, id_anuncio: str) -> dict:
        raise ErrorDescarga(self.motivo)

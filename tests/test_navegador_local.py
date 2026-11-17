"""Prueba del navegador real (Playwright + Chromium) contra un Carroya de mentira en localhost.

No toca internet. Un servidor local imita cómo funciona Carroya: la página carga
vacía y su JavaScript pide los datos a la API. Así se prueba de verdad la parte
que abre páginas y captura la respuesta JSON. Si Chromium no está instalado,
la prueba se salta (instálelo con: python -m playwright install chromium).
"""
import json
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import pytest

from corolla import paso1_recoleccion as recoleccion
from corolla.paso5_bitacora import Bitacora
from corolla.paso1_navegador import ErrorDescarga, NavegadorCarroya
from corolla.simulacion import Mercado

FECHA = date(2026, 11, 12)

PAGINA_BUSQUEDA = """<!doctype html><html><body><div id=root>cargando</div><script>
const page = new URLSearchParams(location.search).get('page') || '1';
const pedir = (p) => fetch('/find-filters', {method: 'POST', headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({seoArray: [], params: {page: p, brand: 'Toyota', model: 'Corolla',
  modelRange: '2022-2026'}, isReqForRedirect: false})});
pedir('99');                                   // petición señuelo de otra página: debe ignorarse
setTimeout(() => pedir(page).then(r => r.json()).then(d => {
  document.getElementById('root').textContent = d.count; }), 200);
</script><img src="/foto.jpg"></body></html>"""

PAGINA_DETALLE = """<!doctype html><html><body><div id=root></div><script>
const id = location.pathname.split('/').pop();
fetch('/find-vehicle-detail/' + id).then(r => r.text()).then(t => {
  document.getElementById('root').textContent = t.length; });
</script></body></html>"""


@pytest.fixture(scope="module")
def sitio():
    mercado = Mercado(semilla=21, n_inicial=25)
    falla = sorted(i for i, a in mercado.activos.items() if a["model"] == "Corolla")[0]
    fotos_pedidas = []

    class Manejador(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _responder(self, codigo, cuerpo, tipo):
            datos = cuerpo.encode() if isinstance(cuerpo, str) else cuerpo
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)

        def do_GET(self):
            ruta = urlparse(self.path).path
            if ruta.startswith("/automoviles-y-camionetas/"):
                self._responder(200, PAGINA_BUSQUEDA, "text/html; charset=utf-8")
            elif ruta.startswith("/detalle/"):
                self._responder(200, PAGINA_DETALLE, "text/html; charset=utf-8")
            elif ruta.startswith("/find-vehicle-detail/"):
                id_anuncio = ruta.rsplit("/", 1)[-1]
                if id_anuncio == falla:
                    self._responder(500, '{"error": "interno"}', "application/json")
                else:
                    self._responder(200, json.dumps(mercado.respuesta_detalle(id_anuncio)), "application/json")
            elif ruta == "/foto.jpg":
                fotos_pedidas.append(ruta)
                self._responder(200, b"\xff\xd8\xff", "image/jpeg")
            else:
                self._responder(404, "no", "text/plain")

        def do_POST(self):
            cuerpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            pagina = int(cuerpo["params"]["page"])
            respuesta = {"count": 0, "pages": 0, "results": {}} if pagina == 99 else mercado.respuesta_busqueda(pagina)
            self._responder(200, json.dumps(respuesta), "application/json")

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{servidor.server_port}", mercado, falla, fotos_pedidas
    servidor.shutdown()


def test_navegador_captura_el_json_que_recibe_la_pagina(sitio, rutas):
    base, mercado, falla, fotos = sitio
    navegador = NavegadorCarroya(
        url_busqueda=base + "/automoviles-y-camionetas/toyota/corolla?page={pagina}&modelRange=2022-2026",
        pausa=(0, 0), tiempo_limite_ms=15_000)
    try:
        navegador._abrir()
    except ErrorDescarga as exc:
        pytest.skip(f"Chromium no disponible en este equipo: {exc}")

    with navegador:
        segunda = navegador.obtener_busqueda(2)
        assert segunda["count"] == 26 and len(segunda["results"]["superHighlights"]) == 6  # no la señuelo
        bitacora = Bitacora(rutas, "PRUEBA-NAV", "recoleccion", FECHA, consola=False)
        manifiesto = recoleccion.ejecutar_paso_1(
            navegador, rutas, FECHA, "PRUEBA-NAV", bitacora, set(), espera_reintentos=(0, 0),
            plantilla_detalle=base + "/detalle/{estado}/{marca}/{linea}/{anio}/{ciudad}/{id}")

    assert manifiesto["busqueda_completa"] and manifiesto["paginas_leidas"] == [1, 2]
    assert manifiesto["descargas"] == {"sin intentar": 0, "descargado": 24, "fallido": 1}
    datos = {f["id_anuncio"]: f for f in recoleccion.leer_csv(rutas.datos(FECHA))}
    assert "HTTP 500" in datos[falla]["motivo_error"]
    assert not fotos  # las imágenes se bloquean para no descargar de más


def test_recoleccion_completa_con_el_navegador_real(sitio, rutas, monkeypatch):
    """El camino que usa el Mac a las 8:00 (sin fuente simulada): espera de internet,
    navegador real y respaldo con ventana, pasos 1, 3 y 6 y el estado del día."""
    from corolla import flujo
    from corolla import paso1_navegador

    base, mercado, falla, fotos = sitio
    esperas = []
    monkeypatch.setattr(flujo, "esperar_conexion", lambda **k: esperas.append(k) or True)
    creados = []

    class NavegadorLocal(paso1_navegador.NavegadorCarroya):
        def __init__(self, con_ventana=None, **k):
            creados.append(con_ventana)
            super().__init__(con_ventana=False, pausa=(0, 0), tiempo_limite_ms=15_000,
                             url_busqueda=base + "/automoviles-y-camionetas/toyota/corolla?page={pagina}")

    monkeypatch.setattr(flujo, "NavegadorCarroya", NavegadorLocal)
    try:
        with NavegadorLocal() as prueba:   # se cierra al salir; dos Playwright abiertos a la vez chocan
            prueba._abrir()
    except ErrorDescarga as exc:
        pytest.skip(f"Chromium no disponible en este equipo: {exc}")
    creados.clear()

    estado = flujo.ejecutar_recoleccion(
        rutas, FECHA, espera_reintentos=(0, 0), consola=False, origen="programado",
        plantilla_detalle=base + "/detalle/{estado}/{marca}/{linea}/{anio}/{ciudad}/{id}")
    assert len(esperas) == 1                      # esperó internet antes de empezar
    assert creados == [None]                      # la primera página funcionó; no hizo falta el respaldo
    assert estado["origen"] == "programado"
    assert estado["metricas"]["enlaces_encontrados"] == 25 and estado["metricas"]["descargas_exitosas"] == 24
    assert estado["etapas"]["analisis"]["estado"] in ("ok", "con_advertencias")
    assert rutas.bd.exists()

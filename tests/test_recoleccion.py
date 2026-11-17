from datetime import date

from corolla import paso1_recoleccion as recoleccion
from corolla.paso5_bitacora import Bitacora
from corolla.paso1_navegador import ErrorDescarga
from corolla.simulacion import FuenteSimulada, Mercado
from datos_api import ID_1, ID_2, busqueda, detalle, tarjeta

FECHA = date(2026, 11, 12)
SIN_ESPERA = (0, 0)


class FuenteFija:
    """Fuente mínima: páginas y fichas definidas a mano."""

    def __init__(self, paginas, detalles, fallan=()):
        self.paginas, self.detalles, self.fallan = paginas, detalles, set(fallan)

    def obtener_busqueda(self, pagina):
        if pagina not in self.paginas:
            raise ErrorDescarga("HTTP 500")
        return self.paginas[pagina]

    def obtener_detalle(self, url, id_anuncio):
        if id_anuncio in self.fallan:
            raise ErrorDescarga("tiempo agotado")
        return self.detalles[id_anuncio]


def test_recorre_todas_las_paginas_y_no_repite():
    mercado = Mercado(semilla=1, n_inicial=45)
    resultado = recoleccion.buscar_enlaces(FuenteSimulada(mercado), set(), registrar=lambda m: None,
                                           espera_reintentos=SIN_ESPERA)
    assert resultado.paginas_esperadas == 3 and sorted(resultado.paginas_ok) == [1, 2, 3]
    assert resultado.completa
    assert len(resultado.enlaces) == 45                 # el Corolla Cross queda descartado
    assert len(resultado.descartados) == 1 and "línea" in resultado.descartados[0]["motivo"]


def test_pagina_que_falla_deja_busqueda_incompleta():
    mercado = Mercado(semilla=1, n_inicial=45)
    fuente = FuenteSimulada(mercado, paginas_que_fallan={2})
    resultado = recoleccion.buscar_enlaces(fuente, set(), registrar=lambda m: None, espera_reintentos=SIN_ESPERA)
    assert not resultado.completa
    assert 2 in resultado.paginas_fallidas and "páginas sin leer" in resultado.motivo_incompleta


def test_estados_y_archivos_del_paso_1(rutas):
    paginas = {1: busqueda([tarjeta(ID_1), tarjeta(ID_2, anio=2023)], pages=1)}
    fuente = FuenteFija(paginas, {ID_1: detalle(ID_1), ID_2: detalle(ID_2, year=2023)}, fallan={ID_2})
    bitacora = Bitacora(rutas, "PRUEBA-REC-1", "recoleccion", FECHA, consola=False)
    manifiesto = recoleccion.ejecutar_paso_1(fuente, rutas, FECHA, "PRUEBA-REC-1", bitacora, {ID_1},
                                             espera_reintentos=SIN_ESPERA)
    enlaces = {f["id_anuncio"]: f for f in recoleccion.leer_csv(rutas.enlaces(FECHA))}
    datos = {f["id_anuncio"]: f for f in recoleccion.leer_csv(rutas.datos(FECHA))}

    assert manifiesto["busqueda_completa"] and manifiesto["descargas"] == {
        "sin intentar": 0, "descargado": 1, "fallido": 1}
    assert enlaces[ID_1]["es_nuevo"] is False and enlaces[ID_2]["es_nuevo"] is True
    # el fallido guarda su motivo y su hora, y sus campos del vehículo quedan vacíos
    assert datos[ID_2]["estado_descarga"] == "fallido" and "tiempo agotado" in datos[ID_2]["motivo_error"]
    assert datos[ID_2]["fecha_hora_descarga"] and datos[ID_2]["precio"] is None
    assert enlaces[ID_2]["intentos"] == 3
    assert datos[ID_1]["estado_descarga"] == "descargado" and datos[ID_1]["precio"] == 116900000
    assert datos[ID_1]["moneda"] == "COP"
    # las horas llevan la zona explícita
    assert datos[ID_1]["fecha_hora_descarga"].endswith("-05:00")
    # crudos guardados y sin datos personales
    crudo = (rutas.crudos_dia(FECHA) / f"detalle_{ID_1}.json").read_text(encoding="utf-8")
    assert "seller" not in crudo and "ABC123" not in crudo


def test_sin_intentar_deja_hora_vacia(rutas):
    paginas = {1: busqueda([tarjeta(ID_1), tarjeta(ID_2)], pages=1)}
    fuente = FuenteFija(paginas, {ID_1: detalle(ID_1), ID_2: detalle(ID_2)})
    bitacora = Bitacora(rutas, "PRUEBA-REC-2", "recoleccion", FECHA, consola=False)
    recoleccion.ejecutar_paso_1(fuente, rutas, FECHA, "PRUEBA-REC-2", bitacora, set(), max_anuncios=1,
                                espera_reintentos=SIN_ESPERA)
    datos = {f["id_anuncio"]: f for f in recoleccion.leer_csv(rutas.datos(FECHA))}
    enlaces = {f["id_anuncio"]: f for f in recoleccion.leer_csv(rutas.enlaces(FECHA))}
    assert datos[ID_2]["estado_descarga"] == "sin intentar"
    assert datos[ID_2]["fecha_hora_descarga"] is None and enlaces[ID_2]["fecha_hora_ultimo_intento"] is None


def test_falla_transitoria_se_recupera_con_reintento(rutas):
    mercado = Mercado(semilla=2, n_inicial=5)
    primero = sorted(i for i, a in mercado.activos.items() if a["model"] == "Corolla")[0]
    fuente = FuenteSimulada(mercado, fallas_transitorias={primero})
    bitacora = Bitacora(rutas, "PRUEBA-REC-3", "recoleccion", FECHA, consola=False)
    manifiesto = recoleccion.ejecutar_paso_1(fuente, rutas, FECHA, "PRUEBA-REC-3", bitacora, set(),
                                             espera_reintentos=SIN_ESPERA)
    assert manifiesto["descargas"]["fallido"] == 0
    enlaces = {f["id_anuncio"]: f for f in recoleccion.leer_csv(rutas.enlaces(FECHA))}
    assert enlaces[primero]["intentos"] == 2

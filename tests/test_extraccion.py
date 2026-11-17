import pytest

from corolla import paso1_extraccion as extraccion
from datos_api import ID_1, ID_2, busqueda, detalle, tarjeta


def test_anuncios_de_busqueda_toma_solo_anuncios_y_sin_repetir():
    respuesta = busqueda([tarjeta(ID_1), tarjeta(ID_2), tarjeta(ID_1)])
    anuncios = extraccion.anuncios_de_busqueda(respuesta)
    assert [a["id"] for a in anuncios] == [ID_1, ID_2]       # ignora los filtros y el repetido


def test_url_detalle_como_la_arma_carroya():
    item = tarjeta(ID_1, anio=2023, ciudad="BOGOTÁ")
    assert extraccion.url_detalle(item) == f"https://www.carroya.com/detalle/usado/toyota/corolla/2023/bogota/{ID_1}"


def test_moneda_y_numeros_sin_inventar():
    assert extraccion.moneda_normalizada("PESO") == "COP"
    assert extraccion.moneda_normalizada("") is None
    assert extraccion.numero_o_nada("116.900.000") == 116900000
    assert extraccion.numero_o_nada("") is None
    assert extraccion.numero_o_nada(None) is None
    assert extraccion.numero_o_nada(0) == 0          # un cero publicado se conserva como cero


@pytest.mark.parametrize("marca, linea, anio, esperado", [
    ("Toyota", "Corolla", 2022, True), ("Toyota", "Corolla", 2026, True),
    ("Toyota", "Corolla", 2021, False), ("Toyota", "Corolla Cross", 2024, False),
    ("Mazda", "Corolla", 2024, False), ("Toyota", "Corolla", None, False),
])
def test_criterios(marca, linea, anio, esperado):
    assert extraccion.verificar_criterios(marca, linea, anio)[0] is esperado


def test_campos_detalle_basicos():
    fila = extraccion.campos_detalle(detalle(), ID_1, {"moneda": "COP"})
    assert fila["precio"] == 116900000 and fila["moneda"] == "COP"
    assert fila["kilometraje"] == 14000 and fila["transmision"] == "Automática"
    assert fila["version"] == "1.8 CVT SEG" and fila["ciudad"] == "Medellin"
    assert fila["cumple_criterios"] is True


def test_campos_faltantes_quedan_vacios():
    fila = extraccion.campos_detalle(detalle(version="", box="", kilometers=None), ID_1)
    assert fila["version"] is None and fila["transmision"] is None and fila["kilometraje"] is None
    assert fila["moneda"] is None          # sin tarjeta no hay moneda: no se inventa


def test_sunroof_tres_estados():
    con = extraccion.campos_detalle(detalle(accessories=[" Alarma", " Techo corredizo"]), ID_1)
    sin = extraccion.campos_detalle(detalle(accessories=[" Alarma", " GPS"]), ID_1)
    nada = extraccion.campos_detalle(detalle(accessories=[], comments=""), ID_1)
    assert (con["sunroof"], sin["sunroof"], nada["sunroof"]) == (True, False, None)
    assert con["accesorios"] == "Alarma; Techo corredizo"    # sin espacios sobrantes


def test_sunroof_desde_comentarios_sin_guardarlos():
    fila = extraccion.campos_detalle(detalle(comments="Tiene sunroof y rines"), ID_1)
    assert fila["sunroof"] is True and fila["sunroof_fuente"] == "comentarios del vendedor"
    assert "comentarios" not in fila


def test_detalle_vacio_o_de_otro_anuncio_falla():
    with pytest.raises(ValueError):
        extraccion.campos_detalle({"data": None}, ID_1)
    with pytest.raises(ValueError):
        extraccion.campos_detalle(detalle(ID_2), ID_1)


@pytest.mark.parametrize("version, nivel", [
    ("1.8 CVT SEG", "SEG"), ("SE-G Automatico", "SEG"), ("1.8 XE-i  Automatico", "XEI"),
    ("1.8 XEi-L Automatico", "XEI"), ("XEI 2.0 Sedan Manual", "XEI"), ("1.8 XL-i Automatico", "XLI"),
    ("GR-S 2.0 Deportivo Manual Gasolina", "GR-S"), ("1.8", "sin identificar"), (None, "sin identificar"),
])
def test_nivel_version(version, nivel):
    assert extraccion.nivel_version(version) == nivel


def test_sanitizar_quita_datos_personales():
    limpio = extraccion.sanitizar(detalle())
    datos = limpio["data"]
    for clave in ("seller", "plate", "comments", "images"):
        assert clave not in datos
    assert "loginContact" not in limpio
    tarjeta_limpia = extraccion.sanitizar(tarjeta())
    assert not any(k in tarjeta_limpia for k in ("csellername", "cselleremail", "cplaca"))
    assert tarjeta_limpia["price"] == 116900000

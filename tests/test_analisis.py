import math
import random

import pandas as pd
import pytest

from corolla import paso6_analisis as analisis
from corolla.simulacion import precio_justo


def mercado_sintetico(n=60, semilla=11, rebajas=None):
    """Tabla con la forma de las observaciones del día. 'rebajas' = {posición: fracción}."""
    rng = random.Random(semilla)
    versiones = [("1.8 CVT SEG", "SEG"), ("1.8 XE-i Automatico", "XEI"), ("1.8 XL-i Automatico", "XLI")]
    filas = []
    for i in range(n):
        anio = rng.choice([2022, 2022, 2023, 2023, 2023, 2024, 2025, 2026])
        version, nivel = versiones[i % 3]
        km = max(1000, round(rng.gauss(12000 * (2026 - anio) + 6000, 6000), -2))
        precio = precio_justo(anio, km, nivel, "Híbrido") * math.exp(rng.gauss(0, 0.04))
        precio *= 1 - (rebajas or {}).get(i, 0)
        filas.append({"id_anuncio": f"id-{i:03d}", "url": f"https://x/{i}", "anio": anio, "version": version,
                      "kilometraje": km, "precio": round(precio, -5), "moneda": "COP", "transmision": "Automática",
                      "combustible": "Híbrido", "ciudad": "BOGOTA", "sunroof": None, "es_nuevo": True,
                      "cumple_criterios": 1})
    return pd.DataFrame(filas)


def test_detecta_la_ganga_y_la_explica():
    tabla = mercado_sintetico(rebajas={7: 0.22})
    d, modelo, _ = analisis.evaluar(tabla)
    fila = d.set_index("id_anuncio").loc["id-007"]
    assert fila["clasificacion"] == analisis.POSIBLE_GANGA
    assert fila["descuento"] >= analisis.DESCUENTO_MINIMO and fila["z"] <= analisis.Z_LIMITE
    assert fila["n_comparables"] >= analisis.MIN_COMPARABLES
    assert "por debajo" in fila["explicacion"] and "millones" in fila["explicacion"]
    assert modelo is not None and not modelo.simplificado


def test_no_basta_con_ser_el_mas_barato():
    """El carro más barato del día (un 2022 con muchos km) no es ganga si su precio es normal para él."""
    tabla = mercado_sintetico()
    d, _, _ = analisis.evaluar(tabla)
    mas_barato = d.loc[d["precio"].idxmin()]
    assert mas_barato["clasificacion"] not in analisis.ALERTAS


def test_rebaja_enorme_se_marca_para_verificar():
    tabla = mercado_sintetico(rebajas={4: 0.55})
    d, _, _ = analisis.evaluar(tabla)
    fila = d.set_index("id_anuncio").loc["id-004"]
    assert fila["clasificacion"] == analisis.SOSPECHOSO
    assert "verificarlo" in fila["explicacion"]


def test_precios_invalidos_se_excluyen_con_motivo():
    tabla = mercado_sintetico()
    tabla.loc[0, "precio"] = 1_500_000           # error de digitación
    tabla.loc[1, "moneda"] = None
    tabla.loc[2, "precio"] = None
    d, _, _ = analisis.evaluar(tabla)
    motivos = d.set_index("id_anuncio")["motivo_invalido"]
    assert "error de digitación" in motivos["id-000"]
    assert motivos["id-001"] == "moneda no informada" and motivos["id-002"] == "sin precio publicado"
    assert (d.set_index("id_anuncio").loc[["id-000", "id-001", "id-002"], "clasificacion"] == analisis.INVALIDO).all()


def test_kilometraje_faltante_no_se_inventa():
    tabla = mercado_sintetico()
    tabla.loc[3, "kilometraje"] = None
    d, _, _ = analisis.evaluar(tabla)
    fila = d.set_index("id_anuncio").loc["id-003"]
    assert fila["clasificacion"] == analisis.NO_EVALUABLE and "kilometraje" in fila["motivo_no_evaluable"]


def test_pocos_datos_modelo_simplificado_o_ninguno():
    _, modelo, notas = analisis.evaluar(mercado_sintetico(n=12))
    assert modelo is not None and modelo.simplificado
    d, modelo, notas = analisis.evaluar(mercado_sintetico(n=6))
    assert modelo is None and (d["clasificacion"] == analisis.NO_EVALUABLE).all()


def test_pocos_comparables_no_genera_alerta():
    tabla = mercado_sintetico(rebajas={9: 0.25})
    tabla.loc[9, "version"] = "GR-S 2.0 Deportivo"   # única en su nivel
    tabla.loc[10, "version"] = "GR-S 2.0 Deportivo"
    tabla.loc[11, "version"] = "GR-S 2.0 Deportivo"
    d, _, _ = analisis.evaluar(tabla)
    assert d.set_index("id_anuncio").loc["id-009", "clasificacion"] not in analisis.ALERTAS


@pytest.mark.parametrize("texto, esperado", [("Automática", 1.0), ("Secuencial", 1.0), ("Mecánica", 0.0)])
def test_transmision(texto, esperado):
    assert analisis.clasificar_transmision(texto) == esperado


def test_estadisticas_basicas():
    st = analisis.estadisticas(pd.Series([10, 20, 30, 40, 50]))
    assert st["n"] == 5 and st["mediana"] == 30 and st["q1"] == 20 and st["q3"] == 40

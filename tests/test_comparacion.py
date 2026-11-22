"""Pruebas de la comparación entre modelos (corolla/comparacion.py) y de la revisión de la entrega.

Se arman tres bases pequeñas a mano, con precios fáciles de calcular, para comprobar que
la comparación usa el mismo día para todos, compara por año del modelo y no modifica nada.
"""
import json
from datetime import date

import pytest

import taller
from corolla import comparacion
from corolla import configuracion as config
from corolla import paso8_entrega
from corolla.paso2_base_de_datos import conectar

M = 1_000_000


def _base(rutas, filas, cambios=()):
    """filas son (id, fecha, año, precio en millones, km, combustible)."""
    con = conectar(rutas.bd)
    for id_, fecha, anio, precio, km, combustible in filas:
        con.execute("INSERT INTO observaciones (id_anuncio, fecha, disponibilidad, cumple_criterios, anio, "
                    "precio, kilometraje, combustible) VALUES (?, ?, 'encontrado', 1, ?, ?, ?, ?)",
                    (id_, fecha, anio, precio * M, km, combustible))
    for id_, fecha, antes, despues in cambios:
        con.execute("INSERT INTO cambios (id_anuncio, fecha, campo, valor_anterior, valor_nuevo) "
                    "VALUES (?, ?, 'precio', ?, ?)", (id_, fecha, str(antes * M), str(despues * M)))
    con.commit()
    con.close()


@pytest.fixture
def tres_modelos(tmp_path):
    raiz = tmp_path / "datos"
    corolla, mazda, kia = (r for _, r in comparacion.fuentes("oficial", raiz))
    # El Corolla tiene un día más (el 18) que los otros dos. El día común más reciente es el 20.
    filas_corolla = []
    for fecha in ("2026-11-18", "2026-11-19", "2026-11-20"):
        for i, (anio, precio, km) in enumerate([(2022, 90, 60000), (2022, 94, 50000), (2023, 100, 40000),
                                               (2023, 104, 35000), (2024, 110, 30000), (2024, 114, 25000),
                                               (2025, 120, 20000), (2025, 124, 15000), (2026, 130, 8000),
                                               (2026, 134, 5000)]):
            filas_corolla.append((f"c{i}", fecha, anio, precio, km, "Híbrido" if i % 2 else "Gasolina"))
    _base(corolla, filas_corolla)
    filas_mazda = [(f"m{i}", fecha, anio, precio, km, "Gasolina")
                   for fecha in ("2026-11-19", "2026-11-20")
                   for i, (anio, precio, km) in enumerate([(2022, 85, 60000), (2023, 92, 40000), (2024, 99, 30000),
                                                          (2025, 104, 20000), (2026, 110, 6000), (2022, 87, 55000),
                                                          (2023, 94, 38000), (2024, 101, 28000), (2025, 106, 18000),
                                                          (2026, 112, 5000)])]
    _base(mazda, filas_mazda, cambios=[("m0", "2026-11-20", 86, 85)])
    filas_kia = [(f"k{i}", fecha, anio, precio, km, "Gasolina")
                 for fecha in ("2026-11-19", "2026-11-20")
                 for i, (anio, precio, km) in enumerate([(2025, 84, 20000), (2025, 86, 15000), (2025, 88, 10000),
                                                        (2026, 90, 5000), (2026, 92, 3000), (2025, 85, 18000),
                                                        (2026, 91, 4000), (2025, 87, 12000), (2026, 89, 6000),
                                                        (2025, 83, 25000)])]
    _base(kia, filas_kia)
    (corolla.reporte(date(2026, 11, 20))).mkdir(parents=True)
    (corolla.reporte(date(2026, 11, 20)) / "resumen_2026-11-20.json").write_text(json.dumps(
        {"alertas": [{"id_anuncio": "c0", "clasificacion": "posible ganga"},
                     {"id_anuncio": "c1", "clasificacion": "precio sospechosamente bajo"}]}), encoding="utf-8")
    return raiz


def test_compara_el_mismo_dia_y_por_anio_del_modelo(tres_modelos, tmp_path):
    resultado = comparacion.comparar("oficial", raiz_datos=tres_modelos, destino=tmp_path / "salida")
    assert resultado["dia"] == "2026-11-20"                       # el último día que tienen los tres
    assert resultado["periodo_comun"] == ["2026-11-19", "2026-11-20"]
    corolla, mazda, kia = resultado["modelos"]
    assert [m["modelo"] for m in resultado["modelos"]] == ["Toyota Corolla", "Mazda 3", "Kia K3"]
    assert corolla["anuncios"] == 10 and corolla["dias_con_datos"] == 3
    assert corolla["precio_mediana"] == pytest.approx(112 * M)
    assert corolla["por_anio"]["2022"] == {"n": 2, "mediana": pytest.approx(92 * M)}
    assert corolla["hibridos_pct"] == pytest.approx(0.5)
    # Mazda 3 2022 frente al Corolla 2022, 86 contra 92 millones
    fila = next(f for f in resultado["mismo_anio"] if f["modelo"] == "Mazda 3" and f["anio"] == 2022)
    assert fila["diferencia_pct"] == pytest.approx(86 / 92 - 1)
    # El Kia K3 solo tiene dos años, así que solo se compara en 2025 y 2026 y se avisa
    assert sorted(f["anio"] for f in resultado["mismo_anio"] if f["modelo"] == "Kia K3") == [2025, 2026]
    assert "poco confiable" in kia["efectos"]["nota"]
    assert corolla["efectos"]["por_anio_pct"] > 0                 # más nuevo, más caro
    # Movimiento del periodo común y gangas del análisis diario (las sospechosas no cuentan)
    assert mazda["bajadas_precio"] == 1 and mazda["subidas_precio"] == 0
    assert corolla["gangas"]["distintas"] == 1


def test_el_modelo_comun_recupera_los_efectos_de_anio_y_kilometraje():
    # Precios armados con una regla conocida, 5 % por año más nuevo y elasticidad de -0,04 al kilometraje
    anuncios = [{"anio": anio, "km": km, "precio": 100 * M * 1.05 ** (anio - 2024) * (km / 30000) ** -0.04}
                for anio in range(2022, 2027) for km in (5000, 20000, 45000)]
    efectos = comparacion.efectos_precio(anuncios)
    assert efectos["por_anio_pct"] == pytest.approx(0.05)
    assert efectos["doble_km_pct"] == pytest.approx(2 ** -0.04 - 1)
    assert efectos["r2"] == pytest.approx(1.0) and efectos["nota"] is None
    assert comparacion.efectos_precio(anuncios[:5])["por_anio_pct"] is None     # muy pocos anuncios


def test_escribe_tabla_detalle_y_grafica_sin_tocar_las_bases(tres_modelos, tmp_path):
    bases = [r.bd for _, r in comparacion.fuentes("oficial", tres_modelos)]
    antes = [b.read_bytes() for b in bases]
    salida = tmp_path / "salida"
    resultado = comparacion.comparar("oficial", raiz_datos=tres_modelos, destino=salida)
    assert [b.read_bytes() for b in bases] == antes               # solo lectura
    assert (salida / "comparacion_modelos.png").stat().st_size > 10_000
    tabla = (salida / "comparacion_modelos.csv").read_text(encoding="utf-8").splitlines()
    assert tabla[0].startswith("modelo,dia,anuncios,precio_mediana") and len(tabla) == 4
    assert json.loads((salida / "comparacion_modelos.json").read_text(encoding="utf-8"))["dia"] == "2026-11-20"
    texto = "\n".join(comparacion.texto(resultado))
    assert "Mazda 3 2022 está 6,5 % más barato que el Corolla del mismo año" in texto
    assert "1 bajada y 0 subidas de precio" in texto


def test_sin_datos_de_otro_modelo_lo_dice(tmp_path):
    raiz = tmp_path / "datos"
    corolla = comparacion.fuentes("oficial", raiz)[0][1]
    _base(corolla, [("c1", "2026-11-20", 2024, 110, 30000, "Híbrido")])
    with pytest.raises(RuntimeError, match="al menos dos modelos"):
        comparacion.comparar("oficial", raiz_datos=raiz, destino=tmp_path / "salida")


def test_comando_comparar(tres_modelos, monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("COROLLA_DATOS", str(tres_modelos))
    monkeypatch.setattr(config, "RAIZ_PROYECTO", tmp_path)
    assert taller.main(["comparar"]) == 0
    salida = capsys.readouterr().out
    assert "Comparación del viernes 20 de noviembre de 2026" in salida
    assert (tmp_path / "entrega" / "comparacion" / "comparacion_modelos.png").exists()


def test_el_dia_perdido_es_un_incidente_documentado_y_no_algo_que_falta(tmp_path):
    raiz = tmp_path / "taller2-corolla"
    rutas = config.Rutas("oficial", raiz / "datos")
    rutas.crear()
    for dia in range(17, 22):
        for archivo in (rutas.enlaces(date(2026, 11, dia)), rutas.datos(date(2026, 11, dia))):
            archivo.write_text("x")
    conectar(rutas.bd).close()
    recibidos = raiz / "entrega" / "correos_recibidos"
    recibidos.mkdir(parents=True)
    for dia in range(17, 22):
        (recibidos / f"correo_2026-11-{dia}.pdf").write_text("pdf")
    (raiz / "entrega" / "documento_una_pagina.pdf").write_text("pdf")
    assert paso8_entrega.revisar(raiz) == []                       # el 16 no aparece como faltante
    assert "16 de noviembre" in paso8_entrega.notas(raiz)[0]
    (recibidos / "correo_2026-11-21.pdf").unlink()
    assert paso8_entrega.revisar(raiz) == ["en entrega/correos_recibidos hay 4 correos exportados y se esperan 5"]
    for dia in range(17, 21):
        (recibidos / f"correo_2026-11-{dia}.pdf").unlink(missing_ok=True)
    (recibidos / "correo_2026-11-17.pdf").write_text("pdf")
    assert paso8_entrega.revisar(raiz) == ["en entrega/correos_recibidos hay 1 correo exportado y se esperan 5"]

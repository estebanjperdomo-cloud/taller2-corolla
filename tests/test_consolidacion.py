import sqlite3
from contextlib import closing
from datetime import date, timedelta

from corolla import paso1_recoleccion as recoleccion
from corolla import paso2_base_de_datos as base
from corolla import paso3_actualizacion as consolidacion
from corolla.paso5_bitacora import Bitacora
from corolla.simulacion import FuenteSimulada, Mercado

DIA_1 = date(2026, 11, 12)
DIA_2 = DIA_1 + timedelta(days=1)
DIA_3 = DIA_1 + timedelta(days=2)


def correr_dia(rutas, mercado, fecha, **fallas):
    bitacora = Bitacora(rutas, f"PRUEBA-REC-{fecha:%d}", "recoleccion", fecha, consola=False)
    conocidos = base.ids_conocidos(rutas.bd, fecha)
    recoleccion.ejecutar_paso_1(FuenteSimulada(mercado, **fallas), rutas, fecha, f"R{fecha:%d}", bitacora,
                                conocidos, espera_reintentos=(0, 0))
    return consolidacion.procesar_dia(rutas.bd, rutas.datos(fecha), rutas.manifiesto(fecha))


def consulta(rutas, sql, *params):
    with closing(sqlite3.connect(rutas.bd)) as con:
        return con.execute(sql, params).fetchall()


def test_primer_dia_todo_agregado(rutas):
    mercado = Mercado(semilla=3, n_inicial=30)
    metricas = correr_dia(rutas, mercado, DIA_1)
    assert metricas["registros_agregados"] == 30 and metricas["registros_actualizados"] == 0
    assert metricas["anuncios_unicos"] == 30
    assert consulta(rutas, "SELECT COUNT(*) FROM observaciones")[0][0] == 30


def test_procesar_dos_veces_no_duplica(rutas):
    mercado = Mercado(semilla=3, n_inicial=30)
    primera = correr_dia(rutas, mercado, DIA_1)
    segunda = consolidacion.procesar_dia(rutas.bd, rutas.datos(DIA_1), rutas.manifiesto(DIA_1))
    assert segunda["ya_procesado"] is True
    for clave in ("registros_agregados", "registros_actualizados", "registros_sin_cambios", "anuncios_unicos"):
        assert segunda[clave] == primera[clave]
    assert consulta(rutas, "SELECT COUNT(*) FROM observaciones")[0][0] == 30
    assert consulta(rutas, "SELECT COUNT(*) FROM anuncios")[0][0] == 30


def test_reprocesar_un_dia_modificado_reemplaza_sin_duplicar(rutas):
    mercado = Mercado(semilla=3, n_inicial=30)
    correr_dia(rutas, mercado, DIA_1)
    correr_dia(rutas, mercado, DIA_2)
    # Se "re-ejecuta" el día 2 con un precio distinto: cambia el archivo, no se duplica nada.
    mercado.bajar_precios(1)
    correr_dia(rutas, mercado, DIA_2)
    assert consulta(rutas, "SELECT COUNT(*) FROM observaciones WHERE fecha = ?", DIA_2.isoformat())[0][0] == 30
    assert consulta(rutas, "SELECT COUNT(*) FROM anuncios")[0][0] == 30
    assert consulta(rutas, "SELECT COUNT(*) FROM cambios WHERE campo = 'precio'")[0][0] == 1


def test_cambios_y_disponibilidad_en_busqueda_completa(rutas):
    mercado = Mercado(semilla=4, n_inicial=30)
    correr_dia(rutas, mercado, DIA_1)
    salen = mercado.retirar(2)
    mercado.bajar_precios(3)
    nuevo = mercado.agregar()
    metricas = correr_dia(rutas, mercado, DIA_2)
    assert metricas["registros_agregados"] == 1
    assert metricas["no_encontrados"] == 2 and metricas["disponibilidad_desconocida"] == 0
    filas = dict(consulta(rutas, "SELECT id_anuncio, disponibilidad_actual FROM anuncios"))
    assert all(filas[i] == "no_encontrado" for i in salen) and filas[nuevo["id"]] == "encontrado"
    assert consulta(rutas, "SELECT COUNT(*) FROM cambios WHERE fecha = ? AND campo = 'precio'",
                    DIA_2.isoformat())[0][0] == 3
    # un anuncio que no apareció conserva su primera y última fecha vista
    primera, ultima = consulta(rutas, "SELECT primera_fecha_visto, ultima_fecha_visto FROM anuncios "
                                      "WHERE id_anuncio = ?", salen[0])[0]
    assert primera == ultima == DIA_1.isoformat()


def test_busqueda_incompleta_marca_disponibilidad_desconocida(rutas):
    mercado = Mercado(semilla=5, n_inicial=50)
    correr_dia(rutas, mercado, DIA_1)
    metricas = correr_dia(rutas, mercado, DIA_2, paginas_que_fallan={3})
    assert metricas["disponibilidad_desconocida"] > 0 and metricas["no_encontrados"] == 0


def test_falla_de_descarga_no_borra_datos_ni_disponibilidad(rutas):
    mercado = Mercado(semilla=6, n_inicial=20)
    correr_dia(rutas, mercado, DIA_1)
    victima = sorted(i for i, a in mercado.activos.items() if a["model"] == "Corolla")[0]
    precio_dia_1 = consulta(rutas, "SELECT precio FROM anuncios WHERE id_anuncio = ?", victima)[0][0]
    correr_dia(rutas, mercado, DIA_2, ids_que_fallan={victima})
    fila = consulta(rutas, "SELECT disponibilidad_actual, precio, fecha_datos FROM anuncios WHERE id_anuncio = ?",
                    victima)[0]
    assert fila == ("encontrado", precio_dia_1, DIA_1.isoformat())      # sigue disponible; datos del día 1
    obs = consulta(rutas, "SELECT estado_descarga, motivo_error, precio FROM observaciones "
                          "WHERE id_anuncio = ? AND fecha = ?", victima, DIA_2.isoformat())[0]
    assert obs[0] == "fallido" and "HTTP 500" in obs[1] and obs[2] is None


def test_reconstruir_desde_archivos_da_lo_mismo(rutas):
    mercado = Mercado(semilla=7, n_inicial=25)
    correr_dia(rutas, mercado, DIA_1)
    mercado.retirar(1)
    mercado.bajar_precios(2)
    correr_dia(rutas, mercado, DIA_2)
    mercado.regresar_uno()
    correr_dia(rutas, mercado, DIA_3)
    antes = consulta(rutas, "SELECT * FROM anuncios ORDER BY id_anuncio")
    cambios = consulta(rutas, "SELECT id_anuncio, fecha, campo, valor_anterior, valor_nuevo FROM cambios ORDER BY 1, 2, 3")
    consolidacion.reconstruir_desde_archivos(rutas.bd, rutas.diarios)
    assert consulta(rutas, "SELECT * FROM anuncios ORDER BY id_anuncio") == antes
    assert consulta(rutas, "SELECT id_anuncio, fecha, campo, valor_anterior, valor_nuevo FROM cambios "
                           "ORDER BY 1, 2, 3") == cambios
    # el anuncio que volvió registra el cambio de disponibilidad
    assert consulta(rutas, "SELECT COUNT(*) FROM cambios WHERE campo = 'disponibilidad' AND valor_nuevo = "
                           "'encontrado'")[0][0] == 1

"""Pruebas del paso 4 (programación en el Mac), de los comandos de taller.py y del paso 8.

Se pueden correr en cualquier computador: las llamadas a launchctl se reemplazan por
una función falsa que solo anota lo que se le pidió.
"""
import os
import plistlib
import socket
import time
import zipfile
from datetime import date, datetime

import pytest

import taller
from corolla import configuracion as config
from corolla import estado as estado_mod
from corolla import flujo, paso4_programacion as p4, paso8_entrega, verificacion
from corolla.paso1_navegador import esperar_conexion
from corolla.simulacion import FuenteSimulada, Mercado

DIA = date(2026, 11, 13)


@pytest.fixture
def zona(monkeypatch):
    """Cambia la zona horaria del 'sistema' durante una prueba."""
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset no existe en Windows; esta prueba es para el Mac")

    def cambiar(nombre):
        monkeypatch.setenv("TZ", nombre)
        time.tzset()
    yield cambiar
    monkeypatch.delenv("TZ", raising=False)
    time.tzset()


# --- Paso 4 ---------------------------------------------------------------------------------
def test_plist_de_la_recoleccion(tmp_path, zona):
    zona("America/Bogota")
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / ".venv" / "bin" / "python").write_text("")
    contenido = p4.contenido_plist("recoleccion", raiz=tmp_path)
    assert contenido["Label"] == "co.uniandes.taller2corolla.recoleccion"
    assert contenido["ProgramArguments"][:3] == ["/usr/bin/caffeinate", "-i", "-s"]
    assert contenido["ProgramArguments"][3] == str(tmp_path / ".venv" / "bin" / "python")
    assert contenido["ProgramArguments"][4:] == [str(tmp_path / "taller.py"), "recolectar", "--programado"]
    assert contenido["StartCalendarInterval"] == {"Hour": 8, "Minute": 0}
    assert contenido["WorkingDirectory"] == str(tmp_path)
    assert plistlib.loads(plistlib.dumps(contenido)) == contenido  # es un plist válido


def test_si_el_mac_no_esta_en_hora_de_bogota_se_convierte(zona):
    zona("UTC")
    assert p4.hora_local("recoleccion") == (13, 0)
    assert p4.hora_local("correo") == (16, 0)
    zona("America/Bogota")
    assert p4.hora_local("correo") == (11, 0)


def test_instalar_carga_las_dos_tareas(tmp_path, monkeypatch):
    llamadas = []
    monkeypatch.setattr(p4.sys, "platform", "darwin")
    monkeypatch.setattr(p4.Path, "home", lambda: tmp_path / "casa")
    monkeypatch.setattr(p4, "_launchctl", lambda *a: llamadas.append(a) or
                        type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    creados = p4.instalar(raiz=tmp_path, registrar=lambda m: None)
    assert [r.name for r in creados] == ["co.uniandes.taller2corolla.recoleccion.plist",
                                         "co.uniandes.taller2corolla.correo.plist"]
    assert [a[0] for a in llamadas] == ["bootout", "bootstrap", "bootout", "bootstrap"]
    correo = plistlib.loads(creados[1].read_bytes())
    assert correo["ProgramArguments"][-2:] == ["correo", "--programado"]
    assert (tmp_path / "datos" / "launchd").is_dir()


def test_programar_fuera_de_un_mac_explica_por_que_no(monkeypatch):
    monkeypatch.setattr(p4.sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="solo funciona en macOS"):
        p4.instalar(registrar=lambda m: None)


def test_estado_lee_lo_que_dice_launchctl(tmp_path, monkeypatch):
    salida = "gui/501/co.uniandes.taller2corolla.recoleccion = {\n\tstate = not running\n\truns = 3\n" \
             "\tlast exit code = 0\n}"
    monkeypatch.setattr(p4.sys, "platform", "darwin")
    monkeypatch.setattr(p4, "_launchctl", lambda *a: type("R", (), {"returncode": 0, "stdout": salida})())
    fila = p4.estado(raiz=tmp_path)[0]
    assert fila["cargada"] and fila["estado"] == "not running"
    assert fila["veces_ejecutada"] == "3" and fila["ultimo_codigo_salida"] == "0"


def test_proximas_ejecuciones_indican_el_modo():
    domingo = datetime(2026, 11, 15, 7, 0, tzinfo=config.ZONA_HORARIA)
    lineas = p4.proximas_ejecuciones(domingo, cantidad=3)
    assert "domingo 15 de noviembre" in lineas[0] and "recolectar en modo prueba" in lineas[0]
    assert "correo en modo prueba" in lineas[1]
    assert "lunes 16 de noviembre" in lineas[2] and "modo oficial" in lineas[2]
    despues = p4.proximas_ejecuciones(datetime(2026, 11, 21, 12, 0, tzinfo=config.ZONA_HORARIA))
    assert all("no hace nada" in linea for linea in despues)


# --- Comandos de taller.py ------------------------------------------------------------------------
def test_tarea_programada_despues_del_periodo_no_hace_nada(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("COROLLA_DATOS", str(tmp_path))
    with config.reloj_simulado(datetime(2026, 11, 22, 8, 0, tzinfo=config.ZONA_HORARIA)):
        assert taller.main(["recolectar", "--programado"]) == 0
        assert taller.main(["correo", "--programado"]) == 0
    assert "terminó" in capsys.readouterr().out
    assert not (tmp_path / "oficial").exists() and not (tmp_path / "prueba").exists()


def test_modo_de_los_comandos():
    parser = taller.construir_parser()
    assert taller._modo(parser.parse_args(["paso3"])) == "prueba"
    assert taller._modo(parser.parse_args(["paso3", "--modo", "oficial"])) == "oficial"
    with config.reloj_simulado(datetime(2026, 11, 17, 8, 0, tzinfo=config.ZONA_HORARIA)):
        assert taller._modo(parser.parse_args(["recolectar", "--programado"]), True) == "oficial"
        assert taller._modo(parser.parse_args(["recolectar"]), True) == "prueba"


def test_pasos_por_separado_desde_la_linea_de_comandos(monkeypatch, tmp_path, capsys):
    """paso1 (simulado), luego paso3, consultar, paso6, paso7 y log con taller.py."""
    monkeypatch.setenv("COROLLA_DATOS", str(tmp_path))
    rutas = config.Rutas("prueba")
    dia = flujo.Dia(rutas, DIA, consola=False)
    fuente = FuenteSimulada(Mercado(semilla=21, n_inicial=30))
    flujo.correr_paso1(dia, crear_fuente=lambda: fuente, espera_reintentos=(0, 0))
    dia.bitacora.cerrar()
    assert estado_mod.leer(rutas, DIA)["estado"] == estado_mod.EN_CURSO

    assert taller.main(["paso3", "--fecha", DIA.isoformat()]) == 0
    assert taller.main(["paso3", "--fecha", DIA.isoformat()]) == 0           # repetirlo no duplica
    assert '"ya_procesado": true' in capsys.readouterr().out
    assert taller.main(["consultar"]) == 0
    assert "1. Anuncios únicos encontrados en el periodo  (30 filas" in capsys.readouterr().out
    assert taller.main(["paso6", "--fecha", DIA.isoformat()]) == 0
    assert "Precios válidos del día: 30" in capsys.readouterr().out
    assert estado_mod.leer(rutas, DIA)["estado"] == estado_mod.COMPLETADA   # el paso 6 cerró el día
    assert taller.main(["paso7", "--fecha", DIA.isoformat(), "--sin-enviar"]) == 0
    assert "[PRUEBA] Corolla 2022 a 2026" in capsys.readouterr().out
    assert taller.main(["log", "--fecha", DIA.isoformat()]) == 0
    salida = capsys.readouterr().out
    assert "consolidacion" in salida and "correo" in salida and "Modo prueba" in salida


# --- Robustez de la ejecución diaria ---------------------------------------------------------------
def test_repetir_el_dia_guarda_los_archivos_anteriores(rutas):
    mercado = Mercado(semilla=22, n_inicial=20)
    for _ in range(2):
        flujo.ejecutar_recoleccion(rutas, DIA, crear_fuente=lambda: FuenteSimulada(mercado),
                                   espera_reintentos=(0, 0), consola=False)
    apartados = list(rutas.reemplazados.glob(f"{DIA.isoformat()}_reemplazado_*"))
    assert len(apartados) == 1 and (apartados[0] / f"datos_{DIA.isoformat()}.csv").exists()
    from corolla.paso2_base_de_datos import conectar
    con = conectar(rutas.bd)
    assert con.execute("SELECT COUNT(*) FROM observaciones").fetchone()[0] == 20  # sin duplicados
    con.close()


def test_si_falla_la_primera_pagina_se_usa_el_navegador_de_respaldo(rutas):
    mercado = Mercado(semilla=23, n_inicial=20)
    estado = flujo.ejecutar_recoleccion(
        rutas, DIA, crear_fuente=lambda: FuenteSimulada(mercado, paginas_que_fallan={1}),
        crear_fuente_respaldo=lambda: FuenteSimulada(mercado), espera_reintentos=(0, 0), consola=False)
    assert estado["estado"] == estado_mod.COMPLETADA
    assert estado["metricas"]["uso_navegador_respaldo"] is True
    assert estado["metricas"]["enlaces_encontrados"] == 20


def test_esperar_conexion(monkeypatch):
    intentos = []

    class Conexion:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def conectar(*a, **k):
        intentos.append(1)
        if len(intentos) < 3:
            raise OSError("sin red")
        return Conexion()

    monkeypatch.setattr(socket, "create_connection", conectar)
    assert esperar_conexion(intervalo_s=0, registrar=lambda m: None) is True and len(intentos) == 3
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(OSError("no")))
    assert esperar_conexion(max_espera_s=0, intervalo_s=0, registrar=lambda m: None) is False


# --- Verificación y entrega ------------------------------------------------------------------------
def test_verificar_detecta_carpetas_protegidas_y_env(tmp_path):
    assert verificacion._carpeta(tmp_path / "Users" / "x" / "Documents" / "taller")[0] == verificacion.FALTA
    assert verificacion._carpeta(tmp_path / "taller2-corolla")[0] == verificacion.OK
    assert verificacion._env(tmp_path)[0] == verificacion.FALTA


def test_la_entrega_no_lleva_credenciales_ni_la_demo(tmp_path, monkeypatch):
    monkeypatch.setattr(p4.Path, "home", lambda: tmp_path / "casa")
    raiz = tmp_path / "taller2-corolla"
    for relativa in ("taller.py", "README.md", "datos/oficial/diarios/enlaces_2026-11-16.csv",
                     "datos/prueba/diarios/enlaces_2026-11-15.csv", "datos/demo/diarios/x.csv",
                     ".venv/bin/python", ".env"):
        (raiz / relativa).parent.mkdir(parents=True, exist_ok=True)
        (raiz / relativa).write_text("contenido")
    monkeypatch.setenv("SMTP_PASSWORD", "abcd efgh ijkl mnop")
    zip_, faltantes = paso8_entrega.empaquetar(raiz)
    nombres = zipfile.ZipFile(zip_).namelist()
    assert "taller2-corolla/taller.py" in nombres
    assert "taller2-corolla/datos/oficial/diarios/enlaces_2026-11-16.csv" in nombres
    assert "taller2-corolla/datos/prueba/diarios/enlaces_2026-11-15.csv" in nombres
    assert not any(n.endswith(".env") or "/.venv/" in n or "/demo/" in n for n in nombres)
    assert any("correos exportados" in f for f in faltantes)

    (raiz / "README.md").write_text("la clave es abcdefghijklmnop")
    with pytest.raises(RuntimeError, match="contraseña del correo aparece"):
        paso8_entrega.empaquetar(raiz)

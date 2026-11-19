"""Pruebas de los modelos adicionales (Mazda 3, Kia K3) y del envío confiable del correo.

No usan internet: los modelos adicionales se simulan cambiando la marca y la línea de los
anuncios del Carroya simulado, y el servidor de correo se reemplaza por uno falso.
"""
import copy
import hashlib
import json
import smtplib
from datetime import date, datetime
from email.message import EmailMessage

import pytest

import taller
from corolla import configuracion as config
from corolla import estado as estado_mod
from corolla import flujo, paso1_extraccion as extraccion, paso7_correo as correo
from corolla.simulacion import FuenteSimulada, Mercado

DIA = date(2026, 11, 13)
MAZDA_3 = next(b for b in config.MODELOS_EXTRA if b.clave == "mazda-3")
KIA_K3 = next(b for b in config.MODELOS_EXTRA if b.clave == "kia-k3")


class FuenteDeMarca(FuenteSimulada):
    """Carroya simulado que mezcla varias líneas de una marca, por si la página de un
    modelo llegara a traer otro carro (por ejemplo un Kia K3 Cross en la de Kia K3)."""

    def __init__(self, mercado, marca, lineas):
        super().__init__(mercado)
        self.marca, self.lineas = marca, lineas

    def _linea(self, id_anuncio):
        return self.lineas[int(hashlib.md5(id_anuncio.encode()).hexdigest(), 16) % len(self.lineas)]

    def obtener_busqueda(self, pagina):
        respuesta = copy.deepcopy(super().obtener_busqueda(pagina))
        for item in extraccion.anuncios_de_busqueda(respuesta):
            item["brand"], item["model"] = self.marca, self._linea(str(item["id"]))
        return respuesta

    def obtener_detalle(self, url, id_anuncio):
        respuesta = copy.deepcopy(super().obtener_detalle(url, id_anuncio))
        respuesta["data"]["brand"], respuesta["data"]["model"] = self.marca, self._linea(id_anuncio)
        return respuesta


# --- Criterios de los modelos adicionales ---------------------------------------------------------
@pytest.mark.parametrize("marca, linea, anio, esperado", [
    ("Mazda", "3", 2023, True),
    ("MAZDA", "Mazda 3", 2024, True),
    ("Mazda", "MAZDA3 Sport", 2022, True),
    ("Mazda", "CX-30", 2024, False),
    ("Mazda", "CX-3", 2024, False),
    ("Mazda", "3", 2019, False),
    ("Kia", "3", 2023, False),
])
def test_criterios_mazda_3(marca, linea, anio, esperado):
    assert extraccion.verificar_criterios(marca, linea, anio, MAZDA_3)[0] is esperado


@pytest.mark.parametrize("marca, linea, anio, esperado", [
    ("Kia", "K3", 2025, True),
    ("KIA", "Kia K3 GT-Line", 2026, True),
    ("Kia", "K3 Cross", 2025, False),
    ("Kia", "Picanto", 2024, False),
])
def test_criterios_kia_k3(marca, linea, anio, esperado):
    assert extraccion.verificar_criterios(marca, linea, anio, KIA_K3)[0] is esperado


def test_el_corolla_sigue_con_sus_criterios_exactos():
    assert extraccion.verificar_criterios("Toyota", "Corolla", 2024)[0] is True
    assert extraccion.verificar_criterios("Toyota", "Corolla Cross", 2024)[0] is False


def test_las_busquedas_adicionales_usan_la_pagina_del_modelo():
    assert MAZDA_3.url.format(pagina=2) == \
        "https://www.carroya.com/automoviles-y-camionetas/mazda/3?page=2&modelRange=2022-2026"
    assert KIA_K3.url.format(pagina=1) == \
        "https://www.carroya.com/automoviles-y-camionetas/kia/k3?page=1&modelRange=2022-2026"


@pytest.mark.parametrize("version, nivel", [
    ("Touring 2.0 Sedan Automático Hybrid", "Touring"),
    ("2.0 Grand Touring LX Hatchback", "Grand Touring"),
    ("Prime 2.0 Automatico", "Prime"),
    ("GT Line 1.6 Automatico", "GT Line"),
    ("GT-LINE", "GT Line"),
    ("Zenith 2.0 IVT", "Zenith"),
    # el Corolla no cambia
    ("1.8 CVT SEG", "SEG"),
    ("SE-G Automatico", "SEG"),
    ("1.8 XE-i Automatico", "XEI"),
    ("GR-S 2.0", "GR-S"),
    ("Automatico", "sin identificar"),
])
def test_niveles_de_version(version, nivel):
    assert extraccion.nivel_version(version) == nivel


# --- Recolección de los modelos adicionales ----------------------------------------------------------
def test_modelos_adicionales_en_carpetas_separadas_y_en_el_correo(tmp_path, monkeypatch):
    monkeypatch.setenv("COROLLA_DATOS", str(tmp_path))
    mercado_mazda = Mercado(semilla=31, n_inicial=40)
    resumenes = flujo.ejecutar_modelos_extra(
        "prueba", DIA, modelos=[MAZDA_3], consola=False, espera_reintentos=(0, 0),
        crear_fuente_por_modelo={"mazda-3": lambda: FuenteDeMarca(mercado_mazda, "Mazda", ["3", "CX-30"])})
    rutas = config.rutas_modelo(MAZDA_3, "prueba")
    assert rutas.base == tmp_path / "modelos" / "mazda-3" / "prueba"
    assert resumenes[0]["estado"] == estado_mod.COMPLETADA
    assert resumenes[0]["metricas"]["anuncios_validos_analisis"] == resumenes[0]["metricas"]["descargas_exitosas"]
    manifiesto = json.loads(rutas.manifiesto(DIA).read_text(encoding="utf-8"))
    assert manifiesto["criterios"]["modelo"] == "Mazda 3"
    aceptados = manifiesto["enlaces_que_cumplen_criterios"]
    assert 0 < aceptados < 41 and len(manifiesto["descartados_por_criterios"]) == 41 - aceptados
    assert all("CX-30" in d["motivo"] for d in manifiesto["descartados_por_criterios"])
    assert rutas.bd.exists()
    assert not (tmp_path / "prueba").exists()          # el Corolla no se tocó

    # El correo del Corolla incluye la sección de los modelos adicionales
    corolla = config.Rutas("prueba")
    flujo.ejecutar_recoleccion(corolla, DIA, crear_fuente=lambda: FuenteSimulada(Mercado(semilla=32, n_inicial=30)),
                               espera_reintentos=(0, 0), consola=False)
    resultado = flujo.ejecutar_correo(corolla, DIA, enviar=False, consola=False)
    texto = open(resultado["copia"].replace(".eml", ".txt"), encoding="utf-8").read()
    html = open(resultado["copia"].replace(".eml", ".html"), encoding="utf-8").read()
    assert "OTROS MODELOS MONITOREADOS" in texto and "Mazda 3" in texto
    assert "Otros modelos monitoreados (adicional)" in html


def test_si_un_modelo_adicional_falla_no_afecta_a_los_demas(tmp_path, monkeypatch):
    monkeypatch.setenv("COROLLA_DATOS", str(tmp_path))

    def se_cae():
        raise RuntimeError("Carroya cambió la página")

    resumenes = flujo.ejecutar_modelos_extra(
        "prueba", DIA, consola=False, espera_reintentos=(0, 0),
        crear_fuente_por_modelo={"mazda-3": se_cae,
                                 "kia-k3": lambda: FuenteDeMarca(Mercado(semilla=33, n_inicial=20), "Kia",
                                                                 ["K3", "K3 Cross", "Picanto"])})
    estados = {r["clave"]: r["estado"] for r in resumenes}
    assert estados["mazda-3"] == estado_mod.FALLIDA
    assert estados["kia-k3"] != estado_mod.FALLIDA


# --- Envío confiable del correo -------------------------------------------------------------------
class ServidorFalso:
    enviados = []

    def __init__(self, host, puerto, timeout=None, context=None):
        self.puerto = puerto

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self):
        pass

    def has_extn(self, nombre):
        return True

    def starttls(self, context=None):
        pass

    def login(self, usuario, clave):
        pass

    def send_message(self, mensaje, to_addrs=None):
        ServidorFalso.enviados.append(self.puerto)


def _mensaje():
    m = EmailMessage()
    m["Subject"], m["From"], m["To"] = "Prueba", "a@ejemplo.com", "b@ejemplo.com"
    m.set_content("hola")
    return m


@pytest.fixture
def credenciales(monkeypatch):
    for clave, valor in {"SMTP_HOST": "smtp.gmail.com", "SMTP_USER": "a@ejemplo.com",
                         "SMTP_PASSWORD": "abcd efgh ijkl mnop", "EMAIL_TO": "b@ejemplo.com"}.items():
        monkeypatch.setenv(clave, valor)
    monkeypatch.delenv("SMTP_PORT", raising=False)
    ServidorFalso.enviados = []


def test_si_la_red_bloquea_el_465_se_usa_el_587(credenciales, monkeypatch):
    def bloqueado(*a, **k):
        raise ConnectionRefusedError(61, "Connection refused")

    monkeypatch.setattr(smtplib, "SMTP_SSL", bloqueado)
    monkeypatch.setattr(smtplib, "SMTP", ServidorFalso)
    estado, detalle = correo.enviar(_mensaje(), intentos=1)
    assert estado == "enviado" and "puerto 587" in detalle and ServidorFalso.enviados == [587]


def test_un_error_de_contrasena_no_se_trata_como_bloqueo_de_red(credenciales, monkeypatch):
    class ClaveMala(ServidorFalso):
        def login(self, usuario, clave):
            raise smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")

    intentos_587 = []
    monkeypatch.setattr(smtplib, "SMTP_SSL", ClaveMala)
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: intentos_587.append(1))
    estado, detalle = correo.enviar(_mensaje(), intentos=1)
    assert estado == "fallido" and "SMTPAuthenticationError" in detalle and not intentos_587


def test_el_correo_programado_no_se_repite_si_ya_salio(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("COROLLA_DATOS", str(tmp_path))
    rutas = config.Rutas("prueba").crear()
    (rutas.logs / "PRUEBA-COR-20261113-110000.jsonl").write_text(
        json.dumps({"etapa": "correo", "correo_estado": "enviado", "fecha_reporte": "2026-11-13"}) + "\n",
        encoding="utf-8")
    monkeypatch.setattr(flujo, "ejecutar_correo", lambda *a, **k: pytest.fail("no debía volver a enviarse"))
    with config.reloj_simulado(datetime(2026, 11, 13, 11, 30, tzinfo=config.ZONA_HORARIA)):
        assert taller.main(["correo", "--programado"]) == 0
    assert "ya se había enviado" in capsys.readouterr().out


@pytest.mark.parametrize("hora, dia_del_correo", [
    ((11, 0), 20), ((23, 30), 20), ((10, 59), 19), ((7, 0), 19), ((0, 15), 19),
])
def test_a_que_dia_corresponde_el_correo_programado(hora, dia_del_correo):
    momento = datetime(2026, 11, 20, *hora, tzinfo=config.ZONA_HORARIA)
    assert config.fecha_correo_programado(momento) == date(2026, 11, dia_del_correo)


def _correo_falso(enviados):
    def ejecutar_correo(rutas, fecha, enviar=True, consola=True, origen="manual"):
        enviados.append((rutas.modo, fecha, origen))
        return {"run_id": "x", "estado": "enviado", "detalle": "ok", "copia": "copia.eml", "asunto": "x"}
    return ejecutar_correo


def test_si_el_mac_durmio_desde_ayer_sale_el_correo_de_ayer_y_no_el_de_hoy(tmp_path, monkeypatch):
    monkeypatch.setenv("COROLLA_DATOS", str(tmp_path))
    monkeypatch.setattr(config, "ESPERA_RECOLECCION_GRACIA_S", 0)
    enviados = []
    monkeypatch.setattr(flujo, "ejecutar_correo", _correo_falso(enviados))
    # 7:00 del 20. La tarea de las 11:00 del 19 se quedó sin correr y el correo del 19 no salió.
    with config.reloj_simulado(datetime(2026, 11, 20, 7, 0, tzinfo=config.ZONA_HORARIA)):
        assert taller.main(["correo", "--programado"]) == 0
    assert enviados == [("oficial", date(2026, 11, 19), "programado")]


def test_si_el_correo_de_ayer_ya_salio_no_se_envia_nada_antes_de_las_11(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("COROLLA_DATOS", str(tmp_path))
    rutas = config.Rutas("oficial").crear()
    (rutas.logs / "COR-20261119-110002.jsonl").write_text(
        json.dumps({"etapa": "correo", "correo_estado": "enviado"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(flujo, "ejecutar_correo", lambda *a, **k: pytest.fail("no debía enviarse"))
    with config.reloj_simulado(datetime(2026, 11, 20, 7, 0, tzinfo=config.ZONA_HORARIA)):
        assert taller.main(["correo", "--programado"]) == 0
    assert "ya se había enviado" in capsys.readouterr().out


def test_el_correo_espera_a_la_recoleccion_que_esta_corriendo(tmp_path, monkeypatch):
    pytest.importorskip("fcntl")
    import threading
    import time
    monkeypatch.setenv("COROLLA_DATOS", str(tmp_path))
    rutas = config.Rutas("prueba")
    tomado, soltar = threading.Event(), threading.Event()

    def recoleccion():
        with estado_mod.candado_recoleccion(rutas, DIA):
            tomado.set()
            soltar.wait(5)
            estado_mod.guardar(rutas, DIA, estado_mod.nuevo(DIA, "REC", "prueba"))

    hilo = threading.Thread(target=recoleccion)
    hilo.start()
    tomado.wait(5)
    assert estado_mod.recoleccion_en_marcha(rutas, DIA) is True
    threading.Timer(0.5, soltar.set).start()
    inicio = time.monotonic()
    assert estado_mod.esperar_recoleccion(rutas, DIA, intervalo_s=0.05, registrar=lambda m: None) == "lista"
    assert time.monotonic() - inicio >= 0.4                     # sí esperó
    hilo.join()
    assert estado_mod.recoleccion_en_marcha(rutas, DIA) is False


def test_el_correo_no_espera_para_siempre(tmp_path, monkeypatch):
    pytest.importorskip("fcntl")
    monkeypatch.setenv("COROLLA_DATOS", str(tmp_path))
    rutas = config.Rutas("prueba")
    # Sin rastro de recolección: espera solo el periodo de gracia.
    assert estado_mod.esperar_recoleccion(rutas, DIA, gracia_s=0.1, intervalo_s=0.05,
                                          registrar=lambda m: None) == "sin_recoleccion"
    # Con la recolección colgada: espera hasta el máximo y sale igual.
    with estado_mod.candado_recoleccion(rutas, DIA):
        assert estado_mod.esperar_recoleccion(rutas, DIA, max_espera_s=0.2, intervalo_s=0.05,
                                              registrar=lambda m: None) == "sigue_en_curso"
    # Con la recolección terminada: no espera nada.
    estado_mod.guardar(rutas, DIA, estado_mod.nuevo(DIA, "REC", "prueba"))
    assert estado_mod.esperar_recoleccion(rutas, DIA, gracia_s=60, registrar=lambda m: None) == "lista"


def test_basta_con_que_conecte_uno_de_los_dos_puertos(monkeypatch):
    import socket
    from corolla.paso1_navegador import esperar_conexion
    probados = []

    class Conexion:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def conectar(direccion, timeout=None):
        probados.append(direccion[1])
        if direccion[1] == 465:
            raise ConnectionRefusedError(61, "Connection refused")
        return Conexion()

    monkeypatch.setattr(socket, "create_connection", conectar)
    assert esperar_conexion("smtp.gmail.com", (465, 587), max_espera_s=0, registrar=lambda m: None) is True
    assert probados == [465, 587]


def test_el_correo_manual_si_se_puede_repetir(tmp_path, monkeypatch):
    monkeypatch.setenv("COROLLA_DATOS", str(tmp_path))
    rutas = config.Rutas("prueba").crear()
    assert correo.correo_ya_enviado(rutas, DIA) is False
    (rutas.logs / "PRUEBA-COR-20261113-110000.jsonl").write_text(
        json.dumps({"etapa": "correo", "correo_estado": "fallido"}) + "\n", encoding="utf-8")
    assert correo.correo_ya_enviado(rutas, DIA) is False

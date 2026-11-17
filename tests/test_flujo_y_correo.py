import email
import smtplib
from datetime import date, timedelta

from corolla import configuracion as config, estado as estado_mod, flujo
from corolla.simulacion import FuenteSimulada, Mercado

DIA_1 = date(2026, 11, 12)


def recolectar(rutas, mercado, fecha, **fallas):
    fuente = FuenteSimulada(mercado, **fallas)
    return flujo.ejecutar_recoleccion(rutas, fecha, crear_fuente=lambda: fuente, espera_reintentos=(0, 0),
                                      consola=False)


def test_flujo_completo_y_correo_guardado(rutas):
    mercado = Mercado(semilla=8)
    mercado.agregar(rebaja=0.25)
    estado = recolectar(rutas, mercado, DIA_1)
    assert estado["estado"] == "completada"
    assert all(e["estado"] == "ok" for e in estado["etapas"].values())
    resultado = flujo.ejecutar_correo(rutas, DIA_1, enviar=False, consola=False)
    assert resultado["asunto"].startswith("[PRUEBA] Corolla 2022 a 2026 · 12/11/2026")
    mensaje = email.message_from_bytes(open(resultado["copia"], "rb").read())
    html = next(p for p in mensaje.walk() if p.get_content_type() == "text/html").get_payload(decode=True).decode()
    assert "Distribución de precios" in html and "cid:" in html
    assert any(p.get_content_type() == "image/png" for p in mensaje.walk())
    assert "Correo de PRUEBA" in html


def test_logs_tienen_las_columnas_minimas(rutas):
    from corolla.paso5_bitacora import leer_registros
    recolectar(rutas, Mercado(semilla=9, n_inicial=25), DIA_1)
    registros = leer_registros(rutas.logs)
    etapas = {r["etapa"] for r in registros}
    assert {"busqueda", "descarga", "consolidacion", "analisis", "ejecucion_completa"} <= etapas
    for r in registros:
        for campo in ("run_id", "etapa", "inicio", "fin", "duracion_s", "estado"):
            assert r[campo] is not None
        assert r["inicio"].endswith("-05:00")
    final = next(r for r in registros if r["etapa"] == "ejecucion_completa")
    assert final["enlaces_encontrados"] == 25 and final["anuncios_unicos"] == 25
    assert final["tamano_bd_bytes"] > 0


def test_correo_sale_aunque_la_recoleccion_siga_en_curso(rutas):
    estado_mod.guardar(rutas, DIA_1, estado_mod.nuevo(DIA_1, "PRUEBA-REC-X", "prueba"))
    resultado = flujo.ejecutar_correo(rutas, DIA_1, enviar=False, consola=False)
    texto = open(resultado["copia"].replace(".eml", ".txt"), encoding="utf-8").read()
    assert "recolección en curso" in resultado["asunto"]
    assert "todavía no termina" in texto and "análisis del día todavía no existe" in texto


def test_correo_sale_aunque_no_haya_ejecucion(rutas):
    resultado = flujo.ejecutar_correo(rutas, DIA_1, enviar=False, consola=False)
    assert "sin recolección" in resultado["asunto"]


def test_dia_fallido_queda_registrado(rutas):
    estado = recolectar(rutas, Mercado(semilla=10, n_inicial=25), DIA_1, paginas_que_fallan={1})
    assert estado["estado"] == "fallida"
    resultado = flujo.ejecutar_correo(rutas, DIA_1, enviar=False, consola=False)
    assert "recolección fallida" in resultado["asunto"]


def test_segundo_dia_reporta_bajadas_de_precio(rutas):
    mercado = Mercado(semilla=12, n_inicial=40)
    recolectar(rutas, mercado, DIA_1)
    mercado.bajar_precios(4)
    recolectar(rutas, mercado, DIA_1 + timedelta(days=1))
    resultado = flujo.ejecutar_correo(rutas, DIA_1 + timedelta(days=1), enviar=False, consola=False)
    texto = open(resultado["copia"].replace(".eml", ".txt"), encoding="utf-8").read()
    assert "BAJADAS DE PRECIO" in texto


def test_envio_smtp_con_servidor_falso(rutas, monkeypatch):
    enviados = []

    class SMTPFalso:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, usuario, clave):
            assert usuario == "remitente@gmail.com" and clave == "clave-de-aplicacion"

        def send_message(self, mensaje, to_addrs=None):
            enviados.append((mensaje["Subject"], to_addrs))

    monkeypatch.setattr(smtplib, "SMTP_SSL", SMTPFalso)
    monkeypatch.setenv("SMTP_USER", "remitente@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "clave-de-aplicacion")
    monkeypatch.setenv("EMAIL_TO", "destino@gmail.com")
    recolectar(rutas, Mercado(semilla=13, n_inicial=20), DIA_1)
    resultado = flujo.ejecutar_correo(rutas, DIA_1, enviar=True, consola=False)
    assert resultado["estado"] == "enviado" and enviados[0][1] == ["destino@gmail.com"]


def test_sin_credenciales_no_se_envia_pero_queda_copia(rutas, monkeypatch):
    for variable in ("SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO"):
        monkeypatch.delenv(variable, raising=False)
    resultado = flujo.ejecutar_correo(rutas, DIA_1, enviar=True, consola=False)
    assert resultado["estado"] == "no_enviado" and resultado["copia"]


def test_modo_de_las_tareas_programadas_segun_la_fecha():
    assert config.modo_programado(date(2026, 11, 15)) == "prueba"   # la prueba del domingo
    assert config.modo_programado(date(2026, 11, 16)) == "oficial"
    assert config.modo_programado(date(2026, 11, 21)) == "oficial"
    assert config.modo_programado(date(2026, 11, 22)) is None       # después del periodo no corre

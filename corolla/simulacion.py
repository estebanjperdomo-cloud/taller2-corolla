"""Simulador de Carroya para las pruebas y para la demostración sin internet.

Genera un mercado ficticio de Corollas con la MISMA forma de JSON que entrega la
API real (find-filters para la búsqueda y find-vehicle-detail para cada ficha)
y lo hace evolucionar día a día: anuncios nuevos, anuncios que salen, bajadas de
precio, fallas de descarga y una búsqueda incompleta. Todo lo que produce queda
en datos/demo/ y los correos llevan [DEMO] en el asunto.
"""
from __future__ import annotations

import math
import random
import shutil
import uuid
from datetime import datetime, time, timedelta

from . import configuracion as config
from .paso1_navegador import ErrorDescarga

VERSIONES = [  # (versión escrita por el vendedor, combustible, caja, peso de aparición)
    ("1.8 CVT SEG", "Híbrido", "Automática", 13), ("SE-G Automatico", "Híbrido", "Automática", 8),
    ("1.8 XE-i  Automatico", "Híbrido", "Automática", 12), ("1.8 CVT XEI", "Híbrido", "Automática", 4),
    ("1.8 XEi-L Automatico", "Híbrido", "Automática", 3), ("1.8 XL-i Automatico", "Híbrido", "Automática", 5),
    ("XEI 2.0 Sedan Automatico CVT", "Gasolina", "Automática", 2), ("XEI 2.0 Sedan Manual", "Gasolina", "Mecánica", 1),
    ("GR-S 2.0 Deportivo Manual Gasolina", "Gasolina", "Mecánica", 3), ("1.8 Aut", "Híbrido", "Automática", 2),
    ("1.8", "Híbrido", "Automática", 3), (None, "Híbrido", "", 2),
]
EFECTO_NIVEL = {"SEG": 0.08, "XEI": 0.0, "XLI": -0.08, "GR-S": 0.22, "sin identificar": -0.02}
ANIOS = [(2022, 17), (2023, 26), (2024, 5), (2025, 7), (2026, 5)]
CIUDADES = [("BOGOTA", 27), ("MEDELLIN", 21), ("CUCUTA", 2), ("VILLAVICENCIO", 2), ("CALI", 1), ("BARRANQUILLA", 1),
            ("ENVIGADO", 1), ("MANIZALES", 1), ("BUCARAMANGA", 1), ("IBAGUE", 1), ("PASTO", 1), ("BELLO", 1)]
COLORES = ["Gris", "Blanco", "Plateado", "Negro", "Rojo", "Azul"]
ACCESORIOS = ["Air bag delanteros", "Air bag pasajeros", "Alarma", "Bloqueo Central", "Cámara de reversa",
              "Sensor de reversa", "Sensor punto ciego", "Sensores delanteros", "Aire acondicionado",
              "Android Auto", "Apple car play", "Bluetooth", "Espejos eléctricos", "Vidrios eléctricos",
              "Rines de lujo", "Tapicería en cuero", "Velocidad crucero", "GPS"]


def _elegir(rng: random.Random, opciones: list[tuple]):
    return rng.choices(opciones, weights=[o[-1] for o in opciones])[0]


def precio_justo(anio: int, km: float, nivel: str, combustible: str) -> float:
    """Precio 'de mercado' del simulador: baja con la edad y el kilometraje, sube con la versión."""
    precio = 125e6 * 0.93 ** (2025 - anio) * math.exp(-0.06 * math.log(max(km, 1000) / 20000))
    precio *= math.exp(EFECTO_NIVEL[nivel])
    if combustible == "Gasolina" and nivel != "GR-S":
        precio *= 0.94
    return precio


class Mercado:
    """Anuncios activos de un Carroya ficticio."""

    def __init__(self, semilla: int = 7, n_inicial: int = 60):
        from .paso1_extraccion import nivel_version

        self._nivel = nivel_version
        self.rng = random.Random(semilla)
        self.activos: dict[str, dict] = {}
        self.retirados: dict[str, dict] = {}
        self.dia = 0
        for _ in range(n_inicial):
            self.agregar()
        # Un anuncio que no cumple los criterios (otra línea) para probar el filtro.
        intruso = self.agregar()
        intruso["model"] = "Corolla Cross"

    def _uuid(self) -> str:
        return str(uuid.UUID(int=self.rng.getrandbits(128), version=4))

    def agregar(self, rebaja: float = 0.0) -> dict:
        rng = self.rng
        anio = _elegir(rng, ANIOS)[0]
        version, combustible, caja, _ = _elegir(rng, VERSIONES)
        edad = 2026 - anio
        km = max(1000, round(rng.gauss(12000 * edad + 6000, 7000) / 500) * 500)
        nivel = self._nivel(version)
        precio = precio_justo(anio, km, nivel, combustible) * math.exp(rng.gauss(0, 0.055)) * (1 - rebaja)
        accesorios = rng.sample(ACCESORIOS, rng.randint(4, 12)) if rng.random() < 0.6 else []
        if accesorios and rng.random() < 0.2:
            accesorios.append("Techo corredizo")
        anuncio = {
            "id": self._uuid(), "year": anio, "price": int(round(precio / 1e5) * 1e5), "kilometers": km,
            "version": version, "fuel": combustible, "box": caja, "city": _elegir(rng, CIUDADES)[0],
            "color": rng.choice(COLORES), "accessories": accesorios, "model": "Corolla",
            "publicado": self.dia, "orden": rng.random(),
        }
        self.activos[anuncio["id"]] = anuncio
        return anuncio

    def retirar(self, cantidad: int) -> list[str]:
        candidatos = sorted(i for i, a in self.activos.items() if a["model"] == "Corolla")
        salen = self.rng.sample(candidatos, cantidad)
        for i in salen:
            self.retirados[i] = self.activos.pop(i)
        return salen

    def regresar_uno(self) -> str | None:
        if not self.retirados:
            return None
        i = sorted(self.retirados)[0]
        self.activos[i] = self.retirados.pop(i)
        return i

    def bajar_precios(self, cantidad: int) -> None:
        candidatos = sorted(i for i, a in self.activos.items() if a["model"] == "Corolla")
        for i in self.rng.sample(candidatos, cantidad):
            a = self.activos[i]
            a["price"] = int(round(a["price"] * (1 - self.rng.uniform(0.02, 0.07)) / 1e5) * 1e5)

    # -- respuestas con la forma de la API real ------------------------------------------------
    def _ordenados(self) -> list[dict]:
        return sorted(self.activos.values(), key=lambda a: (-a["publicado"], a["orden"]))

    def respuesta_busqueda(self, pagina: int, por_pagina: int = 20) -> dict:
        anuncios = self._ordenados()
        paginas = max(1, math.ceil(len(anuncios) / por_pagina))
        tramo = anuncios[(pagina - 1) * por_pagina: pagina * por_pagina]
        tarjetas = [{
            "id": a["id"], "year": a["year"], "title": f"Toyota {a['model']} {a['year']}", "status": "usado",
            "sold": "N", "price": a["price"], "brand": "Toyota", "model": a["model"], "city": a["city"],
            "kilometers": a["kilometers"], "color": a["color"], "cmodeloint": a["year"], "cprecioint": a["price"],
            "clinea2": a["version"], "ctipocaja": a["box"], "ccombustible": a["fuel"], "ctipomoneda": "PESO",
            "caccesorios": ", ".join(a["accessories"]), "cofrecidopor": "Particular",
            "csellername": "Vendedor simulado", "cselleremail": "vendedor@ejemplo.com", "cplaca": "XXX000",
        } for a in tramo]
        return {"count": len(anuncios), "pages": paginas, "seo": {},
                "results": {"filter-city": [{"name": "Bogotá", "count": 10}], "superHighlights": tarjetas,
                            "megaHighlights": [], "latestReleases": []}}

    def respuesta_detalle(self, id_anuncio: str) -> dict:
        a = self.activos.get(id_anuncio)
        if a is None:
            raise ErrorDescarga("la API de Carroya respondió HTTP 404 (simulado)")
        return {"loginContact": False, "data": {
            "id": a["id"], "title": f"Toyota {a['model']}", "status": "usado", "price": a["price"],
            "brand": "Toyota", "brandCode": "99", "model": a["model"], "version": a["version"] or "",
            "year": a["year"], "kilometers": a["kilometers"], "cylindrical": 20 if "2.0" in (a["version"] or "") else 18,
            "box": a["box"], "fuel": a["fuel"], "steering_system": "", "plate": "XXX000", "plate_city": "Bogota",
            "city": a["city"].title(), "cityCode": "11001", "color": a["color"], "armored": False,
            "code_carroya": a["id"], "accessories": [" " + x for x in a["accessories"]], "featured": 1,
            "sold": "N", "comments": "Carro en excelente estado, único dueño. Llame al 300 000 0000.",
            "seller": {"name": "Vendedor simulado", "whatsapp": "3000000000"}, "publicationStatus": "Publicado",
            "fechapublicacion": "2026-11-01T10:00:00.000+0000", "images": [{"image": "https://ejemplo/foto.jpg"}],
        }}


class FuenteSimulada:
    """Se comporta como NavegadorCarroya, pero responde desde el mercado ficticio."""

    def __init__(self, mercado: Mercado, paginas_que_fallan=(), ids_que_fallan=(), fallas_transitorias=()):
        self.mercado = mercado
        self.paginas_que_fallan = set(paginas_que_fallan)
        self.ids_que_fallan = set(ids_que_fallan)
        self.pendientes_transitorias = {i: 1 for i in fallas_transitorias}
        self.peticiones = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def obtener_busqueda(self, pagina: int) -> dict:
        self.peticiones += 1
        if pagina in self.paginas_que_fallan:
            raise ErrorDescarga("tiempo agotado: la página no pidió o no recibió los datos (simulado)")
        return self.mercado.respuesta_busqueda(pagina)

    def obtener_detalle(self, url: str, id_anuncio: str) -> dict:
        self.peticiones += 1
        if id_anuncio in self.ids_que_fallan:
            raise ErrorDescarga("la API de Carroya respondió HTTP 500 (simulado)")
        if self.pendientes_transitorias.get(id_anuncio, 0) > 0:
            self.pendientes_transitorias[id_anuncio] -= 1
            raise ErrorDescarga("tiempo agotado: la página no pidió o no recibió los datos (simulado)")
        return self.mercado.respuesta_detalle(id_anuncio)


def ejecutar_demo(dias: int = 6, semilla: int = 7, raiz=None, registrar=print) -> config.Rutas:
    """Seis días simulados (16 al 21 de noviembre) con el flujo completo y sus correos."""
    from . import flujo

    rutas = config.Rutas("demo", raiz) if raiz else config.Rutas("demo")
    if rutas.base.exists():
        shutil.rmtree(rutas.base)
    mercado = Mercado(semilla)
    ganga_inicial = mercado.agregar(rebaja=0.20)
    mercado.agregar(rebaja=0.52)                     # precio sospechosamente bajo
    registrar(f"Mercado inicial con {len(mercado.activos)} anuncios (incluye un Corolla Cross que no cumple).")

    for numero in range(dias):
        fecha = config.PERIODO_INICIO + timedelta(days=numero)
        mercado.dia = numero
        falla_paginas, falla_ids, transitorias = (), (), ()
        if numero == 1:
            mercado.retirar(2); [mercado.agregar() for _ in range(2)]; mercado.agregar(rebaja=0.18)
            mercado.bajar_precios(3)
            falla_ids = (sorted(mercado.activos)[5],)
        elif numero == 2:
            mercado.retirar(1); [mercado.agregar() for _ in range(2)]; mercado.bajar_precios(2)
            falla_paginas = (3,)
        elif numero == 3:
            [mercado.agregar() for _ in range(2)]; mercado.regresar_uno(); mercado.bajar_precios(2)
            transitorias = tuple(sorted(mercado.activos)[:2])
        elif numero == 4:
            mercado.retirar(3); [mercado.agregar() for _ in range(3)]; mercado.agregar(rebaja=0.22)
            mercado.bajar_precios(3)
            mercado.activos[ganga_inicial["id"]]["kilometers"] += 1500
        elif numero >= 5:
            mercado.retirar(2); [mercado.agregar() for _ in range(2)]; mercado.bajar_precios(2)

        fuente = FuenteSimulada(mercado, falla_paginas, falla_ids, transitorias)
        with config.reloj_simulado(datetime.combine(fecha, time(8, 0), tzinfo=config.ZONA_HORARIA)):
            estado = flujo.ejecutar_recoleccion(rutas, fecha, crear_fuente=lambda: fuente,
                                                espera_reintentos=(0, 0), consola=False, origen="demo")
        with config.reloj_simulado(datetime.combine(fecha, time(11, 0), tzinfo=config.ZONA_HORARIA)):
            envio = flujo.ejecutar_correo(rutas, fecha, enviar=False, consola=False, origen="demo")
        registrar(f"{fecha} · recolección {estado['estado']} · {estado['metricas'].get('enlaces_encontrados')} "
                  f"enlaces · {estado['metricas'].get('anuncios_nuevos')} nuevos · "
                  f"{estado['metricas'].get('posibles_gangas_nuevas')} gangas nuevas · correo: {envio['asunto']}")
    return rutas

"""Configuración central del monitor de Toyota Corolla en Carroya.

Todo lo que podría cambiar (direcciones, criterios, horarios, periodo y carpetas)
está aquí, para no tener números regados por el código.
"""
from __future__ import annotations

import os
import time as _time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Zona horaria explícita y única para TODOS los registros del sistema.
NOMBRE_ZONA = "America/Bogota"
ZONA_HORARIA = ZoneInfo(NOMBRE_ZONA)

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent

# --- Carroya ----------------------------------------------------------------------
# Búsqueda pública de partida que da el enunciado del taller.
URL_BUSQUEDA = (
    "https://www.carroya.com/automoviles-y-camionetas/toyota/corolla"
    "?page={pagina}&modelRange=2022-2026"
)
# Ficha pública de cada anuncio. El último segmento es el identificador (UUID).
URL_DETALLE = "https://www.carroya.com/detalle/{estado}/{marca}/{linea}/{anio}/{ciudad}/{id}"

# Fragmentos de las direcciones internas que consulta la propia página de Carroya.
# No las llamamos nosotros. El navegador abre la página pública y leemos la
# respuesta que la página recibe (ver paso1_navegador.py).
API_BUSQUEDA = "find-filters"
API_DETALLE = "find-vehicle-detail/"

# Criterios del taller
MARCA = "Toyota"
LINEA = "Corolla"
ANIO_MIN = 2022
ANIO_MAX = 2026

# --- Periodo evaluado y horarios (hora de Colombia) ----------------------------------
PERIODO_INICIO = date(2026, 11, 16)
PERIODO_FIN = date(2026, 11, 21)
HORA_RECOLECCION = time(8, 0)
HORA_CORREO = time(11, 0)

# --- Comportamiento del recolector ----------------------------------------------------
MAX_PAGINAS = 30                       # tope de seguridad
INTENTOS_POR_DESCARGA = 3
ESPERA_ENTRE_REINTENTOS_S = (5.0, 12.0)
PAUSA_ENTRE_PAGINAS_S = (1.5, 3.5)     # pausa amable entre una página y otra
TIEMPO_LIMITE_MS = 45_000
GUARDAR_CADA = 10                      # guardar el progreso cada N descargas
ESPERA_INTERNET_MAX_S = 600            # al despertar, el Mac puede tardar en conectarse al wifi
# Días del periodo oficial sin recolección, contados en docs/incidentes.md. La revisión de la
# entrega los muestra como incidente documentado y no como algo que falta. Nunca se rellenan.
DIAS_SIN_DATOS = {
    date(2026, 11, 16): "el monitor todavía no estaba instalado",
}
ESPERA_RECOLECCION_MAX_S = 3600        # el correo programado espera hasta una hora a la recolección
ESPERA_RECOLECCION_GRACIA_S = 120      # y dos minutos si la recolección todavía no ha arrancado

# --- Búsquedas en Carroya --------------------------------------------------------------------
@dataclass(frozen=True)
class Busqueda:
    """Una búsqueda en Carroya. El Corolla es la del taller; las demás son adicionales.

    linea es la primera palabra de la línea del carro una vez se le quita la marca
    (por ejemplo "3" para Mazda 3 o "k3" para Kia K3). excluir lista palabras que
    indican otro carro aunque empiece igual (por ejemplo "cross" en Kia K3 Cross).
    """

    clave: str
    nombre: str
    marca: str
    linea: str
    url: str
    excluir: tuple = ()
    anio_min: int = ANIO_MIN
    anio_max: int = ANIO_MAX
    max_paginas: int = MAX_PAGINAS


# Cada modelo adicional usa su página pública en Carroya, igual que la del Corolla. Se
# revisaron en el navegador el 18 de noviembre de 2026. Mazda 3 tenía 100 anuncios en 5
# páginas y Kia K3 tenía 38 en 2. Igual cada anuncio se revisa contra la marca, la línea
# y los años, por si la página mezcla otro carro.
URL_MODELO = "https://www.carroya.com/automoviles-y-camionetas/{marca}/{linea}?page={{pagina}}&modelRange=2022-2026"
MODELOS_EXTRA = (
    Busqueda("mazda-3", "Mazda 3", "Mazda", "3", URL_MODELO.format(marca="mazda", linea="3")),
    Busqueda("kia-k3", "Kia K3", "Kia", "k3", URL_MODELO.format(marca="kia", linea="k3"), excluir=("cross",)),
)


# oficial  evidencias del 16 al 21 de noviembre
# prueba   cualquier ejecución manual y las pruebas antes o después del periodo
# demo     seis días simulados, sin internet
MODOS = ("oficial", "prueba", "demo")


# --- Tiempo -------------------------------------------------------------------------
_reloj_simulado = None  # solo lo usa la demostración (simulacion.py)


def ahora() -> datetime:
    """Fecha y hora actual en Bogotá, con su desfase (-05:00)."""
    if _reloj_simulado is not None:
        return _reloj_simulado()
    return datetime.now(ZONA_HORARIA)


@contextmanager
def reloj_simulado(inicio: datetime):
    """Hace que ahora() arranque en 'inicio' y avance con el tiempo real.

    Sirve para que la demostración deje horas del día simulado
    (por ejemplo 2026-11-16T08:00:02-05:00) y no las de hoy.
    """
    global _reloj_simulado
    base = _time.monotonic()
    _reloj_simulado = lambda: inicio + timedelta(seconds=_time.monotonic() - base)  # noqa: E731
    try:
        yield
    finally:
        _reloj_simulado = None


def hoy() -> date:
    return ahora().date()


def iso(momento: datetime | None) -> str | None:
    """Fecha y hora ISO 8601 con zona explícita, por ejemplo 2026-11-16T08:00:03-05:00."""
    if momento is None:
        return None
    return momento.astimezone(ZONA_HORARIA).isoformat(timespec="seconds")


MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre")
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def fecha_larga(fecha: date) -> str:
    """'lunes 16 de noviembre de 2026', sin depender del idioma del sistema."""
    return f"{DIAS[fecha.weekday()]} {fecha.day} de {MESES[fecha.month - 1]} de {fecha.year}"


def modo_programado(fecha: date) -> str | None:
    """Modo de las ejecuciones que lanza el Mac a las 8:00 y a las 11:00.

    Antes del 16 de noviembre son pruebas (así la programación se prueba sola),
    del 16 al 21 son oficiales y después del 21 no se ejecuta nada (None).
    """
    if fecha < PERIODO_INICIO:
        return "prueba"
    if fecha <= PERIODO_FIN:
        return "oficial"
    return None


def fecha_correo_programado(momento: datetime) -> date:
    """De qué día es el correo que le toca a una tarea programada que arranca en 'momento'.

    Si el Mac estaba dormido a la hora de una tarea, launchd la corre apenas se despierta.
    Una tarea del correo que arranca antes de las 11:00 viene del horario de ayer (por
    ejemplo, el Mac durmió desde la tarde hasta la mañana siguiente). Le toca el correo
    de ayer, que quizá no salió, y no el de hoy, cuya recolección todavía no ha corrido.
    """
    momento = momento.astimezone(ZONA_HORARIA)
    if momento.time() >= HORA_CORREO:
        return momento.date()
    return momento.date() - timedelta(days=1)


def nuevo_run_id(tipo: str, modo: str, momento: datetime | None = None) -> str:
    """Identificador de ejecución, legible y ordenable.

    REC-20261116-080002 para la recolección y COR-... para el correo.
    Las ejecuciones que no son oficiales llevan el prefijo PRUEBA- o DEMO-.
    """
    momento = momento or ahora()
    base = f"{tipo}-{momento:%Y%m%d-%H%M%S}"
    return base if modo == "oficial" else f"{modo.upper()}-{base}"


# --- Carpetas y archivos ------------------------------------------------------------
def carpeta_datos() -> Path:
    return Path(os.environ.get("COROLLA_DATOS", RAIZ_PROYECTO / "datos"))


def rutas_modelo(busqueda: "Busqueda", modo: str, raiz: Path | None = None) -> "Rutas":
    """Carpetas de un modelo adicional, separadas del Corolla, en datos/modelos/<clave>/<modo>/.
    Su base lleva el nombre del modelo (mazda_3.sqlite, kia_k3.sqlite). 'raiz' es la carpeta
    datos/ (por defecto la del proyecto)."""
    return Rutas(modo, (raiz or carpeta_datos()) / "modelos" / busqueda.clave,
                 f"{busqueda.clave.replace('-', '_')}.sqlite")


@dataclass(frozen=True)
class Rutas:
    """Dónde queda cada archivo. Cada modo tiene su propia carpeta, así los datos
    de prueba nunca se mezclan con las evidencias oficiales."""

    modo: str
    raiz: Path = field(default_factory=carpeta_datos)
    archivo_bd: str = "corolla.sqlite"     # los modelos adicionales usan el suyo

    def __post_init__(self):
        if self.modo not in MODOS:
            raise ValueError(f"Modo desconocido: {self.modo}. Use uno de {MODOS}")

    @property
    def base(self) -> Path:
        return Path(self.raiz) / self.modo

    @property
    def diarios(self) -> Path:
        return self.base / "diarios"

    @property
    def reemplazados(self) -> Path:
        """Archivos diarios que se reemplazaron al repetir un día (evidencia, no se borran)."""
        return self.diarios / "reemplazados"

    @property
    def crudos(self) -> Path:
        return self.base / "crudos"

    @property
    def consolidado(self) -> Path:
        return self.base / "consolidado"

    @property
    def bd(self) -> Path:
        return self.consolidado / self.archivo_bd

    @property
    def reportes(self) -> Path:
        return self.base / "reportes"

    @property
    def correos(self) -> Path:
        return self.base / "correos"

    @property
    def estado(self) -> Path:
        return self.base / "estado"

    @property
    def logs(self) -> Path:
        return self.base / "logs"

    def crear(self) -> "Rutas":
        for carpeta in (self.diarios, self.crudos, self.consolidado, self.reportes,
                        self.correos, self.estado, self.logs):
            carpeta.mkdir(parents=True, exist_ok=True)
        return self

    # Archivos diarios del paso 1
    def enlaces(self, fecha: date) -> Path:
        return self.diarios / f"enlaces_{fecha.isoformat()}.csv"

    def datos(self, fecha: date) -> Path:
        return self.diarios / f"datos_{fecha.isoformat()}.csv"

    def manifiesto(self, fecha: date) -> Path:
        return self.diarios / f"manifiesto_{fecha.isoformat()}.json"

    def crudos_dia(self, fecha: date) -> Path:
        return self.crudos / fecha.isoformat()

    def archivo_estado(self, fecha: date) -> Path:
        return self.estado / f"ejecucion_{fecha.isoformat()}.json"

    def reporte(self, fecha: date) -> Path:
        return self.reportes / fecha.isoformat()

    def correos_dia(self, fecha: date) -> Path:
        return self.correos / fecha.isoformat()

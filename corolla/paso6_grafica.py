"""Paso 6 del taller. Gráfica diaria de la distribución de precios (va incrustada en el correo).

Arriba, un histograma de los precios válidos del día con la mediana y el 50 %
central (entre el primer y el tercer cuartil). Abajo, cada anuncio como un punto
según el año del modelo, con la mediana de cada año y las alertas resaltadas.
"""
from __future__ import annotations

import math
import zlib
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # sin ventana, así funciona también cuando la lanza el Mac a las 8:00
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import PathPatch  # noqa: E402
from matplotlib.path import Path as Trazo  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator  # noqa: E402

from . import configuracion as config, formato  # noqa: E402

# Paleta validada (azul para anuncios, naranja para alertas) y tintas neutras.
AZUL = "#2a78d6"
NARANJA = "#eb6834"
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
TENUE = "#898781"
REJILLA = "#e1e0d9"
BASE = "#c3c2b7"
BANDA = "#f0efec"
FONDO = "#ffffff"
FUENTES = ["Inter", "Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans"]


def _en_millones(valor, _pos=None) -> str:
    return f"{formato.decimal(valor, 0)} M"


def _barra(ax, x0: float, ancho: float, alto: float, color: str, radio_px: float = 4.0) -> None:
    """Barra con la punta redondeada (4 px) y la base recta sobre el eje."""
    if alto <= 0:
        return
    (px0, py0), (px1, py1) = ax.transData.transform([(x0, 0), (x0 + ancho, alto)])
    ancho_px, alto_px = abs(px1 - px0), abs(py1 - py0)
    r = min(radio_px, ancho_px / 2, alto_px)
    rx, ry = r * ancho / ancho_px, r * alto / alto_px
    vertices = [(x0, 0), (x0, alto - ry), (x0, alto), (x0 + rx, alto), (x0 + ancho - rx, alto),
                (x0 + ancho, alto), (x0 + ancho, alto - ry), (x0 + ancho, 0), (x0, 0)]
    codigos = [Trazo.MOVETO, Trazo.LINETO, Trazo.CURVE3, Trazo.CURVE3, Trazo.LINETO,
               Trazo.CURVE3, Trazo.CURVE3, Trazo.LINETO, Trazo.CLOSEPOLY]
    ax.add_patch(PathPatch(Trazo(vertices, codigos), facecolor=color, edgecolor="none", zorder=3))


def _estilo_ejes(ax) -> None:
    ax.set_facecolor(FONDO)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color(BASE)
    ax.spines["bottom"].set_linewidth(1)
    ax.tick_params(colors=TENUE, labelcolor=TINTA_2, length=0, labelsize=8.5, pad=6)
    ax.grid(axis="y", color=REJILLA, linewidth=0.8)
    ax.set_axisbelow(True)


def distribucion_precios(validos: pd.DataFrame, stats: dict, fecha: date, ruta: Path) -> Path:
    """Dibuja y guarda la gráfica. 'validos' trae una fila por anuncio con precio válido."""
    precios = pd.to_numeric(validos["precio"], errors="coerce").dropna().to_numpy() / 1e6
    alertas = validos[validos["clasificacion"].isin(("posible ganga", "precio sospechosamente bajo"))] \
        if "clasificacion" in validos else validos.iloc[0:0]

    with plt.rc_context({"font.family": "sans-serif", "font.sans-serif": FUENTES,
                         "axes.titlesize": 10, "axes.titleweight": "semibold"}):
        figura = plt.figure(figsize=(6.2, 6.9), dpi=200, facecolor=FONDO)
        # Posiciones fijas (izquierda, abajo, ancho, alto) para que ningún texto se encime.
        arriba = figura.add_axes([0.115, 0.56, 0.855, 0.255])
        abajo = figura.add_axes([0.115, 0.06, 0.855, 0.285])

        # Títulos de la figura (texto alineado a la izquierda, tinta neutra)
        figura.text(0.115, 0.975, "Distribución de precios publicados", fontsize=13,
                    fontweight="semibold", color=TINTA, ha="left", va="top")
        figura.text(0.115, 0.942, f"{config.fecha_larga(fecha).capitalize()} · {stats['n']} anuncios con precio "
                    f"válido · millones de pesos", fontsize=9, color=TINTA_2, ha="left", va="top")

        # --- Histograma -----------------------------------------------------------------------
        _estilo_ejes(arriba)
        ancho_bin = 5.0
        inicio = math.floor(precios.min() / ancho_bin) * ancho_bin
        fin = math.ceil(precios.max() / ancho_bin) * ancho_bin
        if fin <= inicio:
            fin = inicio + ancho_bin
        bordes = np.arange(inicio, fin + ancho_bin / 2, ancho_bin)
        conteos, _ = np.histogram(precios, bins=bordes)
        q1, mediana, q3 = stats["q1"] / 1e6, stats["mediana"] / 1e6, stats["q3"] / 1e6

        arriba.set_xlim(inicio - ancho_bin * 0.3, fin + ancho_bin * 0.3)
        arriba.set_ylim(0, max(conteos.max() * 1.28, 3))
        arriba.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=5))
        arriba.xaxis.set_major_formatter(FuncFormatter(_en_millones))
        arriba.axvspan(q1, q3, color=BANDA, zorder=1, linewidth=0)
        figura.canvas.draw()  # fija la escala para convertir píxeles a datos
        separacion = 2 * (arriba.get_xlim()[1] - arriba.get_xlim()[0]) / arriba.bbox.width
        for borde, conteo in zip(bordes[:-1], conteos):
            _barra(arriba, borde + separacion / 2, ancho_bin - separacion, conteo, AZUL)
        tope = arriba.get_ylim()[1]
        arriba.axvline(mediana, color=TINTA, linewidth=1.5, zorder=4)
        arriba.text(mediana, tope * 0.97, f"  Mediana {formato.millones(stats['mediana'] , 1, ' M')}",
                    color=TINTA, fontsize=8.5, fontweight="semibold", ha="left", va="top", zorder=5)
        arriba.text(q1, tope * 0.86, "Q1 ", color=TENUE, fontsize=8, ha="right", va="top")
        arriba.text(q3, tope * 0.86, " Q3", color=TENUE, fontsize=8, ha="left", va="top")
        arriba.text(0, 1.2, "Histograma de precios", transform=arriba.transAxes, fontsize=10,
                    fontweight="semibold", color=TINTA, ha="left", va="bottom")
        arriba.text(0, 1.1, "Cuántos anuncios hay en cada rango de $5 millones. La franja gris es el 50 % central.",
                    transform=arriba.transAxes, fontsize=8.5, color=TINTA_2, ha="left", va="bottom")
        arriba.set_ylabel("Anuncios", color=TINTA_2, fontsize=8.5)

        # --- Puntos por año del modelo ---------------------------------------------------------
        _estilo_ejes(abajo)
        anios = sorted(int(a) for a in validos["anio"].dropna().unique())
        posiciones = {a: i for i, a in enumerate(anios)}
        abajo.set_xlim(-0.6, len(anios) - 0.4)
        ids_alerta = set(alertas["id_anuncio"]) if len(alertas) else set()
        for _, fila in validos.iterrows():
            if pd.isna(fila["anio"]) or fila["id_anuncio"] in ids_alerta:
                continue
            x = posiciones[int(fila["anio"])] + _desplazamiento(fila["id_anuncio"])
            abajo.scatter(x, fila["precio"] / 1e6, s=26, color=AZUL, edgecolors=FONDO, linewidths=1.0, zorder=3)
        for anio in anios:
            mediana_anio = validos.loc[validos["anio"] == anio, "precio"].median() / 1e6
            x = posiciones[anio]
            abajo.plot([x - 0.28, x + 0.28], [mediana_anio] * 2, color=TINTA, linewidth=2,
                       solid_capstyle="round", zorder=4)
            abajo.text(x + 0.31, mediana_anio, formato.decimal(mediana_anio, 1), color=TINTA_2,
                       fontsize=7.5, va="center", ha="left", zorder=5)
        hay_sospechoso = hay_ganga = False
        for _, fila in alertas.iterrows():
            if pd.isna(fila["anio"]):
                continue
            sospechoso = fila["clasificacion"] == "precio sospechosamente bajo"
            hay_sospechoso |= sospechoso
            hay_ganga |= not sospechoso
            x = posiciones[int(fila["anio"])] + _desplazamiento(fila["id_anuncio"])
            abajo.scatter(x, fila["precio"] / 1e6, s=70, marker="D" if sospechoso else "o", color=NARANJA,
                          edgecolors=FONDO, linewidths=2, zorder=6)
            abajo.annotate(formato.millones(fila["precio"], 1, " M"), (x, fila["precio"] / 1e6),
                           xytext=(8, -2), textcoords="offset points", fontsize=7.5, color=TINTA, va="center",
                           zorder=7)
        abajo.set_xticks(range(len(anios)), [str(a) for a in anios])
        abajo.yaxis.set_major_formatter(FuncFormatter(_en_millones))
        abajo.yaxis.set_major_locator(MaxNLocator(nbins=6))
        abajo.text(0, 1.25, "Precio según el año del modelo", transform=abajo.transAxes, fontsize=10,
                   fontweight="semibold", color=TINTA, ha="left", va="bottom")
        abajo.text(0, 1.155, "Cada punto es un anuncio y la raya negra es la mediana del año.",
                   transform=abajo.transAxes, fontsize=8.5, color=TINTA_2, ha="left", va="bottom")
        leyenda = [Line2D([], [], marker="o", linestyle="", markersize=6, color=AZUL, label="Anuncio"),
                   Line2D([], [], color=TINTA, linewidth=2, label="Mediana del año")]
        if hay_ganga:
            leyenda.append(Line2D([], [], marker="o", linestyle="", markersize=7, color=NARANJA,
                                  label="Posible ganga"))
        if hay_sospechoso:
            leyenda.append(Line2D([], [], marker="D", linestyle="", markersize=6, color=NARANJA,
                                  label="Precio sospechosamente bajo"))
        abajo.legend(handles=leyenda, loc="lower left", fontsize=7.5, frameon=False, ncol=len(leyenda),
                     handletextpad=0.4, columnspacing=1.2, bbox_to_anchor=(-0.01, 1.0), borderaxespad=0.2)
        minimo, maximo = precios.min(), precios.max()
        margen = (maximo - minimo) * 0.08 or 5
        abajo.set_ylim(minimo - margen, maximo + margen)

        ruta.parent.mkdir(parents=True, exist_ok=True)
        figura.savefig(ruta, dpi=200, facecolor=FONDO)
        plt.close(figura)
    return ruta


def _desplazamiento(id_anuncio: str) -> float:
    """Pequeño corrimiento horizontal, siempre el mismo para el mismo anuncio."""
    return (zlib.crc32(str(id_anuncio).encode()) % 1000) / 1000 * 0.4 - 0.2

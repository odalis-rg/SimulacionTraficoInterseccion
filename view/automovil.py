"""Automóvil visto desde arriba para la animación.

Cada automóvil se dibuja con unas pocas piezas (ruedas, carrocería con
espejos, techo, parabrisas y luneta, faros y luces traseras) definidas en
coordenadas locales: centro en el origen y frente hacia +x. Todas comparten
una traslación, así que mover el auto en cada fotograma cuesta una sola
actualización.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass

from matplotlib.artist import Artist
from matplotlib.axes import Axes
from matplotlib.colors import to_hex, to_rgb
from matplotlib.patches import BoxStyle, PathPatch
from matplotlib.path import Path
from matplotlib.transforms import Affine2D

from view.style import PALETA


@dataclass(frozen=True)
class FormaAutomovil:
    """Proporciones del dibujo: posiciones en fracciones del largo (L) y anchos en fracciones del ancho (W)."""

    radio_carroceria: float = 0.32
    rueda: tuple[float, float, float, float] = (0.30, 0.49, 0.20, 0.16)
    """(centro x × L, centro y × W, largo × L, ancho × W) de cada rueda."""
    espejo: tuple[float, float, float, float] = (0.16, 0.53, 0.05, 0.10)
    """(centro x × L, centro y × W, largo × L, ancho × W) de cada espejo."""
    techo: tuple[float, float, float, float] = (-0.20, 0.08, 0.35, 0.12)
    """(x trasera × L, x delantera × L, medio ancho × W, radio × W)."""
    parabrisas: tuple[float, float, float, float] = (0.08, 0.35, 0.25, 0.42)
    """(x del techo × L, medio ancho ahí × W, x del capó × L, medio ancho ahí × W)."""
    luneta: tuple[float, float, float, float] = (-0.33, 0.38, -0.20, 0.35)
    """(x del maletero × L, medio ancho ahí × W, x del techo × L, medio ancho ahí × W)."""
    luz: tuple[float, float, float] = (0.055, 0.30, 0.16)
    """(largo × L, centro y × W, ancho × W) de faros y luces traseras."""
    borde: float = 0.6
    """Grosor (puntos) del contorno de la carrocería."""
    aclarado_techo: float = 0.22
    oscurecido_borde: float = 0.35


FORMA = FormaAutomovil()


@functools.lru_cache(maxsize=None)
def mezclar(color: str, otro: str, proporcion: float) -> str:
    """Color intermedio: ``proporcion`` = 0 devuelve ``color`` y 1 devuelve ``otro``."""
    a, b = to_rgb(color), to_rgb(otro)
    return to_hex(tuple((1 - proporcion) * x + proporcion * y for x, y in zip(a, b)))


def rectangulo(x0: float, y0: float, ancho: float, alto: float) -> Path:
    return Affine2D().scale(ancho, alto).translate(x0, y0).transform_path(Path.unit_rectangle())


def _redondeado(x0: float, y0: float, ancho: float, alto: float, radio: float) -> Path:
    return BoxStyle.Round(pad=0.0, rounding_size=radio)(x0, y0, ancho, alto, 1.0)


def _trapecio(x_a: float, medio_a: float, x_b: float, medio_b: float) -> Path:
    """Trapecio simétrico respecto del eje x, con lados paralelos en x_a y x_b."""
    vertices = [(x_a, -medio_a), (x_b, -medio_b), (x_b, medio_b), (x_a, medio_a), (x_a, -medio_a)]
    return Path(vertices, [Path.MOVETO, Path.LINETO, Path.LINETO, Path.LINETO, Path.CLOSEPOLY])


def _pares(cx: float, cy: float, largo: float, ancho: float, lados_x: tuple[int, ...]) -> Path:
    """Piezas simétricas a ambos lados del eje x (y a ambos extremos si ``lados_x`` = (-1, 1))."""
    return Path.make_compound_path(*(rectangulo(sx * cx - largo / 2, sy * cy - ancho / 2, largo, ancho)
                                     for sx in lados_x for sy in (-1, 1)))


class Automovil:
    """Automóvil reutilizable: se ubica, colorea y oculta en cada fotograma."""

    def __init__(self, ax: Axes, largo: float, ancho: float, zorder: float) -> None:
        f, L, W = FORMA, largo, ancho
        rx, ry, rl, ra = f.rueda
        ex, ey, el, ea = f.espejo
        tx0, tx1, tm, tr = f.techo
        ll, ly, la = f.luz
        carroceria = Path.make_compound_path(
            _redondeado(-L / 2, -W / 2, L, W, f.radio_carroceria * W),
            _pares(ex * L, ey * W, el * L, ea * W, (1,)),
        )
        self._ruedas = PathPatch(_pares(rx * L, ry * W, rl * L, ra * W, (-1, 1)), facecolor=PALETA.neumatico,
                                 edgecolor="none")
        self._carroceria = PathPatch(carroceria, linewidth=f.borde)
        self._techo = PathPatch(_redondeado(tx0 * L, -tm * W, (tx1 - tx0) * L, 2 * tm * W, tr * W), edgecolor="none")
        self._vidrios = PathPatch(Path.make_compound_path(
            _trapecio(f.parabrisas[0] * L, f.parabrisas[1] * W, f.parabrisas[2] * L, f.parabrisas[3] * W),
            _trapecio(f.luneta[0] * L, f.luneta[1] * W, f.luneta[2] * L, f.luneta[3] * W),
        ), facecolor=PALETA.vidrio, edgecolor="none")
        self._faros = PathPatch(_pares((0.5 - ll / 2) * L, ly * W, ll * L, la * W, (1,)), facecolor=PALETA.faro,
                                edgecolor="none")
        self._luces = PathPatch(_pares((0.5 - ll / 2) * L, ly * W, ll * L, la * W, (-1,)), edgecolor="none")
        self.artistas: list[Artist] = [self._ruedas, self._carroceria, self._techo, self._vidrios, self._faros,
                                       self._luces]
        self._traslacion = Affine2D()
        transformacion = self._traslacion + ax.transData
        for orden, pieza in enumerate(self.artistas):
            pieza.set_transform(transformacion)
            pieza.set_zorder(zorder + orden / len(self.artistas))
            pieza.set_visible(False)
            ax.add_patch(pieza)
        self._aspecto: tuple[str, bool] | None = None

    def mostrar(self, x: float, y: float, color: str, frenando: bool, alfa: float) -> None:
        """Ubica el auto con su centro en (x, y); ``frenando`` enciende las luces de freno."""
        self._traslacion.clear().translate(x, y)
        if self._aspecto != (color, frenando):
            self._carroceria.set_facecolor(color)
            self._carroceria.set_edgecolor(mezclar(color, "#000000", FORMA.oscurecido_borde))
            self._techo.set_facecolor(mezclar(color, "#ffffff", FORMA.aclarado_techo))
            self._luces.set_facecolor(PALETA.luz_freno if frenando else PALETA.luz_trasera)
            self._aspecto = (color, frenando)
        for pieza in self.artistas:
            pieza.set_alpha(alfa)
            pieza.set_visible(True)

    def ocultar(self) -> None:
        for pieza in self.artistas:
            pieza.set_visible(False)

"""Partes fijas de la escena: calles, marcas viales, leyenda y semáforo."""

from __future__ import annotations

from matplotlib.artist import Artist
from matplotlib.axes import Axes
from matplotlib.patches import Circle, FancyBboxPatch, PathPatch, Rectangle
from matplotlib.path import Path as MplPath

from model.traffic_light import Fase
from view.animacion.automovil import Automovil, rectangulo
from view.animacion.medidas import DISPOSICION, GEOMETRIA
from view.style import PALETA


def _trazos(inicio: float, fin: float, trazo: float, hueco: float) -> list[tuple[float, float]]:
    """Segmentos (desde, hasta) de una línea discontinua entre ``inicio`` y ``fin``."""
    segmentos, x = [], inicio
    while x < fin:
        segmentos.append((x, min(x + trazo, fin)))
        x += trazo + hueco
    return segmentos


def _franjas(inicio: float, fin: float, franja: float, hueco: float) -> list[float]:
    """Inicio de cada franja de un paso de cebra repartidas entre ``inicio`` y ``fin``."""
    cantidad = int((fin - inicio + hueco) // (franja + hueco))
    sobrante = fin - inicio - cantidad * franja - (cantidad - 1) * hueco
    return [inicio + sobrante / 2 + i * (franja + hueco) for i in range(cantidad)]


def _pintar(ax: Axes, caminos: list[MplPath], color: str, orden: float) -> None:
    """Agrega como una sola pieza estática un conjunto de figuras del mismo color."""
    ax.add_patch(PathPatch(MplPath.make_compound_path(*caminos), facecolor=color, edgecolor="none", zorder=orden))


class Interseccion:
    """Dibuja (una sola vez) manzanas, aceras, calzadas, marcas viales y la leyenda de autos."""

    def __init__(self, ax: Axes, tamano_auto: tuple[float, float]) -> None:
        g = GEOMETRIA
        ax.set_xlim(0, g.largo)
        ax.set_ylim(g.base, g.alto)
        ax.set_aspect("equal")
        ax.axis("off")
        _pintar(ax, [rectangulo(0, 0, g.largo, g.alto)], PALETA.manzana, 0.0)
        _pintar(ax, [rectangulo(0, g.calzada_inferior - g.acera, g.largo, 2 * (g.ancho_carril + g.acera)),
                     rectangulo(g.cruce_inicio - g.acera, 0, g.cruce_ancho + 2 * g.acera, g.alto)], PALETA.acera, 0.1)
        _pintar(ax, [rectangulo(0, g.calzada_inferior, g.largo, 2 * g.ancho_carril),
                     rectangulo(g.cruce_inicio, 0, g.cruce_ancho, g.alto)], PALETA.asfalto, 0.2)
        _pintar(ax, self._marcas_blancas(), PALETA.marca_vial, 0.3)
        _pintar(ax, self._lineas_centrales(), PALETA.linea_central, 0.3)
        self._leyenda(ax, tamano_auto)

    @staticmethod
    def _marcas_blancas() -> list[MplPath]:
        """Bordes de carril, línea de detención, pasos de cebra y flecha del acceso."""
        g = GEOMETRIA
        antes, despues = g.cruce_inicio - g.acera, g.cruce_fin + g.acera
        bajo, sobre = g.calzada_inferior - g.acera, g.calzada_superior + g.acera
        marcas = []
        for y in (g.calzada_inferior + g.retiro_borde, g.calzada_superior - g.retiro_borde - g.grosor_borde):
            marcas += [rectangulo(0, y, antes, g.grosor_borde),
                       rectangulo(despues, y, g.largo - despues, g.grosor_borde)]
        for x in (g.cruce_inicio + g.retiro_borde, g.cruce_fin - g.retiro_borde - g.grosor_borde):
            marcas += [rectangulo(x, 0, g.grosor_borde, bajo), rectangulo(x, sobre, g.grosor_borde, g.alto - sobre)]
        marcas.append(rectangulo(g.linea_detencion - g.grosor_linea, g.calzada_inferior, g.grosor_linea,
                                 g.ancho_carril))
        profundidad = g.acera - 2 * g.retiro_cebra
        for x in (antes + g.retiro_cebra, g.cruce_fin + g.retiro_cebra):
            marcas += [rectangulo(x, y, profundidad, g.franja_cebra) for y in
                       _franjas(g.calzada_inferior, g.calzada_superior, g.franja_cebra, g.hueco_cebra)]
        for y in (bajo + g.retiro_cebra, g.calzada_superior + g.retiro_cebra):
            marcas += [rectangulo(x, y, g.franja_cebra, profundidad) for x in
                       _franjas(g.cruce_inicio, g.cruce_fin, g.franja_cebra, g.hueco_cebra)]
        marcas.append(Interseccion._flecha())
        return marcas

    @staticmethod
    def _flecha() -> MplPath:
        g = GEOMETRIA
        x0, largo, astil, punta = g.flecha
        x1, x2, y = x0 + largo - punta, x0 + largo, g.centro_acceso
        vertices = [(x0, y - astil / 2), (x1, y - astil / 2), (x1, y - punta / 2), (x2, y), (x1, y + punta / 2),
                    (x1, y + astil / 2), (x0, y + astil / 2), (x0, y - astil / 2)]
        return MplPath(vertices, [MplPath.MOVETO] + [MplPath.LINETO] * 6 + [MplPath.CLOSEPOLY])

    @staticmethod
    def _lineas_centrales() -> list[MplPath]:
        """Líneas amarillas discontinuas que separan los sentidos de circulación."""
        g = GEOMETRIA
        trazo, hueco = g.trazo_central
        y = g.calzada_inferior + g.ancho_carril - g.grosor_borde / 2
        x = g.cruce_inicio + g.cruce_ancho / 2 - g.grosor_borde / 2
        tramos_x = (_trazos(0, g.cruce_inicio - g.acera, trazo, hueco)
                    + _trazos(g.cruce_fin + g.acera, g.largo, trazo, hueco))
        tramos_y = (_trazos(0, g.calzada_inferior - g.acera, trazo, hueco)
                    + _trazos(g.calzada_superior + g.acera, g.alto, trazo, hueco))
        return ([rectangulo(a, y, b - a, g.grosor_borde) for a, b in tramos_x]
                + [rectangulo(x, a, g.grosor_borde, b - a) for a, b in tramos_y])

    @staticmethod
    def _leyenda(ax: Axes, tamano_auto: tuple[float, float]) -> None:
        """Autos de ejemplo que explican los colores."""
        x, *renglones = GEOMETRIA.leyenda
        largo, ancho = tamano_auto
        ejemplos = ((PALETA.vehiculo_servicio, False, "En servicio: cruza la intersección"),
                    (PALETA.autos[0], True, "En espera: luces de freno encendidas"))
        for y, (color, frenando, texto) in zip(renglones, ejemplos):
            Automovil(ax, largo, ancho, zorder=3).mostrar(x + largo / 2, y, color, frenando, 1.0)
            ax.text(x + largo * 1.25, y, texto, va="center", fontsize=DISPOSICION.texto_pequeno,
                    color=PALETA.texto_secundario, zorder=5)


class SemaforoDibujado:
    """Semáforo de la esquina (vista frontal) que ilumina la fase activa."""

    def __init__(self, ax: Axes) -> None:
        g = GEOMETRIA
        x = g.linea_detencion - g.retiro_semaforo
        tope = g.semaforo_base + g.semaforo_alto
        acera_media = g.calzada_inferior - g.acera / 2
        ax.add_patch(Rectangle((x - g.grosor_poste / 2, tope), g.grosor_poste, acera_media - tope,
                               facecolor=PALETA.carcasa_semaforo, edgecolor="none", zorder=4))
        ax.add_patch(Circle((x, acera_media), g.grosor_poste, facecolor=PALETA.carcasa_semaforo, edgecolor="none",
                            zorder=4))
        ax.add_patch(FancyBboxPatch((x - g.semaforo_ancho / 2, g.semaforo_base), g.semaforo_ancho, g.semaforo_alto,
                                    boxstyle="round,pad=0,rounding_size=1.0", facecolor=PALETA.carcasa_semaforo,
                                    edgecolor="none", zorder=4))
        y_rojo = g.semaforo_base + g.semaforo_alto * 0.72
        y_verde = g.semaforo_base + g.semaforo_alto * 0.28
        self._halo = Circle((x, y_rojo), g.radio_halo, edgecolor="none", alpha=g.alfa_halo, zorder=4)
        self._roja = Circle((x, y_rojo), g.radio_lampara, edgecolor="none", zorder=5)
        self._verde = Circle((x, y_verde), g.radio_lampara, edgecolor="none", zorder=5)
        self._centros = {Fase.ROJO: (x, y_rojo), Fase.VERDE: (x, y_verde)}
        self.artistas: list[Artist] = [self._halo, self._roja, self._verde]
        for lampara in self.artistas:
            ax.add_patch(lampara)

    def mostrar(self, fase: Fase) -> None:
        """Enciende la lámpara de la fase y apaga la otra."""
        rojo = fase is Fase.ROJO
        self._roja.set_facecolor(PALETA.rojo if rojo else PALETA.lampara_apagada)
        self._verde.set_facecolor(PALETA.lampara_apagada if rojo else PALETA.verde)
        self._halo.set_center(self._centros[fase])
        self._halo.set_facecolor(PALETA.rojo if rojo else PALETA.verde)

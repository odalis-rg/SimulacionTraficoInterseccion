"""Escena animada: compone la intersección, el tráfico, el semáforo y los indicadores.

Solo distribuye la figura en tres zonas y delega cada una en su componente;
en cada fotograma pide el estado a la traza y se lo entrega a todos.
"""

from __future__ import annotations

from matplotlib.artist import Artist
from matplotlib.figure import Figure

from config.settings import ConfigAnimacion
from view.animacion.indicadores import MiniSerieCola, PanelIndicadores
from view.animacion.interseccion import Interseccion, SemaforoDibujado
from view.animacion.medidas import DISPOSICION, GEOMETRIA
from view.animacion.trafico import TraficoAnimado
from view.animacion.traza import ReproductorTraza
from view.style import PALETA


class EscenaAnimada:
    """Figura de la animación: (a) intersección, (b) panel de indicadores y (c) mini Q(t)."""

    def __init__(self, figura: Figure, reproductor: ReproductorTraza, config: ConfigAnimacion, controles: bool) -> None:
        d = DISPOSICION
        self._rep = reproductor
        rejilla = figura.add_gridspec(
            2, 2, height_ratios=d.filas, width_ratios=d.columnas, left=d.margenes[0], right=d.margenes[1],
            top=d.margenes[2], bottom=d.margenes[3], wspace=d.separacion[0], hspace=d.separacion[1],
        )
        figura.set_facecolor(PALETA.fondo_animacion)
        ax_via = figura.add_subplot(rejilla[0, 0])
        Interseccion(ax_via, GEOMETRIA.tamano_auto(config.max_vehiculos_fila))
        self._semaforo = SemaforoDibujado(ax_via)
        self._trafico = TraficoAnimado(ax_via, reproductor, config)
        self._panel = PanelIndicadores(figura.add_subplot(rejilla[0, 1]), controles)
        self._serie = MiniSerieCola(figura.add_subplot(rejilla[1, :]), reproductor)
        p = reproductor.parametros
        figura.suptitle(
            f"Acceso semaforizado · λ = {p.lam:g} veh/s · g = {p.g:g} s · r = {p.r:g} s · μ = {p.mu:g} veh/s",
            x=d.margenes[0], ha="left", fontsize=d.texto_titulo, color=PALETA.texto, fontweight="bold",
        )

    def dibujar(self, t: float) -> list[Artist]:
        """Actualiza todas las zonas para el instante simulado t; devuelve los artistas que cambian."""
        estado = self._rep.estado(t)
        self._trafico.dibujar(estado, t)
        self._semaforo.mostrar(estado.fase)
        self._panel.mostrar(estado)
        self._serie.mostrar_hasta(t)
        return [*self._trafico.artistas, *self._semaforo.artistas, *self._panel.artistas, *self._serie.artistas]

    def estado_reproduccion(self, texto: str) -> None:
        self._panel.estado_reproduccion(texto)

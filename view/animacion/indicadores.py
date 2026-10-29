"""Indicadores en vivo de la animación: panel de valores y mini gráfica de Q(t)."""

from __future__ import annotations

from matplotlib.artist import Artist
from matplotlib.axes import Axes
from matplotlib.patches import FancyBboxPatch

from model.traffic_light import Fase
from view.animacion.medidas import DISPOSICION
from view.animacion.traza import EstadoInstante, ReproductorTraza
from view.formato import vehiculo
from view.plots import leyenda_fases, sombrear_fases
from view.style import PALETA

ETIQUETAS = ("Tiempo simulado", "Semáforo", "Cambio de fase en", "Q(t) en espera", "En servicio", "Llegados",
             "Salidos", "Ciclo")


class PanelIndicadores:
    """Tarjeta con el estado del acceso en el instante reproducido."""

    def __init__(self, ax: Axes, controles: bool) -> None:
        d = DISPOSICION
        ax.axis("off")
        ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.04",
                                    transform=ax.transAxes, facecolor=PALETA.superficie, edgecolor="none"))
        ax.text(0.07, 0.93, "Indicadores en vivo", transform=ax.transAxes, fontsize=d.texto_valor,
                fontweight="bold", color=PALETA.texto, va="top")
        self._valores = {}
        for i, etiqueta in enumerate(ETIQUETAS):
            y = 0.80 - i * d.renglon
            ax.text(0.07, y, etiqueta, transform=ax.transAxes, fontsize=d.texto, color=PALETA.texto_secundario,
                    va="center")
            self._valores[etiqueta] = ax.text(0.93, y, "", transform=ax.transAxes, fontsize=d.texto_valor,
                                              color=PALETA.texto, va="center", ha="right", fontweight="bold")
        ax.text(0.07, 0.035, "Espacio: pausa · R: reiniciar" if controles else "", transform=ax.transAxes,
                fontsize=d.texto_pequeno, color=PALETA.texto_tenue, va="center")
        self._reproduccion = ax.text(0.07, 0.09, "", transform=ax.transAxes, fontsize=d.texto_pequeno,
                                     color=PALETA.texto_secundario, va="center")
        self.artistas: list[Artist] = [*self._valores.values(), self._reproduccion]

    def mostrar(self, estado: EstadoInstante) -> None:
        rojo = estado.fase is Fase.ROJO
        textos = {
            "Tiempo simulado": f"{estado.tiempo:.1f} s",
            "Semáforo": estado.fase.value,
            "Cambio de fase en": f"{estado.restante_fase:.1f} s",
            "Q(t) en espera": f"{estado.cola} veh",
            "En servicio": vehiculo(estado.en_servicio),
            "Llegados": str(estado.llegados),
            "Salidos": str(estado.salidos),
            "Ciclo": str(estado.ciclo),
        }
        for etiqueta, texto in textos.items():
            self._valores[etiqueta].set_text(texto)
        self._valores["Semáforo"].set_color(PALETA.rojo if rojo else PALETA.verde)

    def estado_reproduccion(self, texto: str) -> None:
        """Muestra si la animación se reproduce, está en pausa o terminó."""
        self._reproduccion.set_text(texto)


class MiniSerieCola:
    """Q(t) en escalón que se dibuja hasta el instante reproducido, con franjas rojo/verde."""

    def __init__(self, ax: Axes, reproductor: ReproductorTraza) -> None:
        d = DISPOSICION
        self._rep = reproductor
        sombrear_fases(ax, reproductor.fases, reproductor.fin)
        for coleccion in ax.collections:
            coleccion.set_alpha(d.alfa_franjas)
        (self._linea,) = ax.plot([], [], drawstyle="steps-post", color=PALETA.serie_principal, lw=1.6, zorder=3)
        self._cursor = ax.axvline(0, color=PALETA.texto, lw=1.0, zorder=4)
        ax.set_xlim(0, reproductor.fin)
        ax.set_ylim(0, max(float(reproductor.serie_q.max()), 1.0) * d.holgura_serie + 1)
        ax.set_xlabel("Tiempo simulado (s)")
        ax.set_ylabel("Q(t) (veh)")
        ax.grid(axis="x", visible=False)
        ax.set_title("Q(t): vehículos en espera, sin el vehículo en servicio", loc="left", fontsize=d.texto)
        ax.legend(handles=leyenda_fases(), loc="lower right", bbox_to_anchor=(1.0, 1.0), ncols=3,
                  fontsize=d.texto_pequeno, borderaxespad=0.2)
        self.artistas: list[Artist] = [self._linea, self._cursor]

    def mostrar_hasta(self, t: float) -> None:
        self._linea.set_data(*self._rep.serie_hasta(t))
        self._cursor.set_xdata([t, t])

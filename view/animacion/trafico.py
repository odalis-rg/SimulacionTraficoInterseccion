"""Autos de la escena: fila de espera, auto en servicio y salidas, a partir de la traza."""

from __future__ import annotations

import math

from matplotlib.artist import Artist
from matplotlib.axes import Axes

from config.settings import ConfigAnimacion
from view.animacion.automovil import Automovil
from view.animacion.medidas import DISPOSICION, GEOMETRIA, suavizar
from view.animacion.traza import EstadoInstante, ReproductorTraza
from view.style import PALETA


class TraficoAnimado:
    """Ubica en cada fotograma los autos de un conjunto reutilizable.

    * En la fila, cada auto entra desde la izquierda, avanza un lugar con
      suavidad tras cada inicio de servicio y enciende las luces de freno al
      detenerse; si la fila supera el máximo dibujable se muestra «+N».
    * El auto en servicio acelera desde la fila hasta cruzar la intersección
      durante su 1/μ s de servicio.
    * Tras salir, sigue con la velocidad con que terminó y se desvanece.
    """

    def __init__(self, ax: Axes, reproductor: ReproductorTraza, config: ConfigAnimacion) -> None:
        g = GEOMETRIA
        self._rep = reproductor
        self._maximo = config.max_vehiculos_fila
        self._transicion = config.duracion_transicion_s
        self._servicio = reproductor.parametros.tiempo_servicio
        self._paso = g.paso_fila(self._maximo)
        self._largo, ancho = g.tamano_auto(self._maximo)
        cantidad = self._maximo + 2 + math.ceil(self._transicion / self._servicio)
        self._autos = [Automovil(ax, self._largo, ancho, zorder=3) for _ in range(cantidad)]
        self._exceso = ax.text(g.margen_izquierdo, g.calzada_superior + g.acera + 1.2, "", ha="left", va="bottom",
                               fontsize=DISPOSICION.texto, color=PALETA.texto, fontweight="bold", zorder=5,
                               bbox={"boxstyle": "round,pad=0.35", "facecolor": PALETA.superficie, "edgecolor": "none"})
        self.artistas: list[Artist] = [*(pieza for auto in self._autos for pieza in auto.artistas), self._exceso]

    def dibujar(self, estado: EstadoInstante, t: float) -> None:
        usados = self._dibujar_fila(estado, t)
        usados = self._dibujar_servicio(estado, t, usados)
        usados = self._dibujar_salidas(t, usados)
        for auto in self._autos[usados:]:
            auto.ocultar()

    # -- Posiciones ----------------------------------------------------------
    def _x_fila(self, posicion: float) -> float:
        """Centro x del auto en la posición (continua) de la fila; 0 = junto a la línea de detención."""
        g = GEOMETRIA
        return g.linea_detencion - g.separacion_fila - self._paso * (posicion + 0.5)

    def _x_cruzado(self) -> float:
        """Centro x del auto al terminar su servicio: ya atravesó la intersección."""
        return GEOMETRIA.cruce_fin + self._largo / 2

    def _x_en_espera(self, vehiculo: int, posicion: float, t: float) -> tuple[float, bool]:
        """Posición en la fila y si el auto todavía está entrando desde la izquierda."""
        destino = self._x_fila(posicion)
        avance = (t - self._rep.t_llegada(vehiculo)) / self._transicion
        if avance >= 1:
            return destino, False
        entrada = -self._largo
        return entrada + (destino - entrada) * suavizar(avance), True

    def _recorrido_servicio(self, vehiculo: int) -> tuple[float, float]:
        """(x inicial, distancia) del servicio: desde su lugar en la fila hasta cruzar la intersección."""
        origen, _ = self._x_en_espera(vehiculo, 0.0, self._rep.t_inicio_servicio(vehiculo))
        return origen, self._x_cruzado() - origen

    # -- Dibujo ----------------------------------------------------------------
    def _mostrar(self, indice: int, x: float, color: str, frenando: bool, alfa: float) -> int:
        """Ubica el auto ``indice`` del conjunto; devuelve el siguiente índice libre."""
        if indice < len(self._autos):
            self._autos[indice].mostrar(x, GEOMETRIA.centro_acceso, color, frenando, alfa)
        return indice + 1

    def _dibujar_fila(self, estado: EstadoInstante, t: float) -> int:
        visibles = min(estado.cola, self._maximo)
        inicios = self._rep.inicios_recientes(t, self._transicion)
        usados = 0
        for k in range(visibles):
            vehiculo = estado.primero_en_espera + k
            llegada = self._rep.t_llegada(vehiculo)
            # Tras cada inicio de servicio la fila avanza un lugar de forma suave.
            rezago = sum(1.0 - suavizar((t - s) / self._transicion) for s in inicios if s > llegada)
            x, entrando = self._x_en_espera(vehiculo, k + rezago, t)
            detenido = not entrando and rezago < GEOMETRIA.umbral_movimiento
            usados = self._mostrar(usados, x, PALETA.autos[vehiculo % len(PALETA.autos)], detenido, 1.0)
        exceso = estado.cola - visibles
        self._exceso.set_text(f"+{exceso} vehículos más en espera" if exceso > 0 else "")
        self._exceso.set_visible(exceso > 0)
        return usados

    def _dibujar_servicio(self, estado: EstadoInstante, t: float, usados: int) -> int:
        if estado.en_servicio is None:
            return usados
        origen, distancia = self._recorrido_servicio(estado.en_servicio)
        avance = min((t - self._rep.t_inicio_servicio(estado.en_servicio)) / self._servicio, 1.0)
        return self._mostrar(usados, origen + distancia * avance ** 2, PALETA.vehiculo_servicio, False, 1.0)

    def _dibujar_salidas(self, t: float, usados: int) -> int:
        for instante, vehiculo in self._rep.salidas_recientes(t, self._transicion):
            _, distancia = self._recorrido_servicio(vehiculo)
            x = self._x_cruzado() + 2 * distancia / self._servicio * (t - instante)
            usados = self._mostrar(usados, x, PALETA.vehiculo_servicio, False, 1.0 - (t - instante) / self._transicion)
        return usados

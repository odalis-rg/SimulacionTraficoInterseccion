"""Consulta de una traza ya simulada: estado del acceso en cualquier instante.

No ejecuta el modelo ni consume números aleatorios: consulta con búsqueda
binaria la traza y el calendario de fases que registró el simulador. Por eso
lo que dibuja la animación coincide con la traza y las tablas
(Q(t) = vehículos en espera, sin el que está en servicio).
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

import numpy as np

from model.events import RegistroTraza, TipoEvento
from model.simulator import ResultadoReplica
from model.statistics import serie_cola
from model.traffic_light import Fase


@dataclass(frozen=True, slots=True)
class EstadoInstante:
    """Estado del acceso en el instante t, tras procesar todos los eventos ≤ t."""

    tiempo: float
    fase: Fase
    restante_fase: float
    ciclo: int
    cola: int
    en_servicio: int | None
    llegados: int
    salidos: int

    @property
    def primero_en_espera(self) -> int:
        """Id del primer vehículo de la fila (FIFO: los ids siguen el orden de llegada)."""
        return self.llegados - self.cola + 1


class ReproductorTraza:
    """Índices de la traza de una réplica, recortada a la ventana que se reproduce."""

    def __init__(self, resultado: ResultadoReplica, ventana: float) -> None:
        self.parametros = resultado.parametros
        self.semilla = resultado.semilla
        self.fin = min(ventana, resultado.parametros.H)
        self._traza: list[RegistroTraza] = [f for f in resultado.traza if f.tiempo <= self.fin]
        self._tiempos = [f.tiempo for f in self._traza]
        self._llegadas = [f.tiempo for f in self._traza if f.tipo is TipoEvento.LLEGADA]
        self._salidas = [(f.tiempo, f.vehiculo_id) for f in self._traza if f.tipo is TipoEvento.SALIDA]
        self._t_salidas = [t for t, _ in self._salidas]
        self._inicios = self._inicios_de_servicio(self._traza)
        self._t_inicios = sorted(self._inicios.values())
        self.fases = tuple(f for f in resultado.fases if f.inicio <= self.fin)
        self._inicio_fases = [f.inicio for f in self.fases]
        self.serie_t, self.serie_q = serie_cola(self._traza, self.fin)

    @staticmethod
    def _inicios_de_servicio(traza: list[RegistroTraza]) -> dict[int, float]:
        """Instante en que cada vehículo pasa al servidor (cambio de ``en_servicio`` en la traza)."""
        inicios: dict[int, float] = {}
        for fila in traza:
            if fila.en_servicio is not None and fila.en_servicio not in inicios:
                inicios[fila.en_servicio] = fila.tiempo
        return inicios

    def estado(self, t: float) -> EstadoInstante:
        """Estado vigente en t: última fila de la traza con tiempo ≤ t y fase del calendario."""
        i = bisect_right(self._tiempos, t) - 1
        fila = self._traza[i] if i >= 0 else None
        fase = self.fases[max(bisect_right(self._inicio_fases, t) - 1, 0)]
        return EstadoInstante(
            tiempo=t,
            fase=fase.fase,
            restante_fase=max(fase.fin - t, 0.0),
            ciclo=fase.ciclo,
            cola=fila.cola if fila else 0,
            en_servicio=fila.en_servicio if fila else None,
            llegados=bisect_right(self._llegadas, t),
            salidos=bisect_right(self._t_salidas, t),
        )

    def t_llegada(self, vehiculo: int) -> float:
        """Instante de llegada del vehículo ``vehiculo`` (ids consecutivos desde 1)."""
        return self._llegadas[vehiculo - 1]

    def t_inicio_servicio(self, vehiculo: int) -> float:
        """Instante en que el vehículo ``vehiculo`` comenzó su servicio."""
        return self._inicios[vehiculo]

    def inicios_recientes(self, t: float, duracion: float) -> list[float]:
        """Instantes de inicio de servicio en (t − duracion, t]."""
        return self._t_inicios[bisect_right(self._t_inicios, t - duracion):bisect_right(self._t_inicios, t)]

    def salidas_recientes(self, t: float, duracion: float) -> list[tuple[float, int]]:
        """(instante, id) de las salidas ocurridas en (t − duracion, t]."""
        return self._salidas[bisect_right(self._t_salidas, t - duracion):bisect_right(self._t_salidas, t)]

    def serie_hasta(self, t: float) -> tuple[np.ndarray, np.ndarray]:
        """Tramo de Q(t) escalonada desde 0 hasta t (para dibujarla progresivamente)."""
        i = int(np.searchsorted(self.serie_t, t, side="right"))
        return np.append(self.serie_t[:i], t), np.append(self.serie_q[:i], self.serie_q[i - 1])

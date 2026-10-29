"""Tipos de evento, regla de prioridad, agenda de eventos y fila de la traza.

Regla de prioridad ante eventos simultáneos (mismo instante):

1. SALIDA: se procesa primero. Una salida que termina exactamente al final
   del verde es válida y se cuenta en ese ciclo, antes de que llegue el rojo.
2. CAMBIO_FASE: el semáforo cambia antes de atender llegadas, de modo que una
   llegada simultánea encuentra ya la fase nueva.
3. LLEGADA: se procesa al final; el vehículo se incorpora a la cola detrás de
   los que ya esperaban.

Entre eventos del mismo tipo en el mismo instante se respeta el orden en que
se programaron (número de secuencia), lo que mantiene el determinismo.
"""

from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field
from enum import IntEnum

from model.traffic_light import Fase


class TipoEvento(IntEnum):
    """Evento programable. Su valor es la prioridad: menor valor, antes se procesa."""

    SALIDA = 1
    CAMBIO_FASE = 2
    LLEGADA = 3


@dataclass(frozen=True, order=True, slots=True)
class Evento:
    """Evento de la agenda, ordenado por (tiempo, prioridad, secuencia)."""

    tiempo: float
    tipo: TipoEvento
    secuencia: int
    vehiculo_id: int | None = field(default=None, compare=False)


class AgendaEventos:
    """Agenda de eventos futuros implementada como heap binario."""

    def __init__(self) -> None:
        self._heap: list[Evento] = []
        self._secuencia = itertools.count()

    def programar(self, tiempo: float, tipo: TipoEvento, vehiculo_id: int | None = None) -> None:
        """Agrega un evento; el heap lo ordena por (tiempo, prioridad, secuencia)."""
        heapq.heappush(self._heap, Evento(tiempo, tipo, next(self._secuencia), vehiculo_id))

    def extraer(self) -> Evento:
        """Retira y devuelve el próximo evento según la regla de prioridad."""
        return heapq.heappop(self._heap)

    def __len__(self) -> int:
        return len(self._heap)


@dataclass(frozen=True, slots=True)
class RegistroTraza:
    """Fila de la traza: evento procesado y estado del sistema justo después.

    ``cola`` es Q(t): vehículos que esperan, SIN contar el que está en servicio.
    ``en_servicio`` es el id del vehículo que ocupa el servidor (o None).
    """

    tiempo: float
    tipo: TipoEvento
    vehiculo_id: int | None
    fase: Fase
    cola: int
    en_servicio: int | None
    ciclo: int

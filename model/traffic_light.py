"""Semáforo de tiempos fijos: estado actual y calendario de fases."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from config.settings import ParametrosModelo


class Fase(str, Enum):
    """Fase del semáforo (no se modela amarillo ni intervalo de despeje)."""

    ROJO = "ROJO"
    VERDE = "VERDE"


@dataclass(frozen=True, slots=True)
class IntervaloFase:
    """Tramo [inicio, fin) del calendario con su fase y su ciclo (1, 2, …)."""

    inicio: float
    fin: float
    fase: Fase
    ciclo: int


class Semaforo:
    """Alterna rojo y verde de duración fija, empezando en rojo en t = 0.

    El ciclo k (k = 1, 2, …) ocupa [(k−1)T, kT): primero el rojo
    [(k−1)T, (k−1)T + r) y después el verde [(k−1)T + r, kT). Los instantes se
    calculan a partir del índice del ciclo, no por sumas sucesivas, para no
    acumular errores de redondeo.
    """

    def __init__(self, parametros: ParametrosModelo) -> None:
        self._p = parametros
        self.fase = Fase.ROJO
        self.ciclo = 1

    def intervalo_actual(self) -> IntervaloFase:
        """Intervalo de la fase vigente."""
        inicio_ciclo = (self.ciclo - 1) * self._p.T
        if self.fase is Fase.ROJO:
            return IntervaloFase(inicio_ciclo, inicio_ciclo + self._p.r, Fase.ROJO, self.ciclo)
        return IntervaloFase(inicio_ciclo + self._p.r, self.ciclo * self._p.T, Fase.VERDE, self.ciclo)

    def fin_fase_actual(self) -> float:
        """Instante en que termina la fase vigente."""
        return self.intervalo_actual().fin

    def cambiar_fase(self) -> None:
        """Rojo → verde (mismo ciclo); verde → rojo (empieza el ciclo siguiente)."""
        if self.fase is Fase.ROJO:
            self.fase = Fase.VERDE
        else:
            self.fase = Fase.ROJO
            self.ciclo += 1

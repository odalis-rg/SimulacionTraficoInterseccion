"""Procesos de llegada de vehículos: estrategias intercambiables para el simulador.

El simulador solo depende del protocolo ``ProcesoLlegadas``; para cambiar la
forma de las llegadas (por ejemplo, llegadas en pelotón) basta con escribir
otra clase que lo cumpla, sin modificar el motor.
"""

from __future__ import annotations

from typing import Iterable, Protocol

import numpy as np


class ProcesoLlegadas(Protocol):
    """Fuente de instantes de llegada en orden no decreciente."""

    def siguiente(self, desde: float) -> float | None:
        """Instante de la próxima llegada posterior a ``desde``; None si no hay más."""
        ...


class LlegadasPoisson:
    """Llegadas de Poisson homogéneas: intervalos exponenciales de media 1/λ.

    Usa un ``numpy.random.Generator`` dedicado solo a las llegadas: la misma
    semilla produce el mismo flujo aunque cambien g o r (números aleatorios
    comunes). Con λ = 0 no hay llegadas.
    """

    def __init__(self, lam: float, semilla: int) -> None:
        self._lam = lam
        self._rng = np.random.default_rng(semilla)

    def siguiente(self, desde: float) -> float | None:
        if self._lam == 0:
            return None
        return desde + self._rng.exponential(1.0 / self._lam)


class LlegadasPrefijadas:
    """Llegadas en instantes dados; sirve para pruebas deterministas."""

    def __init__(self, instantes: Iterable[float]) -> None:
        self._pendientes = iter(sorted(instantes))

    def siguiente(self, desde: float) -> float | None:
        return next(self._pendientes, None)

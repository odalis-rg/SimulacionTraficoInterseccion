"""Entidad Vehículo del modelo."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Vehiculo:
    """Vehículo que llega al acceso semaforizado.

    Los instantes están en segundos de simulación. ``None`` indica que el hecho
    no ocurrió dentro del horizonte H (el vehículo sigue esperando o en servicio).
    Las métricas derivadas (espera, tiempo en el sistema) se calculan solo en
    ``model/statistics.py``.
    """

    id: int
    t_llegada: float
    t_inicio_servicio: float | None = None
    t_salida: float | None = None

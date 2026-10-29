"""Contratos entre la ventana principal y sus componentes.

La ventana solo conoce estos protocolos: avisa a los receptores cuando cambia
la configuración o llega una simulación nueva, y recibe por inyección el
exportador y el animador. Agregar una pestaña que muestre resultados no
obliga a cambiar el flujo de simulación: basta registrarla como receptora.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from matplotlib.figure import Figure

from config.settings import Configuracion
from controller.analysis import Comparacion, ResultadoBarrido, ResultadoEscenario
from model.simulator import ResultadoReplica


@dataclass(frozen=True)
class SimulacionEscenarios:
    """Resultados de la última simulación de escenarios, listos para mostrar o guardar."""

    resultados: Sequence[ResultadoEscenario]
    comparacion: Comparacion | None
    confianza: float


class ReceptorSimulacion(Protocol):
    """Componente que presenta los resultados de una simulación de escenarios."""

    def mostrar_resultados(self, simulacion: SimulacionEscenarios) -> None: ...


class ReceptorConfiguracion(Protocol):
    """Componente que refleja la configuración activa (escenarios y parámetros)."""

    def configuracion_cambiada(self, config: Configuracion) -> None: ...


class Exportador(Protocol):
    """Guarda en la carpeta de salida los resultados ya calculados."""

    def escenarios(self, resultados: Sequence[ResultadoEscenario], comparacion: Comparacion | None) -> list[Path]: ...

    def barrido(self, barrido: ResultadoBarrido, ventana: float) -> list[Path]: ...


class ControlAnimacion(Protocol):
    """Animación en curso dentro de la ventana."""

    @property
    def pausado(self) -> bool: ...

    def alternar_pausa(self) -> None: ...

    def reiniciar(self) -> None: ...

    def detener(self) -> None: ...


class AnimadorIncrustado(Protocol):
    """Crea la animación de una réplica sobre una figura de la ventana."""

    def crear_en(self, figura: Figure, resultado: ResultadoReplica, velocidad: float) -> ControlAnimacion: ...

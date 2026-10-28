"""Acumuladores y métricas de una réplica: único lugar donde se calcula cada métrica.

Definición común a código, tablas, gráficas y animación:
    Q(t) = número de vehículos que ESPERAN en la cola, sin el vehículo en servicio.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from config.settings import ParametrosModelo
from model.events import RegistroTraza
from model.vehicle import Vehiculo

SEGUNDOS_POR_HORA = 3600.0
"""Conversión de veh/s a veh/h."""


@dataclass(frozen=True, slots=True)
class Indicador:
    """Indicador que se resume entre réplicas; ``clave`` es el campo de MetricasReplica."""

    clave: str
    simbolo: str
    descripcion: str
    unidad: str


INDICADORES: tuple[Indicador, ...] = (
    Indicador("q_media", "Q̄", "Longitud media temporal de la cola", "veh"),
    Indicador("q_max", "Qmáx", "Longitud máxima de la cola", "veh"),
    Indicador("area_cola", "∫Q dt", "Área bajo Q(t) = demora total en cola", "veh·s"),
    Indicador("wq_media", "Wq", "Espera media (inicio de servicio − llegada)", "s/veh"),
    Indicador("w_media", "W", "Tiempo medio en el sistema (salida − llegada)", "s/veh"),
    Indicador("capacidad_efectiva", "C", "Capacidad efectiva (salidas registradas)", "veh/h"),
    Indicador("llegados", "Llegados", "Vehículos llegados en [0, H]", "veh"),
    Indicador("salidos", "Salidos", "Vehículos que salieron en [0, H]", "veh"),
    Indicador("atendidos_por_ciclo", "At./ciclo", "Vehículos atendidos por ciclo", "veh"),
    Indicador("residual_medio", "Residual", "Cola residual al final del verde", "veh"),
    Indicador("pendientes", "Pend.(H)", "Pendientes en el sistema al terminar H", "veh"),
    Indicador("censura_media", "Cens.(H)", "Tiempo llegada→H de pendientes (censurado)", "s"),
)
INDICADORES_POR_CLAVE: dict[str, Indicador] = {ind.clave: ind for ind in INDICADORES}


@dataclass(frozen=True, slots=True)
class RegistroCiclo:
    """Resultado de un ciclo completo, registrado al terminar su verde."""

    ciclo: int
    inicio_verde: float
    fin_verde: float
    atendidos: int
    cola_residual: int


@dataclass(frozen=True, slots=True)
class MetricasReplica:
    """Métricas de una réplica sobre el horizonte simulado [0, H]."""

    q_media: float
    q_max: int
    area_cola: float
    wq_media: float
    w_media: float
    capacidad_efectiva: float
    llegados: int
    salidos: int
    en_cola_final: int
    en_servicio_final: int
    pendientes: int
    censura_media: float
    censura_max: float
    atendidos_por_ciclo: float
    residual_medio: float
    ciclos_completos: int
    balance_ok: bool


class ContadorCiclos:
    """Acumula, ciclo a ciclo, las salidas y la cola residual al terminar cada verde."""

    def __init__(self) -> None:
        self._salidas: Counter[int] = Counter()
        self.ciclos: list[RegistroCiclo] = []

    def registrar_salida(self, ciclo: int) -> None:
        """Cuenta una salida en el ciclo indicado."""
        self._salidas[ciclo] += 1

    def registrar_fin_verde(self, ciclo: int, inicio_verde: float, fin_verde: float, cola_residual: int) -> None:
        """Cierra el ciclo: vehículos atendidos en su verde y Q(t) al terminarlo."""
        self.ciclos.append(RegistroCiclo(ciclo, inicio_verde, fin_verde, self._salidas[ciclo], cola_residual))


# ---------------------------------------------------------------------------
# Cálculos (cada uno vive solo aquí)
# ---------------------------------------------------------------------------
def _media(valores: np.ndarray) -> float:
    """Media aritmética; NaN si no hay datos (métrica no definida en la réplica)."""
    return float(valores.mean()) if valores.size else math.nan


def esperas(vehiculos: Sequence[Vehiculo]) -> np.ndarray:
    """Espera individual = inicio de servicio − llegada (vehículos que iniciaron servicio)."""
    return np.array(
        [v.t_inicio_servicio - v.t_llegada for v in vehiculos if v.t_inicio_servicio is not None], dtype=float
    )


def tiempos_en_sistema(vehiculos: Sequence[Vehiculo]) -> np.ndarray:
    """Tiempo en el sistema = salida − llegada (solo vehículos que salieron)."""
    return np.array([v.t_salida - v.t_llegada for v in vehiculos if v.t_salida is not None], dtype=float)


def tiempos_censurados(vehiculos: Sequence[Vehiculo], H: float) -> np.ndarray:
    """H − llegada de los vehículos que no salieron antes de H.

    Es una observación censurada: su tiempo real en el sistema es mayor. Se
    reporta aparte y nunca se mezcla con la media de los que sí salieron.
    """
    return np.array([H - v.t_llegada for v in vehiculos if v.t_salida is None], dtype=float)


def rho_efectivo(p: ParametrosModelo) -> float:
    """ρef = λT/(μg): llegadas esperadas por ciclo / capacidad nominal por ciclo.

    Es un cociente de referencia; no garantiza la existencia de régimen estacionario.
    """
    return p.lam * p.T / (p.mu * p.g)


def capacidad_nominal(p: ParametrosModelo) -> float:
    """Capacidad nominal del acceso, 3600·μ·g/T (veh/h)."""
    return SEGUNDOS_POR_HORA * p.mu * p.g / p.T


def capacidad_efectiva(salidas: int, H: float) -> float:
    """C = 3600 · salidas realmente registradas / H (veh/h); no promedia tasas."""
    return SEGUNDOS_POR_HORA * salidas / H


def serie_cola(traza: Sequence[RegistroTraza], fin: float) -> tuple[np.ndarray, np.ndarray]:
    """Q(t) escalonada en [0, fin]: instantes de cambio y valor vigente desde cada uno.

    El último punto (``fin``) repite el valor final para cerrar el último intervalo.
    """
    final = traza[-1].cola if traza else 0
    tiempos = np.array([0.0, *(r.tiempo for r in traza), fin], dtype=float)
    colas = np.array([0, *(r.cola for r in traza), final], dtype=float)
    return tiempos, colas


def area_acumulada(tiempos: np.ndarray, colas: np.ndarray) -> np.ndarray:
    """∫₀ᵗ Q(s) ds en cada instante de la serie: Σ Q · (duración del intervalo) (veh·s)."""
    return np.concatenate(([0.0], np.cumsum(colas[:-1] * np.diff(tiempos))))


def calcular_metricas(
    traza: Sequence[RegistroTraza], vehiculos: Sequence[Vehiculo], ciclos: Sequence[RegistroCiclo], H: float
) -> MetricasReplica:
    """Métricas de la réplica a partir de la traza, los vehículos y los ciclos.

    Q̄ = (1/H)·∫₀ᴴ Q(t) dt incluye el intervalo final hasta H. El balance compara
    dos registros independientes: vehículos creados frente a salidos + estado
    final de la cola y del servidor.
    """
    tiempos, colas = serie_cola(traza, H)
    en_cola = traza[-1].cola if traza else 0
    en_servicio = int(bool(traza) and traza[-1].en_servicio is not None)
    sistema = tiempos_en_sistema(vehiculos)
    censura = tiempos_censurados(vehiculos, H)
    salidos = int(sistema.size)
    pendientes = en_cola + en_servicio
    area = float(area_acumulada(tiempos, colas)[-1])
    return MetricasReplica(
        q_media=area / H,
        q_max=int(colas.max()),
        area_cola=area,
        wq_media=_media(esperas(vehiculos)),
        w_media=_media(sistema),
        capacidad_efectiva=capacidad_efectiva(salidos, H),
        llegados=len(vehiculos),
        salidos=salidos,
        en_cola_final=en_cola,
        en_servicio_final=en_servicio,
        pendientes=pendientes,
        censura_media=_media(censura),
        censura_max=float(censura.max()) if censura.size else math.nan,
        atendidos_por_ciclo=_media(np.array([c.atendidos for c in ciclos], dtype=float)),
        residual_medio=_media(np.array([c.cola_residual for c in ciclos], dtype=float)),
        ciclos_completos=len(ciclos),
        balance_ok=len(vehiculos) == salidos + pendientes and censura.size == pendientes,
    )

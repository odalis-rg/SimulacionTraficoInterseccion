"""Análisis entre réplicas.

Media, desviación estándar muestral e intervalo de confianza con t de Student;
consolidación de las réplicas de un escenario, comparación porcentual frente
al escenario base y selección del g que minimiza Q̄ en el barrido. Todos los
resultados describen el horizonte simulado, no un régimen estacionario.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
from scipy import stats

from config.settings import Escenario, ParametrosModelo
from model.simulator import ResultadoReplica
from model.statistics import (
    INDICADORES,
    INDICADORES_POR_CLAVE,
    Indicador,
    MetricasReplica,
    capacidad_nominal,
    esperas,
    rho_efectivo,
)


@dataclass(frozen=True)
class Resumen:
    """Estadísticos de un indicador entre réplicas."""

    media: float
    desviacion: float
    semiancho: float
    n: int

    @property
    def ic_inferior(self) -> float:
        return self.media - self.semiancho

    @property
    def ic_superior(self) -> float:
        return self.media + self.semiancho


def resumir(valores: Iterable[float], confianza: float) -> Resumen:
    """Media, desviación estándar muestral (n − 1) e IC = media ± t₍₁₊c₎/₂,ₙ₋₁ · s/√n.

    Los valores no finitos (métrica no definida en una réplica, p. ej. sin
    pendientes) se excluyen; ``n`` indica cuántas réplicas se usaron.
    """
    datos = np.array([v for v in valores if math.isfinite(v)], dtype=float)
    n = int(datos.size)
    if n == 0:
        return Resumen(math.nan, math.nan, math.nan, 0)
    media = float(datos.mean())
    if n < 2:
        return Resumen(media, math.nan, math.nan, n)
    desviacion = float(datos.std(ddof=1))
    t_critico = float(stats.t.ppf((1.0 + confianza) / 2.0, df=n - 1))
    return Resumen(media, desviacion, t_critico * desviacion / math.sqrt(n), n)


def media_por_ciclo(series: Sequence[Sequence[float]]) -> np.ndarray:
    """Media entre réplicas, ciclo a ciclo (se recorta al menor número de ciclos)."""
    largo = min((len(s) for s in series), default=0)
    if largo == 0:
        return np.zeros(0)
    return np.mean([list(s[:largo]) for s in series], axis=0)


@dataclass(frozen=True)
class ResultadoEscenario:
    """Resultado consolidado de las n réplicas de un escenario."""

    escenario: Escenario
    parametros: ParametrosModelo
    semillas: tuple[int, ...]
    metricas: tuple[MetricasReplica, ...]
    resumen: dict[str, Resumen]
    replica_detalle: int
    detalle: ResultadoReplica
    residual_por_ciclo: np.ndarray
    esperas: np.ndarray

    @property
    def nombre(self) -> str:
        return self.escenario.nombre

    @property
    def rho_ef(self) -> float:
        return rho_efectivo(self.parametros)

    @property
    def capacidad_nominal(self) -> float:
        return capacidad_nominal(self.parametros)

    @property
    def balance_ok(self) -> bool:
        return all(m.balance_ok for m in self.metricas)


class AcumuladorEscenario:
    """Reúne réplica a réplica lo necesario para el análisis.

    Solo conserva la traza completa de la réplica de detalle, de modo que la
    memoria no crece con el número de réplicas.
    """

    def __init__(self, escenario: Escenario, parametros: ParametrosModelo, replica_detalle: int) -> None:
        self._escenario = escenario
        self._parametros = parametros
        self._replica_detalle = replica_detalle
        self._semillas: list[int] = []
        self._metricas: list[MetricasReplica] = []
        self._residuales: list[list[int]] = []
        self._esperas: list[np.ndarray] = []
        self._detalle: ResultadoReplica | None = None

    def agregar(self, replica: int, resultado: ResultadoReplica) -> None:
        self._semillas.append(resultado.semilla)
        self._metricas.append(resultado.metricas)
        self._residuales.append([c.cola_residual for c in resultado.ciclos])
        self._esperas.append(esperas(resultado.vehiculos))
        if replica == self._replica_detalle:
            self._detalle = resultado

    def consolidar(self, confianza: float) -> ResultadoEscenario:
        assert self._detalle is not None, "No se simuló la réplica de detalle"
        return ResultadoEscenario(
            escenario=self._escenario,
            parametros=self._parametros,
            semillas=tuple(self._semillas),
            metricas=tuple(self._metricas),
            resumen={
                ind.clave: resumir((getattr(m, ind.clave) for m in self._metricas), confianza) for ind in INDICADORES
            },
            replica_detalle=self._replica_detalle,
            detalle=self._detalle,
            residual_por_ciclo=media_por_ciclo(self._residuales),
            esperas=np.concatenate(self._esperas),
        )


# ---------------------------------------------------------------------------
# Comparación con el escenario base
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FilaComparacion:
    """Reducción porcentual de un indicador (medias entre réplicas) frente a la base."""

    escenario: str
    indicador: Indicador
    base: float
    valor: float
    reduccion: float


@dataclass(frozen=True)
class Comparacion:
    """Comparación con la base y escenarios excluidos por tener otra λ."""

    base: str
    filas: tuple[FilaComparacion, ...]
    no_comparables: tuple[str, ...]


def reduccion_porcentual(valor: float, referencia: float) -> float:
    """100·(referencia − valor)/referencia; positivo = el escenario reduce el indicador."""
    if not (math.isfinite(valor) and math.isfinite(referencia)) or referencia == 0:
        return math.nan
    return 100.0 * (referencia - valor) / referencia


def comparar_con_base(
    resultados: Sequence[ResultadoEscenario], base: ResultadoEscenario, claves: Sequence[str]
) -> Comparacion:
    """Compara las medias entre réplicas de cada indicador con las de la base.

    Solo se comparan escenarios con la misma λ que la base: así la diferencia
    se debe a los tiempos de fase y no a un cambio de demanda.
    """
    otros = [r for r in resultados if r.nombre != base.nombre]
    comparables = [r for r in otros if math.isclose(r.parametros.lam, base.parametros.lam)]
    filas = tuple(
        FilaComparacion(r.nombre, INDICADORES_POR_CLAVE[clave], base.resumen[clave].media, r.resumen[clave].media,
                        reduccion_porcentual(r.resumen[clave].media, base.resumen[clave].media))
        for r in comparables
        for clave in claves
    )
    return Comparacion(base.nombre, filas, tuple(r.nombre for r in otros if r not in comparables))


# ---------------------------------------------------------------------------
# Pruebas de verificación
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ResultadoPrueba:
    """Resultado de una prueba de verificación (``detalle`` explica el fallo)."""

    numero: int
    descripcion: str
    exito: bool
    detalle: str


# ---------------------------------------------------------------------------
# Barrido de g (Tabla I)
# ---------------------------------------------------------------------------
def indice_minimo(resultados: Sequence[ResultadoEscenario], clave: str) -> int | None:
    """Índice del resultado con menor media del indicador (None si ninguno está definido)."""
    medias = [(r.resumen[clave].media, i) for i, r in enumerate(resultados) if math.isfinite(r.resumen[clave].media)]
    return min(medias)[1] if medias else None


@dataclass(frozen=True)
class ResultadoBarrido:
    """Configuraciones de g con λ y T fijos; ``indice_optimo`` minimiza Q̄ (área bajo Q(t))."""

    lam: float
    T: float
    resultados: tuple[ResultadoEscenario, ...]
    indice_optimo: int | None
    indice_min_wq: int | None

    @classmethod
    def desde(cls, lam: float, T: float, resultados: Sequence[ResultadoEscenario]) -> ResultadoBarrido:
        resultados = tuple(resultados)
        return cls(lam, T, resultados, indice_minimo(resultados, "q_media"), indice_minimo(resultados, "wq_media"))

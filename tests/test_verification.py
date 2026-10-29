"""Pruebas automáticas de verificación del simulador.

Se ejecutan con pytest (``python -m pytest``) y también desde el menú
(opción 1) o con ``python main.py --pruebas --no-menu``. Cada prueba es una
función sin argumentos que usa ``assert``; la tupla ``PRUEBAS`` fija el orden
en que el menú las muestra. Verifican la consistencia interna del programa,
no que los parámetros representen el tráfico real.
"""

from __future__ import annotations

import dataclasses

import numpy as np

from config.settings import ErrorConfiguracion, ParametrosModelo
from model.arrivals import LlegadasPrefijadas
from model.events import AgendaEventos, TipoEvento
from model.simulator import ResultadoReplica, Simulador
from model.traffic_light import Fase

SEMILLA = 2026
"""Semilla de la réplica 1 del informe (2025 + 1)."""
SEMILLAS_TENDENCIA = range(2026, 2036)
TOLERANCIA = 1e-9
DEMANDA_SATURANTE = 5.0
"""λ (veh/s) tan alta que la fila nunca se vacía: cada verde trabaja a plena capacidad."""


def _simular(lam: float = 0.15, g: float = 30.0, r: float = 30.0, mu: float = 0.5, H: float = 3600.0,
             semilla: int = SEMILLA) -> ResultadoReplica:
    return Simulador(ParametrosModelo(lam, g, r, mu, H), semilla).ejecutar()


def test_sin_llegadas_cola_vacia() -> None:
    """Con λ = 0 no hay llegadas ni salidas y la cola permanece vacía."""
    resultado = _simular(lam=0.0)
    tipos = {f.tipo for f in resultado.traza}
    assert tipos == {TipoEvento.CAMBIO_FASE}, f"eventos inesperados: {tipos}"
    assert all(f.cola == 0 and f.en_servicio is None for f in resultado.traza), "la cola no está vacía"
    m = resultado.metricas
    assert m.llegados == m.salidos == m.pendientes == 0
    assert m.q_media == 0 and m.q_max == 0
    assert all(c.atendidos == 0 and c.cola_residual == 0 for c in resultado.ciclos)


def test_sin_salidas_en_rojo() -> None:
    """Ninguna salida ocurre durante el rojo (ni fuera del verde de su ciclo)."""
    for lam in (0.15, 0.35):
        resultado = _simular(lam=lam, g=27.0, r=33.0)
        p = resultado.parametros
        for f in (f for f in resultado.traza if f.tipo is TipoEvento.SALIDA):
            inicio_verde, fin_verde = (f.ciclo - 1) * p.T + p.r, f.ciclo * p.T
            assert f.fase is Fase.VERDE, f"salida en rojo en t = {f.tiempo}"
            assert inicio_verde + p.tiempo_servicio - TOLERANCIA <= f.tiempo <= fin_verde + TOLERANCIA, (
                f"salida fuera del verde en t = {f.tiempo}"
            )


def test_balance_de_vehiculos() -> None:
    """Se cumple el balance: llegados = salidos + pendientes (en cola y en servicio)."""
    casos = ((0.15, 30.0, 30.0, 3600.0), (0.35, 30.0, 30.0, 3600.0), (0.8, 30.0, 30.0, 3590.0),
             (0.6, 20.0, 25.0, 1000.0))
    for lam, g, r, H in casos:
        resultado = _simular(lam=lam, g=g, r=r, H=H)
        m = resultado.metricas
        salidos = sum(v.t_salida is not None for v in resultado.vehiculos)
        assert m.balance_ok, f"balance incorrecto con λ={lam}, H={H}"
        assert m.llegados == salidos + m.en_cola_final + m.en_servicio_final
        assert sum(c.atendidos for c in resultado.ciclos) <= salidos


def test_reproducibilidad() -> None:
    """La misma configuración y semilla producen una traza y métricas idénticas."""
    a, b = _simular(lam=0.25), _simular(lam=0.25)
    assert a.traza == b.traza, "las trazas difieren"
    np.testing.assert_equal(dataclasses.asdict(a.metricas), dataclasses.asdict(b.metricas))
    assert _simular(lam=0.25, semilla=SEMILLA + 1).traza != a.traza, "semillas distintas dieron la misma traza"
    # Números aleatorios comunes: misma semilla y λ → mismas llegadas aunque cambien g y r.
    otra_fase = _simular(lam=0.25, g=40.0, r=20.0)
    assert [v.t_llegada for v in otra_fase.vehiculos] == [v.t_llegada for v in a.vehiculos]


def test_capacidad_por_verde() -> None:
    """Con demanda sin restricciones, las salidas por verde no superan μg y son μg si g es múltiplo de 1/μ."""
    for mu, g, multiplo in ((0.5, 30.0, True), (0.3, 20.0, True), (0.5, 31.0, False)):
        resultado = _simular(lam=DEMANDA_SATURANTE, g=g, r=30.0, mu=mu, H=900.0)
        capacidad = mu * g
        atendidos = [c.atendidos for c in resultado.ciclos]
        assert all(a <= capacidad + TOLERANCIA for a in atendidos), f"μ={mu}, g={g}: {atendidos} supera μg={capacidad}"
        if multiplo:
            assert all(a == round(capacidad) for a in atendidos), f"μ={mu}, g={g}: {atendidos} ≠ μg={capacidad}"


def test_orden_cronologico_y_horizonte() -> None:
    """Los eventos se procesan en orden cronológico y no hay salidas fuera de H."""
    for H in (3600.0, 3590.0, 45.0):
        resultado = _simular(lam=0.8, H=H)
        tiempos = [f.tiempo for f in resultado.traza]
        assert all(t0 <= t1 for t0, t1 in zip(tiempos, tiempos[1:])), "eventos fuera de orden cronológico"
        assert tiempos[-1] <= H, "evento posterior a H"
        assert all(v.t_salida is None or v.t_salida <= H for v in resultado.vehiculos), "salida posterior a H"
    # Si H corta un servicio ya iniciado, su salida no se programa: el vehículo queda pendiente en servicio.
    assert _simular(lam=0.8, H=45.0).metricas.en_servicio_final == 1


def test_sobresaturado_cola_crece() -> None:
    """En el escenario sobresaturado (ρef = 1.4) la cola residual crece ciclo a ciclo."""
    for semilla in SEMILLAS_TENDENCIA:
        residual = [c.cola_residual for c in _simular(lam=0.35, semilla=semilla).ciclos]
        tercio = len(residual) // 3
        primeros, ultimos = np.mean(residual[:tercio]), np.mean(residual[-tercio:])
        assert ultimos > primeros, f"semilla {semilla}: residual {primeros:.1f} → {ultimos:.1f} no crece"


def test_prioridad_eventos_simultaneos() -> None:
    """Eventos simultáneos se procesan en el orden salida → cambio de fase → llegada."""
    agenda = AgendaEventos()
    for tipo in (TipoEvento.LLEGADA, TipoEvento.CAMBIO_FASE, TipoEvento.SALIDA):
        agenda.programar(10.0, tipo)
    orden = [agenda.extraer().tipo for _ in range(3)]
    assert orden == [TipoEvento.SALIDA, TipoEvento.CAMBIO_FASE, TipoEvento.LLEGADA], f"orden de la agenda: {orden}"
    # Con fila saturada y g múltiplo de 1/μ, la última salida coincide con el paso a rojo:
    # se procesa antes que el cambio de fase y se cuenta en ese verde.
    resultado = _simular(lam=DEMANDA_SATURANTE, H=600.0)
    for ciclo in resultado.ciclos:
        simultaneos = [f.tipo for f in resultado.traza if f.tiempo == ciclo.fin_verde]
        assert simultaneos[:2] == [TipoEvento.SALIDA, TipoEvento.CAMBIO_FASE], f"t = {ciclo.fin_verde}: {simultaneos}"
    filas = [(f.tiempo, f.tipo) for f in resultado.traza]
    assert all(t0 < t1 or (t0 == t1 and e0 <= e1) for (t0, e0), (t1, e1) in zip(filas, filas[1:])), (
        "prioridad no respetada"
    )
    # Llegadas forzadas en el mismo instante que un cambio de fase (t = 30, inicio del verde)
    # y que una salida (t = 32): la llegada se procesa después de ambos.
    forzado = Simulador(ParametrosModelo(0.15, 30.0, 30.0, 0.5, 60.0), SEMILLA,
                        llegadas=LlegadasPrefijadas([5.0, 30.0, 32.0])).ejecutar()
    for instante, esperado in ((30.0, [TipoEvento.CAMBIO_FASE, TipoEvento.LLEGADA]),
                               (32.0, [TipoEvento.SALIDA, TipoEvento.LLEGADA])):
        tipos = [f.tipo for f in forzado.traza if f.tiempo == instante]
        assert tipos == esperado, f"t = {instante}: {tipos}"


def test_validacion_de_entradas() -> None:
    """Entradas fuera de dominio (λ < 0; g, r, μ o H ≤ 0) producen un error claro."""
    invalidos = ({"lam": -0.1}, {"g": 0.0}, {"r": -5.0}, {"mu": 0.0}, {"H": 0.0})
    validos = {"lam": 0.15, "g": 30.0, "r": 30.0, "mu": 0.5, "H": 3600.0}
    for cambio in invalidos:
        try:
            ParametrosModelo(**{**validos, **cambio})
        except ErrorConfiguracion:
            continue
        raise AssertionError(f"no se rechazó {cambio}")


PRUEBAS = (
    test_sin_llegadas_cola_vacia,
    test_sin_salidas_en_rojo,
    test_balance_de_vehiculos,
    test_reproducibilidad,
    test_capacidad_por_verde,
    test_orden_cronologico_y_horizonte,
    test_sobresaturado_cola_crece,
    test_prioridad_eventos_simultaneos,
    test_validacion_de_entradas,
)
"""Orden en que el menú ejecuta y muestra las pruebas."""

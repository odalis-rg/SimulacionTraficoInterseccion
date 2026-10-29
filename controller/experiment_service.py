"""Servicio de experimentos: la lógica de la aplicación, sin entrada ni salida.

Simula réplicas y escenarios con sus semillas registradas, compara con la
base, ejecuta el barrido de g y las pruebas de verificación, y mantiene la
configuración activa. Lo usan por igual la consola y la interfaz gráfica, y
no importa ninguna vista: las vistas dependen de él, no al revés.
"""

from __future__ import annotations

import importlib
import math
import time
from dataclasses import replace
from typing import Callable, Sequence

from config.settings import Configuracion, ErrorConfiguracion, Escenario
from controller.analysis import (
    AcumuladorEscenario,
    Comparacion,
    ResultadoBarrido,
    ResultadoEscenario,
    ResultadoPrueba,
    comparar_con_base,
)
from model.simulator import ResultadoReplica, Simulador
from model.statistics import INDICADORES_POR_CLAVE

MODULO_PRUEBAS = "tests.test_verification"
"""Módulo con la tupla ``PRUEBAS``; lo usan pytest, el menú y la interfaz gráfica."""

Progreso = Callable[[str, int, float], None]
"""Aviso al terminar un escenario: (nombre, réplicas, segundos)."""


def _descripcion(prueba: Callable[[], None]) -> str:
    """Primera línea del docstring de la prueba."""
    return (prueba.__doc__ or prueba.__name__).strip().splitlines()[0]


def _ejecutar_prueba(prueba: Callable[[], None]) -> tuple[bool, str]:
    try:
        prueba()
    except AssertionError as error:
        return False, str(error) or "aserción no cumplida"
    except Exception as error:  # noqa: BLE001 — cualquier fallo inesperado se informa como FALLÓ
        return False, f"{type(error).__name__}: {error}"
    return True, ""


class ServicioExperimentos:
    """Operaciones de la aplicación sobre la configuración activa."""

    def __init__(self, config: Configuracion) -> None:
        desconocidos = [c for c in config.salida.indicadores_comparacion if c not in INDICADORES_POR_CLAVE]
        if desconocidos:
            raise ErrorConfiguracion(
                f"Indicadores de comparación desconocidos: {', '.join(desconocidos)}. "
                f"Válidos: {', '.join(INDICADORES_POR_CLAVE)}."
            )
        self._config = config

    @property
    def config(self) -> Configuracion:
        """Configuración activa (inmutable; se reemplaza con los métodos ``configurar_*``)."""
        return self._config

    # ------------------------------------------------------------------
    # Cambios de configuración (validados por ``Configuracion``)
    # ------------------------------------------------------------------
    def configurar_simulacion(self, mu: float, H: float, n_replicas: int) -> None:
        """Cambia μ, H y n; lanza ``ErrorConfiguracion`` si algún valor no es válido."""
        simulacion = replace(self._config.simulacion, mu=mu, H=H, n_replicas=n_replicas)
        self._config = replace(self._config, simulacion=simulacion)

    def configurar_barrido(self, lam: float, T: float, valores_g: Sequence[float]) -> None:
        """Cambia λ, T y los g del barrido; lanza ``ErrorConfiguracion`` si no son válidos."""
        barrido = replace(self._config.barrido, lam=lam, T=T, valores_g=tuple(valores_g))
        self._config = replace(self._config, barrido=barrido)

    def agregar_escenario(self, nombre: str, lam: float, g: float, r: float) -> Escenario:
        """Agrega un escenario validado; lanza ``ErrorConfiguracion`` si no es válido o ya existe."""
        nombre = nombre.strip()
        if self._config.buscar_escenario(nombre) is not None:
            raise ErrorConfiguracion(f"Ya existe un escenario llamado '{nombre}'.")
        escenario = Escenario(nombre, lam, g, r)
        self._config = replace(self._config, escenarios=self._config.escenarios + (escenario,))
        return escenario

    # ------------------------------------------------------------------
    # Simulación
    # ------------------------------------------------------------------
    def simular_replica(self, escenario: Escenario, replica: int) -> ResultadoReplica:
        """Una réplica con su semilla registrada (semilla_base + i)."""
        sim = self._config.simulacion
        return Simulador(escenario.parametros(sim), sim.semilla(replica)).ejecutar()

    def simular_escenario(self, escenario: Escenario) -> ResultadoEscenario:
        """Las n réplicas del escenario, consolidadas para el análisis."""
        sim = self._config.simulacion
        parametros = escenario.parametros(sim)
        acumulador = AcumuladorEscenario(escenario, parametros, self._config.salida.replica_detalle)
        for replica in range(1, sim.n_replicas + 1):
            acumulador.agregar(replica, Simulador(parametros, sim.semilla(replica)).ejecutar())
        return acumulador.consolidar(sim.confianza)

    def simular_escenarios(self, escenarios: Sequence[Escenario],
                           progreso: Progreso | None = None) -> list[ResultadoEscenario]:
        """Simula varios escenarios y avisa al terminar cada uno."""
        resultados = []
        for escenario in escenarios:
            inicio = time.perf_counter()
            resultados.append(self.simular_escenario(escenario))
            if progreso:
                progreso(escenario.nombre, self._config.simulacion.n_replicas, time.perf_counter() - inicio)
        return resultados

    def resultado_base(self, resultados: Sequence[ResultadoEscenario],
                       progreso: Progreso | None = None) -> ResultadoEscenario | None:
        """Resultado del escenario base; se simula si hace falta y hay escenarios con su misma λ."""
        base = self._config.escenario(self._config.escenario_base)
        for resultado in resultados:
            if resultado.escenario == base:
                return resultado
        if any(math.isclose(r.parametros.lam, base.lam) for r in resultados):
            return self.simular_escenarios([base], progreso)[0]
        return None

    def comparar(self, resultados: Sequence[ResultadoEscenario],
                 base: ResultadoEscenario | None) -> Comparacion | None:
        """Comparación porcentual frente a la base, o None si no hay nada que comparar."""
        if base is None:
            return None
        comparacion = comparar_con_base(resultados, base, self._config.salida.indicadores_comparacion)
        return comparacion if comparacion.filas or comparacion.no_comparables else None

    def simular_barrido(self, progreso: Progreso | None = None) -> ResultadoBarrido:
        """Barrido de g con λ y T fijos (r = T − g)."""
        b = self._config.barrido
        return ResultadoBarrido.desde(b.lam, b.T, self.simular_escenarios(b.escenarios(), progreso))

    # ------------------------------------------------------------------
    # Verificación
    # ------------------------------------------------------------------
    @staticmethod
    def correr_pruebas() -> list[ResultadoPrueba]:
        """Ejecuta las pruebas de ``tests/test_verification.py`` y devuelve su resultado."""
        pruebas = importlib.import_module(MODULO_PRUEBAS).PRUEBAS
        return [ResultadoPrueba(i, _descripcion(p), *_ejecutar_prueba(p)) for i, p in enumerate(pruebas, start=1)]

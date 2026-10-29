"""Exportación de resultados ya calculados a la carpeta de salida (CSV y PNG).

Reúne en un solo lugar qué archivos produce cada experimento; la consola y la
interfaz gráfica lo reciben ya construido, cada uno con su propio generador de
gráficas (mostrar o solo guardar).
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from controller.analysis import Comparacion, ResultadoBarrido, ResultadoEscenario
from model.simulator import ResultadoReplica
from view.csv_export import ExportadorCSV
from view.plots import GeneradorGraficas


class ExportadorResultados:
    """Guarda tablas y figuras de escenarios, barrido y traza."""

    def __init__(self, csv: ExportadorCSV, graficas: GeneradorGraficas) -> None:
        self._csv = csv
        self._graficas = graficas

    def escenarios(self, resultados: Sequence[ResultadoEscenario], comparacion: Comparacion | None) -> list[Path]:
        """Resumen, réplicas, ciclos, comparación y las cinco figuras de los escenarios."""
        rutas: list[Path | None] = [self._csv.resumen(resultados)]
        rutas += [self._csv.replicas(r) for r in resultados]
        rutas += [self._csv.ciclos(r.nombre, r.replica_detalle, r.detalle) for r in resultados]
        if comparacion is not None and comparacion.filas:
            rutas.append(self._csv.comparacion(resultados, comparacion))
        rutas += [
            self._graficas.cola_en_el_tiempo(resultados),
            self._graficas.barras_indicador(resultados, "q_media"),
            self._graficas.barras_indicador(resultados, "wq_media"),
            self._graficas.residual_por_ciclo(resultados),
            self._graficas.histograma_esperas(resultados),
        ]
        return [r for r in rutas if r is not None]

    def barrido(self, barrido: ResultadoBarrido, ventana: float) -> list[Path]:
        """Tabla I y sus dos figuras."""
        rutas = [self._csv.barrido(barrido), self._graficas.colas_superpuestas(barrido, ventana),
                 self._graficas.indicadores_vs_g(barrido)]
        return [r for r in rutas if r is not None]

    def traza(self, nombre: str, replica: int, resultado: ResultadoReplica) -> list[Path]:
        """Traza completa y ciclos de una réplica."""
        return [self._csv.traza(nombre, replica, resultado), self._csv.ciclos(nombre, replica, resultado)]

    def mostrar_graficas(self) -> str | None:
        """Abre las figuras pendientes (si se pidió mostrarlas); devuelve un aviso si no se puede."""
        return self._graficas.mostrar()

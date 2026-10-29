"""Pestañas que presentan la simulación de escenarios: tablas, gráficas y ciclos."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from matplotlib.figure import Figure

from model.statistics import INDICADORES_POR_CLAVE
from view.formato import NOTA_REDUCCION_TABLA, celda_ciclo, media_ic, tabla_comparacion, texto_no_comparables
from view.gui.contratos import SimulacionEscenarios
from view.gui.diseno import DisenoVentana
from view.gui.pestanas.base import Pestana
from view.gui.widgets import Columna, Tabla
from view.plots import (
    dibujar_barras_indicador,
    dibujar_cola_en_el_tiempo,
    dibujar_histograma_esperas,
    dibujar_residual_por_ciclo,
)
from view.style import PALETA

COLUMNAS_RESUMEN = ("q_media", "q_max", "wq_media", "capacidad_efectiva", "residual_medio")
"""Indicadores (media ± IC) de la tabla de resultados; el resto queda en la consola y los CSV."""
AVISO_SIN_RESULTADOS = "Elija escenarios a la izquierda y pulse «Simular» (F5)."
NOTA_SATURADOS = "En rojo: ρef ≥ 1, la cola puede crecer ciclo a ciclo (ρef figura en la lista de escenarios)."

FIGURAS: tuple[tuple[str, Callable[[Figure, SimulacionEscenarios], None]], ...] = (
    ("Q(t)", lambda figura, s: dibujar_cola_en_el_tiempo(figura, s.resultados)),
    ("Cola media", lambda figura, s: dibujar_barras_indicador(figura, s.resultados, "q_media", s.confianza)),
    ("Espera media", lambda figura, s: dibujar_barras_indicador(figura, s.resultados, "wq_media", s.confianza)),
    ("Cola residual", lambda figura, s: dibujar_residual_por_ciclo(figura, s.resultados)),
    ("Esperas", lambda figura, s: dibujar_histograma_esperas(figura, s.resultados)),
)
"""Subpestañas de «Gráficas»: (título, cómo dibujarla). Para agregar una figura basta otra fila."""


class PestanaResultados(Pestana):
    """Indicadores por escenario (media ± IC) y comparación porcentual con la base."""

    def __init__(self, cuaderno: ttk.Notebook, diseno: DisenoVentana) -> None:
        super().__init__(cuaderno, "Resultados", diseno)
        d = diseno
        columnas: list[Columna] = [("Escenario", d.columna_nombre, "w")]
        columnas += [(f"{INDICADORES_POR_CLAVE[c].simbolo} ({INDICADORES_POR_CLAVE[c].unidad})", d.columna_valor, "e")
                     for c in COLUMNAS_RESUMEN]
        self._titulo_resumen = self._titulo("Indicadores por escenario (media ± IC)")
        self._titulo_resumen.pack(anchor="w")
        self._tabla_resumen = Tabla(self.marco, columnas, d.filas_resumen, horizontal=False)
        self._tabla_resumen.arbol.tag_configure("saturado", foreground=PALETA.rojo)
        self._tabla_resumen.pack(fill=tk.X, pady=(d.separacion, 0))
        self._nota(self.marco, NOTA_SATURADOS).pack(anchor="w", pady=(d.separacion // 2, 0))
        self._titulo_comparacion = self._titulo("Comparación con la base (misma λ)")
        self._titulo_comparacion.pack(anchor="w", pady=(3 * d.separacion, 0))
        self._tabla_comparacion = Tabla(self.marco, [("Indicador", d.columna_nombre, "w")], d.filas_resumen,
                                        horizontal=False)
        self._tabla_comparacion.pack(fill=tk.X, pady=(d.separacion, 0))
        self._nota_comparacion = self._nota(self.marco)
        self._nota_comparacion.pack(anchor="w", pady=(d.separacion // 2, 0))

    def mostrar_resultados(self, simulacion: SimulacionEscenarios) -> None:
        resultados = simulacion.resultados
        n = len(resultados[0].metricas)
        self._titulo_resumen.configure(
            text=f"Indicadores por escenario (media ± IC {simulacion.confianza:.0%}, {n} réplicas)")
        filas = [(r.nombre, *(media_ic(r.resumen[c]) for c in COLUMNAS_RESUMEN)) for r in resultados]
        self._tabla_resumen.cargar(filas, ["saturado" if r.rho_ef >= 1 else "" for r in resultados])
        self._mostrar_comparacion(simulacion)

    def _mostrar_comparacion(self, simulacion: SimulacionEscenarios) -> None:
        comparacion = simulacion.comparacion
        if comparacion is None or not comparacion.filas:
            self._tabla_comparacion.limpiar()
            self._nota_comparacion.configure(text="Sin comparación: ningún escenario simulado comparte λ con la base.")
            return
        d = self._d
        encabezados, filas = tabla_comparacion(comparacion)
        self._titulo_comparacion.configure(text=f"Comparación con «{comparacion.base}» (misma λ)")
        self._tabla_comparacion.columnas([(encabezados[0], d.columna_nombre, "w"),
                                          (encabezados[1], d.columna_corta, "e"),
                                          *((e, d.columna_valor + d.columna_corta, "e") for e in encabezados[2:])])
        self._tabla_comparacion.arbol.configure(height=len(filas))
        self._tabla_comparacion.cargar(filas)
        notas = [NOTA_REDUCCION_TABLA]
        if comparacion.no_comparables:
            notas.append(texto_no_comparables(comparacion.no_comparables))
        self._nota_comparacion.configure(text="\n".join(notas))


class PestanaGraficas(Pestana):
    """Una subpestaña por figura de ``FIGURAS``, a todo el espacio disponible."""

    def __init__(self, cuaderno: ttk.Notebook, diseno: DisenoVentana) -> None:
        super().__init__(cuaderno, "Gráficas", diseno)
        sub = self._subpestanas()
        self._paneles = [(self._panel_figura(sub, titulo, AVISO_SIN_RESULTADOS), dibujar)
                         for titulo, dibujar in FIGURAS]

    def mostrar_resultados(self, simulacion: SimulacionEscenarios) -> None:
        for panel, dibujar in self._paneles:
            panel.dibujar(dibujar, simulacion)


class PestanaCiclos(Pestana):
    """Vehículos atendidos / cola residual al final de cada verde (pestaña técnica)."""

    def __init__(self, cuaderno: ttk.Notebook, diseno: DisenoVentana) -> None:
        super().__init__(cuaderno, "Ciclos", diseno)
        self._titulo_ciclos = self._titulo("Vehículos atendidos / cola residual al final de cada verde")
        self._titulo_ciclos.pack(anchor="w")
        self._tabla = Tabla(self.marco, [("Ciclo", diseno.columna_corta, "e")], diseno.filas_tabla)
        self._tabla.pack(fill=tk.BOTH, expand=True, pady=(diseno.separacion, 0))

    def mostrar_resultados(self, simulacion: SimulacionEscenarios) -> None:
        resultados, d = simulacion.resultados, self._d
        self._titulo_ciclos.configure(text=f"Vehículos atendidos / cola residual al final de cada verde "
                                           f"(réplica {resultados[0].replica_detalle})")
        self._tabla.columnas([("Ciclo", d.columna_corta, "e"), *((r.nombre, d.columna_valor, "e") for r in resultados)])
        total = max(len(r.detalle.ciclos) for r in resultados)
        self._tabla.cargar(
            (str(k + 1), *(celda_ciclo(r.detalle.ciclos[k] if k < len(r.detalle.ciclos) else None) for r in resultados))
            for k in range(total)
        )

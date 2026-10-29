"""Pestaña técnica de la traza: eventos de una réplica con su estado del sistema."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from config.settings import Configuracion, ErrorConfiguracion
from controller.experiment_service import ServicioExperimentos
from model.simulator import ResultadoReplica
from view.formato import ENCABEZADOS_TRAZA, fila_traza, texto_balance, texto_censura
from view.gui.diseno import DisenoVentana
from view.gui.entradas import leer_entero
from view.gui.pestanas.base import Pestana
from view.gui.tareas import GestorTareas
from view.gui.widgets import Tabla, boton, informar, mostrar_error

ORDEN_SIMULTANEOS = "Eventos simultáneos: SALIDA → CAMBIO_FASE → LLEGADA."
ANCLAJES_TRAZA = ("e", "w", "w", "w", "e", "w", "e")
"""Alineación de cada columna de ``ENCABEZADOS_TRAZA``."""


class PestanaTraza(Pestana):
    """Simula una réplica elegida y lista todos sus eventos."""

    def __init__(self, cuaderno: ttk.Notebook, diseno: DisenoVentana, servicio: ServicioExperimentos,
                 tareas: GestorTareas) -> None:
        super().__init__(cuaderno, "Traza", diseno)
        self._servicio = servicio
        self._tareas = tareas
        d = diseno
        self._escenario = tk.StringVar()
        self._replica = tk.StringVar(value=str(servicio.config.salida.replica_detalle))
        fila = self._fila()
        self._combo = ttk.Combobox(fila, textvariable=self._escenario, state="readonly", width=16)
        self._campo(fila, "Escenario", self._combo)
        self._selector_replica = ttk.Spinbox(fila, textvariable=self._replica, from_=1, width=5)
        self._campo(fila, "Réplica", self._selector_replica)
        tareas.bloqueable(boton(fila, "Ver traza", self._ver_traza, principal=True)).pack(side=tk.LEFT)
        self._info = self._nota(self.marco, ORDEN_SIMULTANEOS)
        self._info.pack(anchor="w", pady=(d.separacion, 0))
        columnas = [(t, d.columna_valor - d.margen, a) for t, a in zip(ENCABEZADOS_TRAZA, ANCLAJES_TRAZA)]
        self._tabla = Tabla(self.marco, columnas, d.filas_tabla, horizontal=False)
        self._tabla.pack(fill=tk.BOTH, expand=True, pady=(d.separacion, 0))
        self.configuracion_cambiada(servicio.config)

    def configuracion_cambiada(self, config: Configuracion) -> None:
        self._combo.configure(values=[e.nombre for e in config.escenarios])
        self._selector_replica.configure(to=config.simulacion.n_replicas)

    def _ver_traza(self) -> None:
        if not self._tareas.libre():
            return
        nombre = self._escenario.get()
        if not nombre:
            informar(self.marco, "Traza", "Elija un escenario.")
            return
        try:
            replica = leer_entero(self._replica.get(), "La réplica", minimo=1)
        except ErrorConfiguracion as error:
            mostrar_error(self.marco, error)
            return
        escenario = self._servicio.config.escenario(nombre)
        self._tareas.ejecutar(f"Simulando la réplica {replica} de «{nombre}»…",
                              lambda: self._servicio.simular_replica(escenario, replica), self._mostrar)

    def _mostrar(self, resultado: ResultadoReplica) -> None:
        self._tabla.cargar(fila_traza(f) for f in resultado.traza)
        textos = [f"{len(resultado.traza)} eventos (semilla {resultado.semilla}). Q(t) = vehículos en espera, sin el "
                  f"que está en servicio. {ORDEN_SIMULTANEOS}",
                  texto_balance(resultado.metricas, resultado.parametros.H)]
        censura = texto_censura(resultado.metricas)
        if censura:
            textos.append(censura)
        self._info.configure(text="\n".join(textos))

"""Panel izquierdo: elegir escenarios, ajustar los parámetros y lanzar la simulación."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Iterable, Sequence

from config.settings import Configuracion, ErrorConfiguracion, Escenario
from controller.experiment_service import ServicioExperimentos
from model.statistics import rho_efectivo
from view.gui.contratos import SimulacionEscenarios
from view.gui.diseno import DisenoVentana, Estilo
from view.gui.entradas import leer_entero, leer_real
from view.gui.tareas import GestorTareas
from view.gui.widgets import DialogoFormulario, Tabla, boton, informar

CAMPOS_ESCENARIO_NUEVO = (("Nombre", "Personalizado"), ("λ (veh/s)", "0.2"), ("g (s)", "30"), ("r (s)", "30"))
"""Campos del diálogo «Nuevo escenario» con su valor inicial sugerido."""


class PanelEscenarios(ttk.Frame):
    """Lista de escenarios (con su ρef), resumen de parámetros y botón «Simular».

    Al cambiar la configuración avisa con ``al_cambiar_configuracion`` y al
    terminar una simulación entrega el resultado a ``al_simular``; quién los
    muestra lo decide la ventana.
    """

    def __init__(self, padre: tk.Misc, diseno: DisenoVentana, servicio: ServicioExperimentos, tareas: GestorTareas,
                 al_cambiar_configuracion: Callable[[], None],
                 al_simular: Callable[[SimulacionEscenarios], None]) -> None:
        m, s = diseno.margen, diseno.separacion
        super().__init__(padre, width=diseno.ancho_panel, padding=(2 * m, m, m, m))
        self.pack_propagate(False)
        self._d = diseno
        self._servicio = servicio
        self._tareas = tareas
        self._al_cambiar_configuracion = al_cambiar_configuracion
        self._al_simular = al_simular
        self._resumen_parametros = tk.StringVar()
        ttk.Label(self, text="Escenarios", style=Estilo.SECCION).pack(anchor="w")
        ttk.Label(self, text="Ctrl o Shift para elegir varios", style=Estilo.NOTA).pack(anchor="w")
        self._tabla = Tabla(self, [("Escenario", diseno.columna_escenario, "w"), ("λ", diseno.columna_lambda, "e"),
                                   ("g", diseno.columna_tiempo, "e"), ("r", diseno.columna_tiempo, "e"),
                                   ("ρef", diseno.columna_rho, "e")], diseno.filas_escenarios, horizontal=False)
        self._tabla.pack(fill=tk.X, pady=(s, 0))
        fila = ttk.Frame(self)
        fila.pack(fill=tk.X, pady=(s, 0))
        botones = (ttk.Button(fila, text="Todos", command=self._seleccionar_todos),
                   ttk.Button(fila, text="Ninguno", command=lambda: self._seleccionar(())),
                   tareas.bloqueable(boton(fila, "＋ Nuevo…", self.nuevo_escenario)))
        for columna, control in enumerate(botones):  # tres columnas del mismo ancho
            fila.columnconfigure(columna, weight=1, uniform="botones")
            control.grid(row=0, column=columna, sticky="ew", padx=(0 if columna == 0 else s // 2, 0))
        ttk.Separator(self).pack(fill=tk.X, pady=2 * s)
        ttk.Label(self, text="Parámetros", style=Estilo.SECCION).pack(anchor="w")
        fila = ttk.Frame(self)
        fila.pack(fill=tk.X, pady=(s // 2, 0))
        ttk.Label(fila, textvariable=self._resumen_parametros, style=Estilo.NOTA, justify=tk.LEFT).pack(side=tk.LEFT)
        tareas.bloqueable(boton(fila, "Cambiar…", self.cambiar_parametros)).pack(side=tk.RIGHT)
        tareas.bloqueable(boton(self, "▶  Simular", self.simular, principal=True)).pack(fill=tk.X, pady=(3 * s, 0))
        self.configuracion_cambiada(servicio.config)
        self._seleccionar_todos()

    # ------------------------------------------------------------------
    # Lista de escenarios
    # ------------------------------------------------------------------
    def configuracion_cambiada(self, config: Configuracion) -> None:
        """Recarga la lista (con su ρef) conservando la selección, y el resumen de parámetros."""
        anteriores = self.seleccionados()
        filas = []
        for e in config.escenarios:
            p = e.parametros(config.simulacion)
            filas.append((e.nombre, f"{p.lam:g}", f"{p.g:g}", f"{p.r:g}", f"{rho_efectivo(p):.2f}"))
        self._tabla.cargar(filas)
        self._seleccionar(anteriores)
        sim = config.simulacion
        self._resumen_parametros.set(f"μ = {sim.mu:g} veh/s\nH = {sim.H:g} s\n{sim.n_replicas} réplicas")

    def seleccionados(self) -> list[str]:
        """Nombres de los escenarios seleccionados, en el orden de la lista."""
        arbol = self._tabla.arbol
        return [arbol.item(item, "values")[0] for item in arbol.selection()]

    def _seleccionar(self, nombres: Iterable[str]) -> None:
        """Selecciona exactamente los escenarios indicados."""
        arbol, elegidos = self._tabla.arbol, set(nombres)
        arbol.selection_set([item for item in arbol.get_children() if arbol.item(item, "values")[0] in elegidos])

    def _seleccionar_todos(self) -> None:
        self._tabla.arbol.selection_set(self._tabla.arbol.get_children())

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def simular(self) -> None:
        """Simula en segundo plano los escenarios seleccionados (y la base si hace falta comparar)."""
        if not self._tareas.libre():
            return
        nombres = self.seleccionados()
        if not nombres:
            informar(self, "Simular", "Seleccione al menos un escenario.")
            return
        config = self._servicio.config
        escenarios = [config.escenario(nombre) for nombre in nombres]
        self._tareas.ejecutar(f"Simulando {len(escenarios)} escenario(s) × {config.simulacion.n_replicas} réplicas…",
                              lambda: self._simular(escenarios), self._al_simular)

    def _simular(self, escenarios: Sequence[Escenario]) -> SimulacionEscenarios:
        """Se ejecuta en el hilo de trabajo: solo calcula."""
        servicio, progreso = self._servicio, self._tareas.progreso
        resultados = servicio.simular_escenarios(escenarios, progreso)
        base = servicio.resultado_base(resultados, progreso)
        return SimulacionEscenarios(resultados, servicio.comparar(resultados, base),
                                    servicio.config.simulacion.confianza)

    def nuevo_escenario(self) -> None:
        """Diálogo para agregar un escenario; queda seleccionado junto con los anteriores."""
        if not self._tareas.libre():
            return

        def aceptar(valores: list[str]) -> str | None:
            nombre, lam, g, r = valores
            try:
                escenario = self._servicio.agregar_escenario(nombre, leer_real(lam, "λ"), leer_real(g, "g"),
                                                             leer_real(r, "r"))
            except ErrorConfiguracion as error:
                return str(error)
            self._al_cambiar_configuracion()
            self._seleccionar([*self.seleccionados(), escenario.nombre])
            self._tareas.informar(f"Escenario «{escenario.nombre}» agregado y seleccionado.")
            return None

        DialogoFormulario(self.winfo_toplevel(), "Nuevo escenario", CAMPOS_ESCENARIO_NUEVO, aceptar, self._d.margen)

    def cambiar_parametros(self) -> None:
        """Diálogo para cambiar μ, H y el número de réplicas."""
        if not self._tareas.libre():
            return
        sim = self._servicio.config.simulacion

        def aceptar(valores: list[str]) -> str | None:
            mu, H, n = valores
            try:
                self._servicio.configurar_simulacion(leer_real(mu, "μ"), leer_real(H, "H"), leer_entero(n, "n"))
            except ErrorConfiguracion as error:
                return str(error)
            self._al_cambiar_configuracion()
            self._tareas.informar("Parámetros actualizados; vuelva a simular para aplicarlos.")
            return None

        DialogoFormulario(self.winfo_toplevel(), "Parámetros de simulación",
                          (("μ (veh/s)", f"{sim.mu:g}"), ("H (s)", f"{sim.H:g}"), ("Réplicas n", str(sim.n_replicas))),
                          aceptar, self._d.margen, nota=f"La réplica i usa la semilla {sim.semilla_base} + i.")

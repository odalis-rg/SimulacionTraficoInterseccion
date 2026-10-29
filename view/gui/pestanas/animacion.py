"""Pestaña de animación: reproduce dentro de la ventana una réplica ya simulada."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from config.settings import Configuracion, ErrorConfiguracion
from controller.experiment_service import ServicioExperimentos
from model.simulator import ResultadoReplica
from view.gui.contratos import AnimadorIncrustado, ControlAnimacion
from view.gui.diseno import DisenoVentana, Estilo
from view.gui.entradas import leer_real
from view.gui.pestanas.base import Pestana
from view.gui.tareas import GestorTareas
from view.gui.widgets import boton, informar, mostrar_error

TEXTO_PAUSA = "❚❚  Pausa"
TEXTO_REANUDAR = "▶  Reanudar"


class PestanaAnimacion(Pestana):
    """Elige escenario y velocidad, simula la réplica de detalle y la reproduce con pausa y reinicio."""

    def __init__(self, cuaderno: ttk.Notebook, diseno: DisenoVentana, servicio: ServicioExperimentos,
                 animador: AnimadorIncrustado, tareas: GestorTareas) -> None:
        super().__init__(cuaderno, "Animación", diseno)
        self._servicio = servicio
        self._animador = animador
        self._tareas = tareas
        self._control: ControlAnimacion | None = None
        self._lienzo: FigureCanvasTkAgg | None = None
        anim, d = servicio.config.animacion, diseno
        self._escenario = tk.StringVar(value=anim.escenario)
        self._velocidad = tk.StringVar(value=f"{anim.velocidad:g}")
        fila = self._fila()
        self._combo = ttk.Combobox(fila, textvariable=self._escenario, state="readonly", width=16)
        self._campo(fila, "Escenario", self._combo)
        self._campo(fila, "Velocidad ×",
                    ttk.Spinbox(fila, textvariable=self._velocidad, from_=1, to=d.velocidad_maxima, width=4))
        tareas.bloqueable(boton(fila, "▶  Reproducir", self._reproducir, principal=True)).pack(side=tk.LEFT)
        self._boton_pausa = ttk.Button(fila, text=TEXTO_PAUSA, command=self._alternar_pausa, state=tk.DISABLED)
        self._boton_pausa.pack(side=tk.LEFT, padx=d.separacion)
        self._boton_reinicio = ttk.Button(fila, text="⟲  Reiniciar", command=self._reiniciar, state=tk.DISABLED)
        self._boton_reinicio.pack(side=tk.LEFT)
        self._area = ttk.Frame(self.marco)
        self._area.pack(fill=tk.BOTH, expand=True, pady=(d.separacion, 0))
        self._aviso = ttk.Label(self._area, style=Estilo.NOTA,
                                text=f"Elija un escenario y pulse «Reproducir». Se muestran los primeros "
                                     f"{anim.ventana_s:g} s de la simulación.")
        self._aviso.pack(expand=True)
        self.configuracion_cambiada(servicio.config)

    def configuracion_cambiada(self, config: Configuracion) -> None:
        self._combo.configure(values=[e.nombre for e in config.escenarios])

    def detener(self) -> None:
        """Detiene la animación en curso y retira su figura."""
        if self._control is not None:
            self._control.detener()
            self._control = None
        if self._lienzo is not None:
            self._lienzo.get_tk_widget().destroy()
            self._lienzo = None

    def _reproducir(self) -> None:
        if not self._tareas.libre():
            return
        nombre = self._escenario.get()
        if not nombre:
            informar(self.marco, "Animación", "Elija un escenario.")
            return
        try:
            velocidad = leer_real(self._velocidad.get(), "La velocidad", mayor_que=0)
        except ErrorConfiguracion as error:
            mostrar_error(self.marco, error)
            return
        config = self._servicio.config
        escenario, replica = config.escenario(nombre), config.salida.replica_detalle
        self._tareas.ejecutar(f"Preparando la animación de «{nombre}»…",
                              lambda: self._servicio.simular_replica(escenario, replica),
                              lambda resultado: self._iniciar(resultado, velocidad))

    def _iniciar(self, resultado: ResultadoReplica, velocidad: float) -> None:
        self.detener()
        self._aviso.pack_forget()
        figura = Figure(dpi=self._d.dpi_graficas)
        self._lienzo = FigureCanvasTkAgg(figura, master=self._area)
        self._lienzo.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self._control = self._animador.crear_en(figura, resultado, velocidad)
        self._lienzo.draw()
        for control in (self._boton_pausa, self._boton_reinicio):
            control.state(["!disabled"])
        self._boton_pausa.configure(text=TEXTO_PAUSA)

    def _alternar_pausa(self) -> None:
        if self._control is not None:
            self._control.alternar_pausa()
            self._boton_pausa.configure(text=TEXTO_REANUDAR if self._control.pausado else TEXTO_PAUSA)

    def _reiniciar(self) -> None:
        if self._control is not None:
            self._control.reiniciar()
            self._boton_pausa.configure(text=TEXTO_PAUSA)

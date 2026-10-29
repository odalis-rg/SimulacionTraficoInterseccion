"""Pestaña de verificación: ejecuta las pruebas del modelo y muestra su resultado."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Sequence

from controller.analysis import ResultadoPrueba
from view.gui.diseno import DisenoVentana, Estilo
from view.gui.pestanas.base import Pestana
from view.gui.tareas import GestorTareas
from view.gui.widgets import Tabla, boton
from view.style import PALETA


class PestanaVerificacion(Pestana):
    """Tabla de pruebas (OK en verde, FALLÓ en rojo) con un resumen de las superadas."""

    def __init__(self, cuaderno: ttk.Notebook, diseno: DisenoVentana, tareas: GestorTareas,
                 correr_pruebas: Callable[[], Sequence[ResultadoPrueba]]) -> None:
        super().__init__(cuaderno, "Verificación", diseno)
        self._tareas = tareas
        self._correr_pruebas = correr_pruebas
        d = diseno
        fila = self._fila()
        tareas.bloqueable(boton(fila, "▶  Ejecutar pruebas", self._ejecutar, principal=True)).pack(side=tk.LEFT)
        self._resumen = ttk.Label(fila, text="", style=Estilo.SECCION)
        self._resumen.pack(side=tk.LEFT, padx=2 * d.margen)
        self._tabla = Tabla(self.marco, [("#", d.columna_corta // 2, "e"), ("Prueba", d.columna_texto, "w"),
                                         ("Resultado", d.columna_corta + d.margen * 3, "center"),
                                         ("Detalle", d.columna_nombre, "w")], d.filas_tabla, horizontal=False)
        self._tabla.arbol.tag_configure("ok", foreground=PALETA.verde)
        self._tabla.arbol.tag_configure("fallo", foreground=PALETA.rojo)
        self._tabla.pack(fill=tk.BOTH, expand=True, pady=(d.separacion, 0))

    def _ejecutar(self) -> None:
        if self._tareas.libre():
            self._tareas.ejecutar("Ejecutando pruebas de verificación…", self._correr_pruebas, self._mostrar)

    def _mostrar(self, pruebas: Sequence[ResultadoPrueba]) -> None:
        self._tabla.cargar([(str(p.numero), p.descripcion, "OK" if p.exito else "FALLÓ", p.detalle) for p in pruebas],
                           ["ok" if p.exito else "fallo" for p in pruebas])
        exitos = sum(p.exito for p in pruebas)
        self._resumen.configure(text=f"{exitos} de {len(pruebas)} pruebas superadas",
                                foreground=PALETA.verde if exitos == len(pruebas) else PALETA.rojo)

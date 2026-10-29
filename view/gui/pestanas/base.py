"""Base común de las pestañas del cuaderno principal."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from view.gui.diseno import DisenoVentana, Estilo
from view.gui.widgets import PanelFigura, nota_ajustable


class Pestana:
    """Marco de una pestaña con las piezas de diseño que comparten todas.

    ``marco`` es el contenido de la pestaña: la ventana lo usa para
    seleccionarla, ocultarla o mostrarla.
    """

    def __init__(self, cuaderno: ttk.Notebook, titulo: str, diseno: DisenoVentana) -> None:
        self._d = diseno
        self.marco = ttk.Frame(cuaderno, padding=diseno.margen)
        cuaderno.add(self.marco, text=titulo)

    def _fila(self) -> ttk.Frame:
        """Fila horizontal de controles en la parte superior."""
        fila = ttk.Frame(self.marco)
        fila.pack(fill=tk.X)
        return fila

    def _campo(self, fila: ttk.Frame, etiqueta: str, control: tk.Widget) -> None:
        """Etiqueta seguida de su control, de izquierda a derecha."""
        ttk.Label(fila, text=etiqueta).pack(side=tk.LEFT)
        control.pack(side=tk.LEFT, padx=(self._d.separacion // 2, self._d.margen))

    def _titulo(self, texto: str) -> ttk.Label:
        return ttk.Label(self.marco, text=texto, style=Estilo.SECCION)

    def _nota(self, padre: tk.Misc, texto: str = "") -> ttk.Label:
        return nota_ajustable(padre, texto, self._d.margen)

    def _subpestanas(self) -> ttk.Notebook:
        cuaderno = ttk.Notebook(self.marco, style=Estilo.SUBCUADERNO)
        cuaderno.pack(fill=tk.BOTH, expand=True, pady=(self._d.separacion, 0))
        return cuaderno

    def _panel_figura(self, cuaderno: ttk.Notebook, titulo: str, aviso: str) -> PanelFigura:
        panel = PanelFigura(cuaderno, aviso, self._d.fuente_aviso, self._d.dpi_graficas)
        cuaderno.add(panel, text=titulo)
        return panel

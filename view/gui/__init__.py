"""Interfaz gráfica para exponer la simulación (Tkinter + matplotlib).

``abrir_interfaz`` crea la ventana con las piezas que recibe ya construidas
(servicio de experimentos, exportador y animador) y bloquea hasta cerrarla.
Las simulaciones corren en segundo plano a través del servicio; la interfaz
solo presenta resultados ya calculados y nunca toca el modelo.
"""

from __future__ import annotations

import os
import tkinter as tk

from config.entorno import consejo_sandbox
from controller.experiment_service import ServicioExperimentos
from view.gui.contratos import AnimadorIncrustado, Exportador
from view.gui.ventana import VentanaPrincipal

__all__ = ["abrir_interfaz"]


def abrir_interfaz(servicio: ServicioExperimentos, exportador: Exportador,
                   animador: AnimadorIncrustado) -> str | None:
    """Abre la ventana y bloquea hasta cerrarla; devuelve un mensaje si no se pudo abrir."""
    try:
        raiz = tk.Tk()
    except tk.TclError as error:
        return _explicar_fallo(error)
    VentanaPrincipal(raiz, servicio, exportador, animador)
    raiz.mainloop()
    return None


def _explicar_fallo(error: tk.TclError) -> str:
    """Causa probable de que Tk no pueda abrir una ventana y cómo resolverla."""
    sandbox = consejo_sandbox()
    if sandbox:
        return f"No se pudo abrir la interfaz gráfica. {sandbox}"
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return ("No se pudo abrir la interfaz gráfica: este proceso no tiene DISPLAY ni WAYLAND_DISPLAY; "
                "ejecútelo desde una terminal abierta en el escritorio (no por SSH ni consola TTY).")
    return f"No se pudo abrir la interfaz gráfica: {error}."

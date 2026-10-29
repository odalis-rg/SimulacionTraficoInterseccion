"""Diagnóstico del backend gráfico de matplotlib (¿puede abrir ventanas?)."""

from __future__ import annotations

import os

import matplotlib
import matplotlib.pyplot as plt

from config.entorno import consejo_sandbox

_BACKENDS_NO_INTERACTIVOS = {"agg", "pdf", "ps", "svg", "pgf", "cairo", "template"}
_BACKENDS_ALTERNATIVOS = ("TkAgg", "GTK4Agg", "GTK3Agg", "QtAgg")
"""Backends con ventanas que se prueban si matplotlib eligió uno sin ventanas."""


def _es_interactivo(backend: str) -> bool:
    nombre = backend.lower()
    return nombre not in _BACKENDS_NO_INTERACTIVOS and "inline" not in nombre


def diagnostico_grafico() -> str | None:
    """None si matplotlib puede abrir ventanas; si no, la causa y cómo resolverla.

    Si matplotlib eligió un backend sin ventanas pero el proceso tiene sesión
    gráfica y MPLBACKEND no lo impone, prueba antes otros backends con ventanas.
    """
    try:
        backend = matplotlib.get_backend()
    except Exception as error:  # noqa: BLE001 — se informa la causa al usuario
        return f"matplotlib no pudo iniciar un backend gráfico ({error})."
    if _es_interactivo(backend):
        return None
    sandbox = consejo_sandbox()
    if sandbox:
        return sandbox
    forzado = os.environ.get("MPLBACKEND")
    if forzado:
        return f"la variable MPLBACKEND={forzado} impone un backend sin ventanas; ejecute «unset MPLBACKEND»."
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return ("este proceso no tiene DISPLAY ni WAYLAND_DISPLAY (sesión SSH, consola TTY o terminal sin acceso "
                "al escritorio); ejecútelo desde una terminal abierta en el escritorio.")
    for alternativo in _BACKENDS_ALTERNATIVOS:
        try:
            plt.switch_backend(alternativo)
            return None
        except Exception:  # noqa: BLE001 — se prueba el siguiente backend
            continue
    return f"matplotlib usa «{backend}» y no hay toolkit con ventanas; instale Tk: sudo apt install python3-tk."

"""Paleta y estilo compartidos por las gráficas estáticas y la animación.

Un solo lugar para los colores: las franjas rojo/verde, los vehículos y las
series tienen el mismo significado en todas las vistas. Las series de
escenarios usan una paleta categórica en orden fijo (validada para daltonismo
en gráficos de líneas); el barrido de g, que es ordinal, usa una rampa de un
solo tono de claro a oscuro.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Paleta:
    """Colores con nombre por función (nunca por posición)."""

    superficie: str = "#fcfcfb"
    fondo_animacion: str = "#f4f3ef"
    texto: str = "#1f1f1d"
    texto_secundario: str = "#52514e"
    texto_tenue: str = "#8a8984"
    rejilla: str = "#e4e3df"
    eje: str = "#b9b8b2"
    encabezado: str = "#e9e8e4"
    resaltado: str = "#dbe9fb"
    serie_activa: str = "#1c5cab"

    rojo: str = "#d9534f"
    verde: str = "#2e9e5b"
    franja_roja: str = "#f6dcda"
    franja_verde: str = "#d9efe0"
    lampara_apagada: str = "#4a4c52"
    carcasa_semaforo: str = "#2f3136"

    vehiculo_servicio: str = "#2a78d6"

    asfalto: str = "#5b6067"
    acera: str = "#d8d4cb"
    manzana: str = "#e3e9d9"
    marca_vial: str = "#f1f1ec"
    linea_central: str = "#e2bb4f"
    neumatico: str = "#232529"
    vidrio: str = "#2d3947"
    faro: str = "#fff3c8"
    luz_freno: str = "#ff4b3e"
    luz_trasera: str = "#7d2f2a"
    autos: tuple[str, ...] = (
        "#9fb0c4", "#c9ced6", "#6e7c8c", "#cfc3a5", "#86a1bd", "#b0b5bb", "#e4e6e9", "#8d99a6",
    )
    """Carrocerías de los autos en espera (tonos sobrios); el auto en servicio usa ``vehiculo_servicio``."""

    serie_principal: str = "#2a78d6"
    categoricos: tuple[str, ...] = (
        "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948",
    )
    rampa_ordinal: tuple[str, ...] = (
        "#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b",
    )


PALETA = Paleta()


def color_categorico(indice: int) -> str:
    """Color de la serie ``indice`` en orden fijo (se repite solo más allá de 8 series)."""
    return PALETA.categoricos[indice % len(PALETA.categoricos)]


def colores_ordinales(cantidad: int) -> list[str]:
    """``cantidad`` pasos equiespaciados de la rampa ordinal (claro → oscuro)."""
    if cantidad <= 1:
        return [PALETA.serie_principal] * cantidad
    ultimo = len(PALETA.rampa_ordinal) - 1
    return [PALETA.rampa_ordinal[round(i * ultimo / (cantidad - 1))] for i in range(cantidad)]


ESTILO_GRAFICAS: dict[str, object] = {
    "figure.facecolor": PALETA.superficie,
    "axes.facecolor": PALETA.superficie,
    "axes.edgecolor": PALETA.eje,
    "axes.labelcolor": PALETA.texto_secundario,
    "axes.titlecolor": PALETA.texto,
    "axes.titlesize": 14,
    "axes.titleweight": "bold",
    "axes.labelsize": 12,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "axes.axisbelow": True,
    "grid.color": PALETA.rejilla,
    "grid.linestyle": "-",
    "grid.linewidth": 0.8,
    "xtick.color": PALETA.texto_secundario,
    "ytick.color": PALETA.texto_secundario,
    "legend.frameon": False,
    "legend.fontsize": 11,
    "lines.linewidth": 1.6,
    "font.size": 12,
    "xtick.labelsize": 11,
    "ytick.labelsize": 11,
    "figure.titlesize": 15,
    "figure.titleweight": "bold",
    "savefig.dpi": 150,
    "savefig.bbox": "tight",
    "savefig.facecolor": PALETA.superficie,
}
"""Parámetros rc de matplotlib: rejilla fina y sólida, ejes discretos, sin marcos."""

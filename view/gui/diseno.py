"""Apariencia de la interfaz: medidas en píxeles de diseño, tipografía y estilos ttk.

Las medidas son píxeles de una pantalla de 1920×1080 (la del portátil). El
factor ancho de pantalla / 1920 compensa la pantalla virtual mayor que
XWayland presenta a Tk cuando GNOME usa escala fraccionaria.
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass, fields, replace
from tkinter import font, ttk
from typing import ClassVar

from view.style import PALETA

FUENTES_TK = ("TkDefaultFont", "TkTextFont", "TkHeadingFont", "TkMenuFont", "TkCaptionFont", "TkSmallCaptionFont",
              "TkIconFont", "TkTooltipFont", "TkFixedFont")
"""Fuentes con nombre de Tk que usan los widgets estándar."""


@dataclass(frozen=True)
class DisenoVentana:
    """Medidas y tamaños de letra en píxeles de una pantalla de 1920×1080.

    ``escalado`` las multiplica por el ancho real de la pantalla dividido entre
    1920. Así una unidad de diseño es un píxel del panel de 1920×1080 también
    cuando GNOME usa escala fraccionaria y XWayland presenta a Tk una pantalla
    virtual mayor (3072×1728 al 125 %). Los campos de ``NO_ESCALABLES``
    (cantidades, tiempos y tamaños en puntos de matplotlib) no cambian.
    """

    NO_ESCALABLES: ClassVar[frozenset[str]] = frozenset({
        "ancho_referencia", "fuente_aviso", "filas_escenarios", "filas_resumen", "filas_tabla", "sondeo_ms",
        "velocidad_maxima",
    })

    ancho_referencia: int = 1920
    ancho_minimo: int = 1000
    alto_minimo: int = 600
    margen_pantalla: int = 30
    ancho_panel: int = 370
    margen: int = 12
    separacion: int = 8
    fuente: int = 15
    """Tamaños de letra en píxeles (alto de la letra); se convierten a puntos con el DPI de Xft."""
    fuente_tabla: int = 15
    fuente_titulo: int = 23
    fuente_subtitulo: int = 13
    fuente_subpestana: int = 13
    fuente_boton_principal: int = 16
    fuente_aviso: float = 12.0
    """Puntos de matplotlib: ya los escala ``dpi_graficas``."""
    dpi_graficas: float = 92.0
    """Resolución de las figuras incrustadas: más alta = textos y trazos más grandes en pantalla."""
    alto_fila: int = 26
    relleno_pestana: tuple[int, int] = (14, 6)
    relleno_subpestana: tuple[int, int] = (10, 4)
    relleno_boton: tuple[int, int] = (10, 5)
    relleno_principal: tuple[int, int] = (12, 10)
    columna_escenario: int = 124
    columna_lambda: int = 52
    columna_tiempo: int = 42
    columna_rho: int = 52
    columna_nombre: int = 150
    columna_corta: int = 66
    columna_valor: int = 120
    columna_texto: int = 600
    filas_escenarios: int = 8
    filas_resumen: int = 6
    filas_tabla: int = 12
    sondeo_ms: int = 60
    velocidad_maxima: int = 60

    def factor_para(self, ancho_pantalla: int) -> float:
        """Píxeles de pantalla por unidad de diseño (1.0 en una sesión de 1920 px de ancho)."""
        return ancho_pantalla / self.ancho_referencia

    def escalado(self, factor: float) -> DisenoVentana:
        """Copia con medidas y tipografía multiplicadas por ``factor``."""
        cambios: dict[str, object] = {}
        for campo in fields(self):
            valor = getattr(self, campo.name)
            if campo.name in self.NO_ESCALABLES:
                continue
            if isinstance(valor, tuple):
                cambios[campo.name] = tuple(max(1, round(v * factor)) for v in valor)
            elif isinstance(valor, int):
                cambios[campo.name] = max(1, round(valor * factor))
            else:
                cambios[campo.name] = valor * factor
        return replace(self, **cambios)


DISENO = DisenoVentana()


class Estilo:
    """Nombres de los estilos ttk que define ``Tema``."""

    ENCABEZADO = "Encabezado.TFrame"
    TITULO = "Titulo.TLabel"
    SUBTITULO = "Subtitulo.TLabel"
    SECCION = "Seccion.TLabel"
    NOTA = "Nota.TLabel"
    BOTON = "TButton"
    PRINCIPAL = "Principal.TButton"
    SUBCUADERNO = "Sub.TNotebook"


def dpi_de_fuentes(raiz: tk.Tk) -> float:
    """DPI con que Xft convierte los puntos de una fuente en píxeles.

    Es el recurso «Xft.dpi» de la sesión (GNOME lo fija según la escala, p. ej.
    192) o, si no existe, la densidad de la pantalla. Tk calcula sus medidas a
    96 ppp aunque Xft dibuje las letras con este valor, así que los tamaños de
    letra se convierten con él para que midan los píxeles pedidos.
    """
    try:
        lector = tk.Tk(className="Xft")  # el recurso «Xft.dpi» solo coincide con la clase «Xft»
        lector.withdraw()
        valor = lector.option_get("dpi", "Dpi")
        lector.destroy()
        return float(valor)
    except (tk.TclError, ValueError):
        return raiz.winfo_fpixels("1i")


class Tema:
    """Tipografía y estilos ttk de la ventana a partir de un ``DisenoVentana``.

    Los tamaños de letra se convierten de píxeles a puntos con el DPI de Xft;
    nunca se cambia ``tk scaling``, que también agrandaría las figuras de
    matplotlib. Las fuentes se guardan como atributos porque Tk borra una
    fuente en cuanto Python libera su objeto.
    """

    def __init__(self, raiz: tk.Tk, diseno: DisenoVentana) -> None:
        self._raiz = raiz
        self._puntos_por_pixel = 72 / dpi_de_fuentes(raiz)
        for nombre in FUENTES_TK:
            font.nametofont(nombre).configure(size=self._puntos(diseno.fuente))
        self.negrita = self._fuente(diseno.fuente, "bold")
        self.tabla = self._fuente(diseno.fuente_tabla, "normal")
        self.tabla_negrita = self._fuente(diseno.fuente_tabla, "bold")
        self.titulo = self._fuente(diseno.fuente_titulo, "bold")
        self.subtitulo = self._fuente(diseno.fuente_subtitulo, "normal")
        self.subpestana = self._fuente(diseno.fuente_subpestana, "normal")
        self.principal = self._fuente(diseno.fuente_boton_principal, "bold")
        raiz.option_add("*TCombobox*Listbox.font", font.nametofont("TkTextFont"))
        self._definir_estilos(diseno)

    def _puntos(self, pixeles: int) -> int:
        """Tamaño en puntos que Xft dibuja con ``pixeles`` de alto."""
        return max(1, round(pixeles * self._puntos_por_pixel))

    def _fuente(self, pixeles: int, peso: str) -> font.Font:
        base = font.nametofont("TkDefaultFont").actual()
        return font.Font(self._raiz, family=base["family"], size=self._puntos(pixeles), weight=peso)

    def _definir_estilos(self, d: DisenoVentana) -> None:
        fondo, superficie = PALETA.fondo_animacion, PALETA.superficie
        estilo = ttk.Style(self._raiz)
        estilo.theme_use("clam")
        estilo.configure(".", background=fondo, foreground=PALETA.texto)
        estilo.configure(Estilo.ENCABEZADO, background=superficie)
        estilo.configure(Estilo.TITULO, background=superficie, font=self.titulo)
        estilo.configure(Estilo.SUBTITULO, background=superficie, foreground=PALETA.texto_secundario,
                         font=self.subtitulo)
        estilo.configure(Estilo.SECCION, font=self.negrita)
        estilo.configure(Estilo.NOTA, foreground=PALETA.texto_secundario, font=self.tabla)
        estilo.configure("Treeview", background=superficie, fieldbackground=superficie, font=self.tabla,
                         rowheight=d.alto_fila)
        estilo.configure("Treeview.Heading", background=PALETA.encabezado, font=self.tabla_negrita,
                         padding=d.relleno_boton)
        estilo.configure("TNotebook.Tab", padding=d.relleno_pestana, font=self.negrita)
        estilo.configure(f"{Estilo.SUBCUADERNO}.Tab", padding=d.relleno_subpestana, font=self.subpestana)
        estilo.configure(Estilo.BOTON, padding=d.relleno_boton)
        estilo.configure(Estilo.PRINCIPAL, background=PALETA.serie_principal, foreground=superficie,
                         font=self.principal, padding=d.relleno_principal)
        estilo.map(Estilo.PRINCIPAL, background=[("disabled", PALETA.eje), ("active", PALETA.serie_activa)])

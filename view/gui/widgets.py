"""Componentes reutilizables de la interfaz (Tkinter + matplotlib)."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Iterable, Sequence

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from config.settings import ErrorConfiguracion
from view.gui.diseno import Estilo
from view.style import PALETA

Columna = tuple[str, int, str]
"""(título, ancho en píxeles, anclaje 'w' | 'e' | 'center')."""


def texto_tk(texto: str) -> str:
    """Tk no dibuja caracteres combinantes: «Q̄» se muestra como «Q media»."""
    return texto.replace("Q̄", "Q media")


def boton(padre: tk.Misc, texto: str, accion: Callable[[], None], principal: bool = False) -> ttk.Button:
    """Botón normal o principal (azul, para la acción más importante de su zona)."""
    return ttk.Button(padre, text=texto, command=accion, style=Estilo.PRINCIPAL if principal else Estilo.BOTON)


def nota_ajustable(padre: tk.Misc, texto: str, margen: int) -> ttk.Label:
    """Nota en gris que ajusta su ancho de línea al de su contenedor."""
    nota = ttk.Label(padre, text=texto, style=Estilo.NOTA, justify=tk.LEFT)
    padre.bind("<Configure>", lambda evento: nota.configure(wraplength=evento.width - 2 * margen), "+")
    return nota


def informar(widget: tk.Misc, titulo: str, texto: str) -> None:
    """Mensaje informativo centrado sobre la ventana del widget."""
    messagebox.showinfo(titulo, texto, parent=widget.winfo_toplevel())


def mostrar_error(widget: tk.Misc, error: BaseException) -> None:
    """Diálogo de error: los de validación con su mensaje, el resto también con su tipo."""
    texto = str(error) if isinstance(error, (ErrorConfiguracion, ValueError)) else f"{type(error).__name__}: {error}"
    messagebox.showerror("No se pudo completar la acción", texto, parent=widget.winfo_toplevel())


class PanelFigura(ttk.Frame):
    """Figura de matplotlib incrustada a todo el espacio disponible, sin barra de herramientas."""

    def __init__(self, padre: tk.Misc, aviso: str, tamano_aviso: float, dpi: float) -> None:
        super().__init__(padre)
        self.figura = Figure(dpi=dpi)
        self.lienzo = FigureCanvasTkAgg(self.figura, master=self)
        self.lienzo.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self._tamano_aviso = tamano_aviso
        self.aviso(aviso)

    def dibujar(self, funcion: Callable[..., None], *datos: object) -> None:
        """Dibuja con una función ``dibujar_*`` de ``view/plots.py``."""
        funcion(self.figura, *datos)
        self.lienzo.draw_idle()

    def aviso(self, texto: str) -> None:
        """Deja la figura vacía con un texto centrado."""
        self.figura.clear()
        self.figura.set_facecolor(PALETA.superficie)
        self.figura.text(0.5, 0.5, texto, ha="center", va="center", color=PALETA.texto_tenue,
                         fontsize=self._tamano_aviso)
        self.lienzo.draw_idle()


class Tabla(ttk.Frame):
    """Treeview con barras de desplazamiento cuyas columnas pueden cambiar."""

    def __init__(self, padre: tk.Misc, columnas: Sequence[Columna], alto: int, horizontal: bool = True) -> None:
        super().__init__(padre)
        self.arbol = ttk.Treeview(self, show="headings", height=alto)
        vertical = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.arbol.yview)
        self.arbol.configure(yscrollcommand=vertical.set)
        self.arbol.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        if horizontal:
            barra = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=self.arbol.xview)
            self.arbol.configure(xscrollcommand=barra.set)
            barra.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.columnas(columnas)

    def columnas(self, columnas: Sequence[Columna]) -> None:
        """Redefine las columnas (y vacía la tabla)."""
        self.limpiar()
        claves = [f"c{i}" for i in range(len(columnas))]
        self.arbol.configure(columns=claves)
        for clave, (titulo, ancho, anclaje) in zip(claves, columnas):
            self.arbol.heading(clave, text=texto_tk(titulo), anchor=anclaje)
            self.arbol.column(clave, width=ancho, minwidth=ancho // 2, anchor=anclaje, stretch=True)

    def cargar(self, filas: Iterable[Sequence[str]], etiquetas: Iterable[str] | None = None) -> None:
        """Reemplaza el contenido; ``etiquetas`` asigna un estilo (tag) a cada fila."""
        self.limpiar()
        etiquetas = list(etiquetas) if etiquetas is not None else None
        for i, fila in enumerate(filas):
            tags = (etiquetas[i],) if etiquetas and etiquetas[i] else ()
            self.arbol.insert("", tk.END, values=[texto_tk(celda) for celda in fila], tags=tags)

    def limpiar(self) -> None:
        self.arbol.delete(*self.arbol.get_children())


class DialogoFormulario:
    """Diálogo modal con campos de texto.

    ``al_aceptar`` recibe los valores en el orden de los campos y devuelve un
    mensaje de error (el diálogo sigue abierto) o None (el diálogo se cierra).
    """

    def __init__(self, padre: tk.Misc, titulo: str, campos: Sequence[tuple[str, str]],
                 al_aceptar: Callable[[list[str]], str | None], margen: int, nota: str = "") -> None:
        self._al_aceptar = al_aceptar
        self._ventana = ventana = tk.Toplevel(padre)
        ventana.title(titulo)
        ventana.transient(padre)
        ventana.resizable(False, False)
        cuerpo = ttk.Frame(ventana, padding=2 * margen)
        cuerpo.pack(fill=tk.BOTH, expand=True)
        self._variables: list[tk.StringVar] = []
        for fila, (etiqueta, valor) in enumerate(campos):
            variable = tk.StringVar(value=valor)
            ttk.Label(cuerpo, text=etiqueta).grid(row=fila, column=0, sticky="w", padx=(0, margen), pady=margen // 2)
            entrada = ttk.Entry(cuerpo, textvariable=variable, width=16)
            entrada.grid(row=fila, column=1, sticky="ew", pady=margen // 2)
            if fila == 0:
                entrada.focus_set()
                entrada.select_range(0, tk.END)
            self._variables.append(variable)
        if nota:
            ttk.Label(cuerpo, text=nota, style=Estilo.NOTA).grid(row=len(campos), column=0, columnspan=2,
                                                                 sticky="w", pady=(margen, 0))
        botones = ttk.Frame(cuerpo)
        botones.grid(row=len(campos) + 1, column=0, columnspan=2, sticky="e", pady=(2 * margen, 0))
        ttk.Button(botones, text="Cancelar", command=ventana.destroy).pack(side=tk.RIGHT)
        boton(botones, "Aceptar", self._aceptar, principal=True).pack(side=tk.RIGHT, padx=(0, margen))
        ventana.bind("<Return>", lambda _evento: self._aceptar())
        ventana.bind("<Escape>", lambda _evento: ventana.destroy())
        ventana.update_idletasks()  # centrado horizontal y en el tercio superior de la ventana principal
        x = padre.winfo_rootx() + (padre.winfo_width() - ventana.winfo_reqwidth()) // 2
        y = padre.winfo_rooty() + (padre.winfo_height() - ventana.winfo_reqheight()) // 3
        ventana.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        ventana.after_idle(self._capturar_eventos)

    def _capturar_eventos(self) -> None:
        """Hace modal el diálogo en cuanto la ventana es visible."""
        try:
            self._ventana.grab_set()
        except tk.TclError:
            self._ventana.after(50, self._capturar_eventos)

    def _aceptar(self) -> None:
        error = self._al_aceptar([variable.get() for variable in self._variables])
        if error:
            messagebox.showerror("Revise los datos", error, parent=self._ventana)
            return
        self._ventana.destroy()

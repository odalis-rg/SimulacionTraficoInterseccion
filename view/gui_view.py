"""Interfaz gráfica para exponer la simulación (Tkinter + matplotlib).

Pensada para proyectar: textos grandes, un elemento principal por pestaña y
pocos controles a la vista. Los escenarios se eligen y se simulan desde el
panel izquierdo; los resultados aparecen en las pestañas Resultados, Gráficas,
Barrido de g, Animación y Verificación. Los parámetros, los escenarios nuevos,
el guardado y las pestañas técnicas (ciclos y traza) quedan en diálogos y
menús. Las simulaciones corren en segundo plano a través del controlador;
esta vista solo presenta resultados ya calculados y nunca toca el modelo.

Las medidas están pensadas para 1920×1080 y se escalan según la altura de la
pantalla, de modo que la ventana también cabe en un proyector de menor
resolución. Atajos: F5 simula, F11 alterna pantalla completa (Esc la cierra),
Ctrl+S guarda los resultados.
"""

from __future__ import annotations

import os
import tkinter as tk
from dataclasses import dataclass, fields, replace
from tkinter import font, messagebox, ttk
from typing import TYPE_CHECKING, Callable, ClassVar, Sequence

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from config.entorno import consejo_sandbox
from config.settings import ErrorConfiguracion
from controller.analysis import Comparacion, ResultadoBarrido, ResultadoEscenario, ResultadoPrueba
from model.simulator import ResultadoReplica
from model.statistics import INDICADORES_POR_CLAVE, rho_efectivo
from view.animation_view import ControlReproduccion
from view.formato import (
    ENCABEZADOS_BARRIDO,
    ENCABEZADOS_TRAZA,
    NOTA_REDUCCION_TABLA,
    celda_ciclo,
    fila_barrido,
    fila_traza,
    media_ic,
    tabla_comparacion,
    texto_balance,
    texto_censura,
    texto_no_comparables,
    textos_optimo,
)
from view.gui_widgets import Columna, DialogoFormulario, EjecutorSegundoPlano, PanelFigura, Tabla, texto_tk
from view.plots import (
    dibujar_barras_indicador,
    dibujar_cola_en_el_tiempo,
    dibujar_colas_superpuestas,
    dibujar_histograma_esperas,
    dibujar_indicadores_vs_g,
    dibujar_residual_por_ciclo,
)
from view.style import PALETA

if TYPE_CHECKING:
    from controller.experiment_controller import ControladorExperimentos


@dataclass(frozen=True)
class DisenoVentana:
    """Medidas (píxeles) y tipografía (puntos) para una pantalla de 1920×1080.

    ``escalado`` las adapta a otra altura de pantalla; los campos de
    ``NO_ESCALABLES`` (límites, cantidades de filas, tiempos) no cambian.
    """

    NO_ESCALABLES: ClassVar[frozenset[str]] = frozenset({
        "alto_referencia", "escala_minima", "escala_maxima", "ancho_minimo", "alto_minimo",
        "filas_escenarios", "filas_resumen", "filas_tabla", "sondeo_ms", "velocidad_maxima",
    })

    alto_referencia: int = 1080
    escala_minima: float = 0.7
    escala_maxima: float = 1.4
    ancho_minimo: int = 1100
    alto_minimo: int = 600
    margen_pantalla: int = 40
    ancho_panel: int = 470
    margen: int = 14
    separacion: int = 10
    fuente: int = 14
    fuente_tabla: int = 13
    fuente_titulo: int = 24
    fuente_subtitulo: int = 13
    fuente_subpestana: int = 13
    fuente_boton_principal: int = 16
    fuente_aviso: float = 16.0
    dpi_graficas: float = 112.0
    """Resolución de las figuras incrustadas: más alta = textos y trazos más grandes en pantalla."""
    alto_fila: int = 34
    relleno_pestana: tuple[int, int] = (20, 9)
    relleno_subpestana: tuple[int, int] = (14, 6)
    relleno_boton: tuple[int, int] = (12, 7)
    relleno_principal: tuple[int, int] = (14, 14)
    columna_escenario: int = 156
    columna_lambda: int = 66
    columna_tiempo: int = 54
    columna_rho: int = 66
    columna_nombre: int = 190
    columna_corta: int = 84
    columna_valor: int = 150
    columna_texto: int = 760
    filas_escenarios: int = 8
    filas_resumen: int = 6
    filas_tabla: int = 12
    sondeo_ms: int = 60
    velocidad_maxima: int = 60

    def factor_para(self, alto_pantalla: int) -> float:
        """Factor de escala para una pantalla de ``alto_pantalla`` píxeles (acotado)."""
        return min(max(alto_pantalla / self.alto_referencia, self.escala_minima), self.escala_maxima)

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
TITULO = "Simulación de un acceso semaforizado"
SUBTITULO = ("Teoría de colas · llegadas de Poisson · servicio de 1/μ s solo en verde · "
             "resultados del horizonte simulado")
COLUMNAS_RESUMEN = ("q_media", "q_max", "wq_media", "capacidad_efectiva", "residual_medio")
"""Indicadores (media ± IC) de la tabla de resultados; el resto queda en la consola y los CSV."""
AVISO_SIN_RESULTADOS = "Elija escenarios a la izquierda y pulse «Simular» (F5)."
AVISO_SIN_BARRIDO = "Pulse «Ejecutar barrido»."
NOTA_SATURADOS = "En rojo: ρef ≥ 1, la cola puede crecer ciclo a ciclo (ρef figura en la lista de escenarios)."


def abrir_interfaz(controlador: ControladorExperimentos) -> str | None:
    """Abre la ventana y bloquea hasta cerrarla; devuelve un mensaje si no se pudo abrir."""
    try:
        raiz = tk.Tk()
    except tk.TclError as error:
        sandbox = consejo_sandbox()
        if sandbox:
            return f"No se pudo abrir la interfaz gráfica. {sandbox}"
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            return ("No se pudo abrir la interfaz gráfica: este proceso no tiene DISPLAY ni WAYLAND_DISPLAY; "
                    "ejecútelo desde una terminal abierta en el escritorio (no por SSH ni consola TTY).")
        return f"No se pudo abrir la interfaz gráfica: {error}."
    VentanaPrincipal(raiz, controlador)
    raiz.mainloop()
    return None


def _real(texto: str, nombre: str) -> float:
    """Número decimal (acepta coma); lanza ``ErrorConfiguracion`` si no lo es."""
    try:
        return float(texto.replace(",", "."))
    except ValueError:
        raise ErrorConfiguracion(f"{nombre} debe ser un número (recibido: «{texto}»).") from None


def _entero(texto: str, nombre: str) -> int:
    try:
        return int(texto)
    except ValueError:
        raise ErrorConfiguracion(f"{nombre} debe ser un entero (recibido: «{texto}»).") from None


class VentanaPrincipal:
    """Encabezado, panel de escenarios a la izquierda y pestañas de resultados."""

    def __init__(self, raiz: tk.Tk, controlador: ControladorExperimentos) -> None:
        self._raiz = raiz
        self._ctl = controlador
        self._d = DISENO.escalado(DISENO.factor_para(raiz.winfo_screenheight()))
        self._resultados: list[ResultadoEscenario] = []
        self._comparacion: Comparacion | None = None
        self._barrido: ResultadoBarrido | None = None
        self._animacion: ControlReproduccion | None = None
        self._lienzo_animacion: FigureCanvasTkAgg | None = None
        self._botones: list[ttk.Button] = []
        self._ocupada = False
        self._pantalla_completa = False
        self._estado = tk.StringVar(value="Listo. F5: simular · F11: pantalla completa.")
        self._resumen_parametros = tk.StringVar()
        self._ver_tecnicas = tk.BooleanVar(value=False)
        self._ejecutor = EjecutorSegundoPlano(raiz, self._d.sondeo_ms, self._estado.set)
        self._configurar_ventana()
        self._construir()
        self._cargar_escenarios(seleccionar_todos=True)

    # ------------------------------------------------------------------
    # Ventana, estilo y menús
    # ------------------------------------------------------------------
    def _configurar_ventana(self) -> None:
        raiz, d = self._raiz, self._d
        raiz.title(TITULO)
        ancho, alto = raiz.winfo_screenwidth(), raiz.winfo_screenheight()
        raiz.geometry(f"{ancho - 2 * d.margen_pantalla}x{alto - 3 * d.margen_pantalla}"
                      f"+{d.margen_pantalla}+{d.margen_pantalla}")
        raiz.minsize(d.ancho_minimo, d.alto_minimo)
        try:
            raiz.attributes("-zoomed", True)  # maximizada en X11
        except tk.TclError:
            pass
        raiz.configure(background=PALETA.fondo_animacion)
        raiz.protocol("WM_DELETE_WINDOW", self._cerrar)
        for nombre in ("TkDefaultFont", "TkTextFont", "TkHeadingFont", "TkMenuFont"):
            font.nametofont(nombre).configure(size=d.fuente)
        self._fuentes = {  # se conservan: Tk borra una fuente cuando Python libera su objeto
            "negrita": self._fuente(d.fuente, "bold"),
            "tabla": self._fuente(d.fuente_tabla, "normal"),
            "tabla_negrita": self._fuente(d.fuente_tabla, "bold"),
            "titulo": self._fuente(d.fuente_titulo, "bold"),
            "subtitulo": self._fuente(d.fuente_subtitulo, "normal"),
            "subpestana": self._fuente(d.fuente_subpestana, "normal"),
            "principal": self._fuente(d.fuente_boton_principal, "bold"),
        }
        raiz.option_add("*TCombobox*Listbox.font", font.nametofont("TkTextFont"))
        f, fondo = self._fuentes, PALETA.fondo_animacion
        estilo = ttk.Style(raiz)
        estilo.theme_use("clam")
        estilo.configure(".", background=fondo, foreground=PALETA.texto)
        estilo.configure("Encabezado.TFrame", background=PALETA.superficie)
        estilo.configure("Titulo.TLabel", background=PALETA.superficie, font=f["titulo"])
        estilo.configure("Subtitulo.TLabel", background=PALETA.superficie, foreground=PALETA.texto_secundario,
                         font=f["subtitulo"])
        estilo.configure("Seccion.TLabel", font=f["negrita"])
        estilo.configure("Nota.TLabel", foreground=PALETA.texto_secundario, font=f["tabla"])
        estilo.configure("Treeview", background=PALETA.superficie, fieldbackground=PALETA.superficie,
                         font=f["tabla"], rowheight=d.alto_fila)
        estilo.configure("Treeview.Heading", background=PALETA.encabezado, font=f["tabla_negrita"],
                         padding=d.relleno_boton)
        estilo.configure("TNotebook.Tab", padding=d.relleno_pestana, font=f["negrita"])
        estilo.configure("Sub.TNotebook.Tab", padding=d.relleno_subpestana, font=f["subpestana"])
        estilo.configure("TButton", padding=d.relleno_boton)
        estilo.configure("Principal.TButton", background=PALETA.serie_principal, foreground=PALETA.superficie,
                         font=f["principal"], padding=d.relleno_principal)
        estilo.map("Principal.TButton", background=[("disabled", PALETA.eje), ("active", PALETA.serie_activa)])
        self._construir_menu()
        raiz.bind("<F5>", lambda _evento: self._simular())
        raiz.bind("<F11>", lambda _evento: self._alternar_pantalla_completa())
        raiz.bind("<Escape>", lambda _evento: self._salir_pantalla_completa())
        raiz.bind("<Control-s>", lambda _evento: self._guardar())
        raiz.bind("<Control-q>", lambda _evento: self._cerrar())

    def _fuente(self, tamano: int, peso: str) -> font.Font:
        base = font.nametofont("TkDefaultFont").actual()
        return font.Font(self._raiz, family=base["family"], size=tamano, weight=peso)

    def _construir_menu(self) -> None:
        barra = tk.Menu(self._raiz)
        archivo = tk.Menu(barra, tearoff=False)
        archivo.add_command(label="Guardar resultados en output/", accelerator="Ctrl+S", command=self._guardar)
        archivo.add_separator()
        archivo.add_command(label="Salir", accelerator="Ctrl+Q", command=self._cerrar)
        simulacion = tk.Menu(barra, tearoff=False)
        simulacion.add_command(label="Simular escenarios seleccionados", accelerator="F5", command=self._simular)
        simulacion.add_command(label="Nuevo escenario…", command=self._dialogo_escenario)
        simulacion.add_command(label="Parámetros de simulación…", command=self._dialogo_parametros)
        ver = tk.Menu(barra, tearoff=False)
        ver.add_command(label="Pantalla completa", accelerator="F11", command=self._alternar_pantalla_completa)
        ver.add_checkbutton(label="Pestañas técnicas (ciclos y traza)", variable=self._ver_tecnicas,
                            command=self._mostrar_tecnicas)
        for etiqueta, menu in (("Archivo", archivo), ("Simulación", simulacion), ("Ver", ver)):
            barra.add_cascade(label=etiqueta, menu=menu)
        self._raiz.configure(menu=barra)

    def _boton(self, padre: tk.Misc, texto: str, accion: Callable[[], None], principal: bool = False) -> ttk.Button:
        """Botón que se desactiva mientras hay una simulación en curso."""
        boton = ttk.Button(padre, text=texto, command=accion, style="Principal.TButton" if principal else "TButton")
        self._botones.append(boton)
        return boton

    def _construir(self) -> None:
        m = self._d.margen
        encabezado = ttk.Frame(self._raiz, style="Encabezado.TFrame", padding=(2 * m, m))
        encabezado.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(encabezado, text=TITULO, style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(encabezado, text=SUBTITULO, style="Subtitulo.TLabel").pack(anchor="w")
        estado = ttk.Frame(self._raiz, padding=(2 * m, 0, 2 * m, m // 2))
        estado.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Label(estado, textvariable=self._estado, style="Nota.TLabel").pack(side=tk.LEFT)
        self._progreso = ttk.Progressbar(estado, mode="indeterminate", length=self._d.ancho_panel // 2)
        panel = ttk.Frame(self._raiz, width=self._d.ancho_panel, padding=(2 * m, m, m, m))
        panel.pack(side=tk.LEFT, fill=tk.Y)
        panel.pack_propagate(False)
        self._cuaderno = ttk.Notebook(self._raiz)
        self._cuaderno.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 2 * m), pady=m)
        self._construir_panel(panel)
        self._construir_resultados()
        self._construir_graficas()
        self._construir_barrido()
        self._construir_animacion()
        self._construir_verificacion()
        self._construir_ciclos()
        self._construir_traza()
        self._mostrar_tecnicas()

    # ------------------------------------------------------------------
    # Panel de escenarios
    # ------------------------------------------------------------------
    def _construir_panel(self, panel: ttk.Frame) -> None:
        d = self._d
        s = d.separacion
        ttk.Label(panel, text="Escenarios", style="Seccion.TLabel").pack(anchor="w")
        ttk.Label(panel, text="Ctrl o Shift para elegir varios", style="Nota.TLabel").pack(anchor="w")
        self._tabla_escenarios = Tabla(panel, [("Escenario", d.columna_escenario, "w"), ("λ", d.columna_lambda, "e"),
                                               ("g", d.columna_tiempo, "e"), ("r", d.columna_tiempo, "e"),
                                               ("ρef", d.columna_rho, "e")], d.filas_escenarios, horizontal=False)
        self._tabla_escenarios.pack(fill=tk.X, pady=(s, 0))
        fila = ttk.Frame(panel)
        fila.pack(fill=tk.X, pady=(s, 0))
        ttk.Button(fila, text="Todos", command=lambda: self._seleccionar(True)).pack(side=tk.LEFT)
        ttk.Button(fila, text="Ninguno", command=lambda: self._seleccionar(False)).pack(side=tk.LEFT, padx=s)
        self._boton(fila, "＋ Nuevo…", self._dialogo_escenario).pack(side=tk.LEFT)
        ttk.Separator(panel).pack(fill=tk.X, pady=2 * s)
        ttk.Label(panel, text="Parámetros", style="Seccion.TLabel").pack(anchor="w")
        fila = ttk.Frame(panel)
        fila.pack(fill=tk.X, pady=(s // 2, 0))
        ttk.Label(fila, textvariable=self._resumen_parametros, style="Nota.TLabel", justify=tk.LEFT).pack(side=tk.LEFT)
        self._boton(fila, "Cambiar…", self._dialogo_parametros).pack(side=tk.RIGHT)
        self._boton(panel, "▶  Simular", self._simular, principal=True).pack(fill=tk.X, pady=(3 * s, 0))

    def _cargar_escenarios(self, seleccionar_todos: bool = False, seleccionar: str | None = None) -> None:
        """Rellena la lista de escenarios (con su ρef), los selectores y el resumen de parámetros."""
        config = self._ctl.config
        filas = []
        for e in config.escenarios:
            p = e.parametros(config.simulacion)
            filas.append((e.nombre, f"{p.lam:g}", f"{p.g:g}", f"{p.r:g}", f"{rho_efectivo(p):.2f}"))
        arbol = self._tabla_escenarios.arbol
        anteriores = set(self._seleccionados())
        self._tabla_escenarios.cargar(filas)
        for item in arbol.get_children():
            nombre = arbol.item(item, "values")[0]
            if seleccionar_todos or nombre in anteriores or nombre == seleccionar:
                arbol.selection_add(item)
        nombres = [e.nombre for e in config.escenarios]
        for combo in (self._combo_traza, self._combo_animacion):
            combo.configure(values=nombres)
        sim = config.simulacion
        self._resumen_parametros.set(f"μ = {sim.mu:g} veh/s · H = {sim.H:g} s\n{sim.n_replicas} réplicas por escenario")
        self._replica_traza.configure(to=sim.n_replicas)

    def _seleccionados(self) -> list[str]:
        arbol = self._tabla_escenarios.arbol
        return [arbol.item(item, "values")[0] for item in arbol.selection()]

    def _seleccionar(self, todos: bool) -> None:
        arbol = self._tabla_escenarios.arbol
        if todos:
            arbol.selection_set(arbol.get_children())
        else:
            arbol.selection_remove(arbol.get_children())

    # ------------------------------------------------------------------
    # Pestañas
    # ------------------------------------------------------------------
    def _pestana(self, titulo: str) -> ttk.Frame:
        marco = ttk.Frame(self._cuaderno, padding=self._d.margen)
        self._cuaderno.add(marco, text=titulo)
        return marco

    def _subpestanas(self, padre: tk.Misc) -> ttk.Notebook:
        cuaderno = ttk.Notebook(padre, style="Sub.TNotebook")
        cuaderno.pack(fill=tk.BOTH, expand=True, pady=(self._d.separacion, 0))
        return cuaderno

    def _panel_figura(self, cuaderno: ttk.Notebook, titulo: str, aviso: str) -> PanelFigura:
        panel = PanelFigura(cuaderno, aviso, self._d.fuente_aviso, self._d.dpi_graficas)
        cuaderno.add(panel, text=titulo)
        return panel

    def _nota(self, padre: tk.Misc, texto: str = "") -> ttk.Label:
        """Nota en gris que ajusta su ancho al de su contenedor."""
        nota = ttk.Label(padre, text=texto, style="Nota.TLabel", justify=tk.LEFT)
        padre.bind("<Configure>", lambda evento: nota.configure(wraplength=evento.width - 2 * self._d.margen), "+")
        return nota

    def _construir_resultados(self) -> None:
        marco = self._pestana("Resultados")
        d = self._d
        columnas: list[Columna] = [("Escenario", d.columna_nombre, "w")]
        columnas += [(f"{INDICADORES_POR_CLAVE[c].simbolo} ({INDICADORES_POR_CLAVE[c].unidad})", d.columna_valor, "e")
                     for c in COLUMNAS_RESUMEN]
        self._titulo_resumen = ttk.Label(marco, text="Indicadores por escenario (media ± IC)", style="Seccion.TLabel")
        self._titulo_resumen.pack(anchor="w")
        self._tabla_resumen = Tabla(marco, columnas, d.filas_resumen, horizontal=False)
        self._tabla_resumen.arbol.tag_configure("saturado", foreground=PALETA.rojo)
        self._tabla_resumen.pack(fill=tk.X, pady=(d.separacion, 0))
        self._nota(marco, NOTA_SATURADOS).pack(anchor="w", pady=(d.separacion // 2, 0))
        self._titulo_comparacion = ttk.Label(marco, text="Comparación con la base (misma λ)", style="Seccion.TLabel")
        self._titulo_comparacion.pack(anchor="w", pady=(3 * d.separacion, 0))
        self._tabla_comparacion = Tabla(marco, [("Indicador", d.columna_nombre, "w")], d.filas_resumen,
                                        horizontal=False)
        self._tabla_comparacion.pack(fill=tk.X, pady=(d.separacion, 0))
        self._nota_comparacion = self._nota(marco)
        self._nota_comparacion.pack(anchor="w", pady=(d.separacion // 2, 0))

    def _construir_graficas(self) -> None:
        self._pestana_graficas = marco = self._pestana("Gráficas")
        sub = self._subpestanas(marco)
        self._paneles = {clave: self._panel_figura(sub, titulo, AVISO_SIN_RESULTADOS) for clave, titulo in (
            ("q_t", "Q(t)"), ("q_media", "Cola media"), ("wq_media", "Espera media"),
            ("residual", "Cola residual"), ("esperas", "Esperas"))}

    def _construir_barrido(self) -> None:
        marco = self._pestana("Barrido de g")
        b, d = self._ctl.config.barrido, self._d
        self._barrido_vars = {"lam": tk.StringVar(value=f"{b.lam:g}"), "T": tk.StringVar(value=f"{b.T:g}"),
                              "g": tk.StringVar(value=", ".join(f"{g:g}" for g in b.valores_g))}
        fila = ttk.Frame(marco)
        fila.pack(fill=tk.X)
        for etiqueta, clave, ancho in (("λ (veh/s)", "lam", 6), ("T (s)", "T", 6), ("Valores de g (s)", "g", 28)):
            ttk.Label(fila, text=etiqueta).pack(side=tk.LEFT)
            ttk.Entry(fila, textvariable=self._barrido_vars[clave], width=ancho).pack(
                side=tk.LEFT, padx=(d.separacion // 2, d.margen))
        self._boton(fila, "▶  Ejecutar barrido", self._ejecutar_barrido, principal=True).pack(side=tk.LEFT)
        self._cuaderno_barrido = sub = self._subpestanas(marco)
        self._pestana_tabla_i = tabla_i = ttk.Frame(sub, padding=d.margen)
        sub.add(tabla_i, text="Tabla I")
        anchos = (d.columna_corta,) * 4 + (d.columna_valor,) * 4
        self._tabla_barrido = Tabla(tabla_i, [(t, a, "e") for t, a in zip(ENCABEZADOS_BARRIDO[:-1], anchos)],
                                    len(b.valores_g), horizontal=False)
        self._tabla_barrido.arbol.tag_configure("optimo", background=PALETA.resaltado,
                                                font=self._fuentes["tabla_negrita"])
        self._tabla_barrido.pack(fill=tk.X)
        self._nota_barrido = self._nota(tabla_i, AVISO_SIN_BARRIDO)
        self._nota_barrido.pack(anchor="w", fill=tk.X, pady=(d.separacion, 0))
        self._panel_fig2 = self._panel_figura(sub, "Fig. 2 · Colas", AVISO_SIN_BARRIDO)
        self._panel_vs_g = self._panel_figura(sub, "Q media y Wq vs g/T", AVISO_SIN_BARRIDO)

    def _construir_animacion(self) -> None:
        marco = self._pestana("Animación")
        anim, d = self._ctl.config.animacion, self._d
        fila = ttk.Frame(marco)
        fila.pack(fill=tk.X)
        self._escenario_animacion = tk.StringVar(value=anim.escenario)
        self._velocidad = tk.StringVar(value=f"{anim.velocidad:g}")
        ttk.Label(fila, text="Escenario").pack(side=tk.LEFT)
        self._combo_animacion = ttk.Combobox(fila, textvariable=self._escenario_animacion, state="readonly", width=16)
        self._combo_animacion.pack(side=tk.LEFT, padx=(d.separacion // 2, d.margen))
        ttk.Label(fila, text="Velocidad ×").pack(side=tk.LEFT)
        ttk.Spinbox(fila, textvariable=self._velocidad, from_=1, to=d.velocidad_maxima, width=4).pack(
            side=tk.LEFT, padx=(d.separacion // 2, d.margen))
        self._boton(fila, "▶  Reproducir", self._reproducir, principal=True).pack(side=tk.LEFT)
        self._boton_pausa = ttk.Button(fila, text="❚❚  Pausa", command=self._alternar_pausa, state=tk.DISABLED)
        self._boton_pausa.pack(side=tk.LEFT, padx=d.separacion)
        self._boton_reinicio = ttk.Button(fila, text="⟲  Reiniciar", command=self._reiniciar, state=tk.DISABLED)
        self._boton_reinicio.pack(side=tk.LEFT)
        self._area_animacion = ttk.Frame(marco)
        self._area_animacion.pack(fill=tk.BOTH, expand=True, pady=(d.separacion, 0))
        self._aviso_animacion = ttk.Label(self._area_animacion, style="Nota.TLabel",
                                          text=f"Elija un escenario y pulse «Reproducir». Se muestran los primeros "
                                               f"{anim.ventana_s:g} s de la simulación.")
        self._aviso_animacion.pack(expand=True)

    def _construir_verificacion(self) -> None:
        marco = self._pestana("Verificación")
        d = self._d
        fila = ttk.Frame(marco)
        fila.pack(fill=tk.X)
        self._boton(fila, "▶  Ejecutar pruebas", self._ejecutar_pruebas, principal=True).pack(side=tk.LEFT)
        self._resumen_pruebas = ttk.Label(fila, text="", style="Seccion.TLabel")
        self._resumen_pruebas.pack(side=tk.LEFT, padx=2 * d.margen)
        self._tabla_pruebas = Tabla(marco, [("#", d.columna_corta // 2, "e"), ("Prueba", d.columna_texto, "w"),
                                            ("Resultado", d.columna_corta + d.margen * 3, "center"),
                                            ("Detalle", d.columna_nombre, "w")], d.filas_tabla, horizontal=False)
        self._tabla_pruebas.arbol.tag_configure("ok", foreground=PALETA.verde)
        self._tabla_pruebas.arbol.tag_configure("fallo", foreground=PALETA.rojo)
        self._tabla_pruebas.pack(fill=tk.BOTH, expand=True, pady=(d.separacion, 0))

    def _construir_ciclos(self) -> None:
        self._pestana_ciclos = marco = self._pestana("Ciclos")
        self._titulo_ciclos = ttk.Label(marco, text="Vehículos atendidos / cola residual al final de cada verde",
                                        style="Seccion.TLabel")
        self._titulo_ciclos.pack(anchor="w")
        self._tabla_ciclos = Tabla(marco, [("Ciclo", self._d.columna_corta, "e")], self._d.filas_tabla)
        self._tabla_ciclos.pack(fill=tk.BOTH, expand=True, pady=(self._d.separacion, 0))

    def _construir_traza(self) -> None:
        self._pestana_traza = marco = self._pestana("Traza")
        d = self._d
        fila = ttk.Frame(marco)
        fila.pack(fill=tk.X)
        self._escenario_traza = tk.StringVar()
        self._replica = tk.StringVar(value=str(self._ctl.config.salida.replica_detalle))
        ttk.Label(fila, text="Escenario").pack(side=tk.LEFT)
        self._combo_traza = ttk.Combobox(fila, textvariable=self._escenario_traza, state="readonly", width=16)
        self._combo_traza.pack(side=tk.LEFT, padx=(d.separacion // 2, d.margen))
        ttk.Label(fila, text="Réplica").pack(side=tk.LEFT)
        self._replica_traza = ttk.Spinbox(fila, textvariable=self._replica, from_=1,
                                          to=self._ctl.config.simulacion.n_replicas, width=5)
        self._replica_traza.pack(side=tk.LEFT, padx=(d.separacion // 2, d.margen))
        self._boton(fila, "Ver traza", self._ver_traza, principal=True).pack(side=tk.LEFT)
        self._info_traza = self._nota(marco, "Eventos simultáneos: SALIDA → CAMBIO_FASE → LLEGADA.")
        self._info_traza.pack(anchor="w", pady=(d.separacion, 0))
        anclajes = ("e", "w", "w", "w", "e", "w", "e")
        self._tabla_traza = Tabla(marco, [(t, d.columna_valor - d.margen, a) for t, a in zip(ENCABEZADOS_TRAZA, anclajes)],
                                  d.filas_tabla, horizontal=False)
        self._tabla_traza.pack(fill=tk.BOTH, expand=True, pady=(d.separacion, 0))

    def _mostrar_tecnicas(self) -> None:
        """Muestra u oculta las pestañas técnicas según el menú Ver."""
        for pestana in (self._pestana_ciclos, self._pestana_traza):
            if self._ver_tecnicas.get():
                self._cuaderno.add(pestana)
            else:
                self._cuaderno.hide(pestana)

    def _alternar_pantalla_completa(self) -> None:
        self._pantalla_completa = not self._pantalla_completa
        self._raiz.attributes("-fullscreen", self._pantalla_completa)

    def _salir_pantalla_completa(self) -> None:
        if self._pantalla_completa:
            self._alternar_pantalla_completa()

    # ------------------------------------------------------------------
    # Tareas en segundo plano
    # ------------------------------------------------------------------
    def _libre(self) -> bool:
        """False (y un aviso) si hay una tarea en curso."""
        if self._ocupada:
            self._estado.set("Espere a que termine la tarea en curso…")
        return not self._ocupada

    def _en_segundo_plano(self, descripcion: str, tarea: Callable[[], object],
                          al_terminar: Callable[[object], None]) -> None:
        self._ocupado(True, descripcion)

        def terminar(resultado: object) -> None:
            self._ocupado(False, "Listo.")
            al_terminar(resultado)

        def fallar(error: BaseException) -> None:
            self._ocupado(False, "Se produjo un error.")
            self._mostrar_error(error)

        self._ejecutor.ejecutar(tarea, terminar, fallar)

    def _ocupado(self, ocupada: bool, texto: str) -> None:
        self._ocupada = ocupada
        for boton in self._botones:
            boton.state(["disabled"] if ocupada else ["!disabled"])
        if ocupada:
            self._progreso.pack(side=tk.RIGHT)
            self._progreso.start()
        else:
            self._progreso.stop()
            self._progreso.pack_forget()
        self._estado.set(texto)

    def _avisar_progreso(self, nombre: str, replicas: int, segundos: float) -> None:
        """Lo llama el hilo de trabajo al terminar cada escenario."""
        self._ejecutor.avisar(f"✓ {nombre}: {replicas} réplicas en {segundos:.2f} s")

    def _mostrar_error(self, error: BaseException) -> None:
        texto = str(error) if isinstance(error, (ErrorConfiguracion, ValueError)) else f"{type(error).__name__}: {error}"
        messagebox.showerror("No se pudo completar la acción", texto, parent=self._raiz)

    # ------------------------------------------------------------------
    # Diálogos
    # ------------------------------------------------------------------
    def _dialogo_escenario(self) -> None:
        if not self._libre():
            return

        def aceptar(valores: list[str]) -> str | None:
            nombre, lam, g, r = valores
            try:
                escenario = self._ctl.agregar_escenario(nombre, _real(lam, "λ"), _real(g, "g"), _real(r, "r"))
            except ErrorConfiguracion as error:
                return str(error)
            self._cargar_escenarios(seleccionar=escenario.nombre)
            self._estado.set(f"Escenario «{escenario.nombre}» agregado y seleccionado.")
            return None

        DialogoFormulario(self._raiz, "Nuevo escenario",
                          (("Nombre", "Personalizado"), ("λ (veh/s)", "0.2"), ("g (s)", "30"), ("r (s)", "30")),
                          aceptar, self._d.margen)

    def _dialogo_parametros(self) -> None:
        if not self._libre():
            return
        sim = self._ctl.config.simulacion

        def aceptar(valores: list[str]) -> str | None:
            mu, H, n = valores
            try:
                self._ctl.configurar_simulacion(_real(mu, "μ"), _real(H, "H"), _entero(n, "n"))
            except ErrorConfiguracion as error:
                return str(error)
            self._cargar_escenarios()
            self._estado.set("Parámetros actualizados; vuelva a simular para aplicarlos.")
            return None

        DialogoFormulario(self._raiz, "Parámetros de simulación",
                          (("μ (veh/s)", f"{sim.mu:g}"), ("H (s)", f"{sim.H:g}"), ("Réplicas n", str(sim.n_replicas))),
                          aceptar, self._d.margen, nota=f"La réplica i usa la semilla {sim.semilla_base} + i.")

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def _simular(self) -> None:
        if not self._libre():
            return
        nombres = self._seleccionados()
        if not nombres:
            messagebox.showinfo("Simular", "Seleccione al menos un escenario.", parent=self._raiz)
            return
        escenarios = [self._ctl.config.escenario(nombre) for nombre in nombres]

        def tarea() -> tuple[list[ResultadoEscenario], Comparacion | None]:
            resultados = self._ctl.simular_escenarios(escenarios, self._avisar_progreso)
            base = self._ctl.resultado_base(resultados, self._avisar_progreso)
            return resultados, self._ctl.comparar(resultados, base)

        n = self._ctl.config.simulacion.n_replicas
        self._en_segundo_plano(f"Simulando {len(escenarios)} escenario(s) × {n} réplicas…", tarea,
                               self._mostrar_resultados)

    def _mostrar_resultados(self, datos: object) -> None:
        resultados, comparacion = datos
        self._resultados, self._comparacion = resultados, comparacion
        conf, n = self._ctl.config.simulacion.confianza, len(resultados[0].metricas)
        self._titulo_resumen.configure(text=f"Indicadores por escenario (media ± IC {conf:.0%}, {n} réplicas)")
        self._tabla_resumen.cargar([(r.nombre, *(media_ic(r.resumen[c]) for c in COLUMNAS_RESUMEN)) for r in resultados],
                                   ["saturado" if r.rho_ef >= 1 else "" for r in resultados])
        self._mostrar_comparacion(comparacion)
        self._mostrar_ciclos(resultados)
        p = self._paneles
        p["q_t"].dibujar(dibujar_cola_en_el_tiempo, resultados)
        p["q_media"].dibujar(dibujar_barras_indicador, resultados, "q_media", conf)
        p["wq_media"].dibujar(dibujar_barras_indicador, resultados, "wq_media", conf)
        p["residual"].dibujar(dibujar_residual_por_ciclo, resultados)
        p["esperas"].dibujar(dibujar_histograma_esperas, resultados)
        self._cuaderno.select(self._pestana_graficas)
        self._estado.set(f"{len(resultados)} escenario(s) simulados con {n} réplicas.")

    def _mostrar_comparacion(self, comparacion: Comparacion | None) -> None:
        if comparacion is None or not comparacion.filas:
            self._tabla_comparacion.limpiar()
            self._nota_comparacion.configure(text="Sin comparación: ningún escenario simulado comparte λ con la base.")
            return
        d = self._d
        encabezados, filas = tabla_comparacion(comparacion)
        self._titulo_comparacion.configure(text=f"Comparación con «{comparacion.base}» (misma λ)")
        self._tabla_comparacion.columnas([(encabezados[0], d.columna_nombre, "w"), (encabezados[1], d.columna_corta, "e"),
                                          *((e, d.columna_valor + d.columna_corta, "e") for e in encabezados[2:])])
        self._tabla_comparacion.arbol.configure(height=len(filas))
        self._tabla_comparacion.cargar(filas)
        notas = [NOTA_REDUCCION_TABLA]
        if comparacion.no_comparables:
            notas.append(texto_no_comparables(comparacion.no_comparables))
        self._nota_comparacion.configure(text="\n".join(notas))

    def _mostrar_ciclos(self, resultados: Sequence[ResultadoEscenario]) -> None:
        d = self._d
        self._titulo_ciclos.configure(text=f"Vehículos atendidos / cola residual al final de cada verde "
                                           f"(réplica {resultados[0].replica_detalle})")
        self._tabla_ciclos.columnas([("Ciclo", d.columna_corta, "e"),
                                     *((r.nombre, d.columna_valor, "e") for r in resultados)])
        total = max(len(r.detalle.ciclos) for r in resultados)
        self._tabla_ciclos.cargar(
            (str(k + 1), *(celda_ciclo(r.detalle.ciclos[k] if k < len(r.detalle.ciclos) else None) for r in resultados))
            for k in range(total)
        )

    def _ejecutar_barrido(self) -> None:
        if not self._libre():
            return
        v = self._barrido_vars
        try:
            valores = [_real(g.strip(), "Cada valor de g") for g in v["g"].get().replace(";", ",").split(",")
                       if g.strip()]
            self._ctl.configurar_barrido(_real(v["lam"].get(), "λ"), _real(v["T"].get(), "T"), valores)
        except ErrorConfiguracion as error:
            self._mostrar_error(error)
            return
        self._en_segundo_plano(f"Barrido de {len(valores)} valores de g…",
                               lambda: self._ctl.simular_barrido(self._avisar_progreso), self._mostrar_barrido)

    def _mostrar_barrido(self, barrido: object) -> None:
        assert isinstance(barrido, ResultadoBarrido)
        self._barrido = barrido
        optimo = barrido.indice_optimo
        self._tabla_barrido.arbol.configure(height=len(barrido.resultados))
        self._tabla_barrido.cargar([fila_barrido(r, False)[:-1] for r in barrido.resultados],
                                   ["optimo" if i == optimo else "" for i in range(len(barrido.resultados))])
        self._nota_barrido.configure(text=texto_tk("\n".join(textos_optimo(barrido))))
        self._panel_fig2.dibujar(dibujar_colas_superpuestas, barrido, self._ctl.config.barrido.ventana_grafica_s)
        self._panel_vs_g.dibujar(dibujar_indicadores_vs_g, barrido, self._ctl.config.simulacion.confianza)
        self._cuaderno_barrido.select(self._pestana_tabla_i)

    def _ver_traza(self) -> None:
        if not self._libre():
            return
        nombre = self._escenario_traza.get()
        if not nombre:
            messagebox.showinfo("Traza", "Elija un escenario.", parent=self._raiz)
            return
        try:
            replica = _entero(self._replica.get(), "La réplica")
            if replica < 1:
                raise ErrorConfiguracion("La réplica debe ser un entero ≥ 1.")
        except ErrorConfiguracion as error:
            self._mostrar_error(error)
            return
        escenario = self._ctl.config.escenario(nombre)
        self._en_segundo_plano(f"Simulando la réplica {replica} de «{nombre}»…",
                               lambda: self._ctl.simular_replica(escenario, replica), self._mostrar_traza)

    def _mostrar_traza(self, resultado: object) -> None:
        assert isinstance(resultado, ResultadoReplica)
        self._tabla_traza.cargar(fila_traza(f) for f in resultado.traza)
        textos = [f"{len(resultado.traza)} eventos (semilla {resultado.semilla}). Q(t) = vehículos en espera, sin el "
                  "que está en servicio. Eventos simultáneos: SALIDA → CAMBIO_FASE → LLEGADA.",
                  texto_balance(resultado.metricas, resultado.parametros.H)]
        censura = texto_censura(resultado.metricas)
        if censura:
            textos.append(censura)
        self._info_traza.configure(text="\n".join(textos))

    def _reproducir(self) -> None:
        if not self._libre():
            return
        nombre = self._escenario_animacion.get()
        if not nombre:
            messagebox.showinfo("Animación", "Elija un escenario.", parent=self._raiz)
            return
        try:
            velocidad = _real(self._velocidad.get(), "La velocidad")
            if velocidad <= 0:
                raise ErrorConfiguracion("La velocidad debe ser mayor que 0.")
        except ErrorConfiguracion as error:
            self._mostrar_error(error)
            return
        escenario = self._ctl.config.escenario(nombre)
        replica = self._ctl.config.salida.replica_detalle
        self._en_segundo_plano(f"Preparando la animación de «{nombre}»…",
                               lambda: self._ctl.simular_replica(escenario, replica),
                               lambda resultado: self._iniciar_animacion(resultado, velocidad))

    def _iniciar_animacion(self, resultado: object, velocidad: float) -> None:
        assert isinstance(resultado, ResultadoReplica)
        self._detener_animacion()
        self._aviso_animacion.pack_forget()
        figura = Figure(dpi=self._d.dpi_graficas)
        self._lienzo_animacion = FigureCanvasTkAgg(figura, master=self._area_animacion)
        self._lienzo_animacion.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self._animacion = self._ctl.animacion.crear_en(figura, resultado, velocidad)
        self._lienzo_animacion.draw()
        for boton in (self._boton_pausa, self._boton_reinicio):
            boton.state(["!disabled"])
        self._boton_pausa.configure(text="❚❚  Pausa")

    def _detener_animacion(self) -> None:
        if self._animacion is not None:
            self._animacion.detener()
            self._animacion = None
        if self._lienzo_animacion is not None:
            self._lienzo_animacion.get_tk_widget().destroy()
            self._lienzo_animacion = None

    def _alternar_pausa(self) -> None:
        if self._animacion is not None:
            self._animacion.alternar_pausa()
            self._boton_pausa.configure(text="▶  Reanudar" if self._animacion.pausado else "❚❚  Pausa")

    def _reiniciar(self) -> None:
        if self._animacion is not None:
            self._animacion.reiniciar()
            self._boton_pausa.configure(text="❚❚  Pausa")

    def _ejecutar_pruebas(self) -> None:
        if not self._libre():
            return
        self._en_segundo_plano("Ejecutando pruebas de verificación…", self._ctl.correr_pruebas, self._mostrar_pruebas)

    def _mostrar_pruebas(self, resultados: object) -> None:
        pruebas: list[ResultadoPrueba] = list(resultados)  # type: ignore[call-overload]
        self._tabla_pruebas.cargar([(str(p.numero), p.descripcion, "OK" if p.exito else "FALLÓ", p.detalle)
                                    for p in pruebas], ["ok" if p.exito else "fallo" for p in pruebas])
        exitos = sum(p.exito for p in pruebas)
        self._resumen_pruebas.configure(text=f"{exitos} de {len(pruebas)} pruebas superadas",
                                        foreground=PALETA.verde if exitos == len(pruebas) else PALETA.rojo)

    def _guardar(self) -> None:
        if not self._libre():
            return
        if not self._resultados and self._barrido is None:
            messagebox.showinfo("Guardar", "Primero simule escenarios o ejecute el barrido.", parent=self._raiz)
            return
        self._estado.set("Guardando CSV y gráficas…")
        self._raiz.configure(cursor="watch")
        self._raiz.update_idletasks()
        try:
            rutas = []
            if self._resultados:
                rutas += self._ctl.exportar_escenarios(self._resultados, self._comparacion, desde_interfaz=True)
            if self._barrido is not None:
                rutas += self._ctl.exportar_barrido(self._barrido, desde_interfaz=True)
        finally:
            self._raiz.configure(cursor="")
        carpeta = rutas[0].parent if rutas else self._ctl.config.salida.carpeta
        self._estado.set(f"{len(rutas)} archivos guardados en {carpeta}")
        messagebox.showinfo("Guardar", f"Se guardaron {len(rutas)} archivos (CSV y PNG) en:\n{carpeta}",
                            parent=self._raiz)

    def _cerrar(self) -> None:
        self._detener_animacion()
        self._ejecutor.cerrar()
        self._raiz.destroy()

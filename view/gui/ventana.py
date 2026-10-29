"""Ventana principal: arma los componentes y los coordina.

Pensada para proyectar: textos grandes, un elemento principal por pestaña y
pocos controles a la vista. Los escenarios se eligen y se simulan desde el
panel izquierdo; los resultados aparecen en las pestañas Resultados, Gráficas,
Barrido de g, Animación y Verificación. Ciclos y Traza son pestañas técnicas
que se muestran desde el menú Ver.

La ventana no calcula ni dibuja resultados: crea el panel y las pestañas, les
reenvía los avisos (configuración cambiada, simulación terminada) y atiende
lo que es de toda la ventana: menús, atajos, pantalla completa y guardado.
Atajos: F5 simula, F11 alterna pantalla completa (Esc la cierra), Ctrl+S
guarda los resultados y Ctrl+Q cierra.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from controller.experiment_service import ServicioExperimentos
from view.gui.contratos import (
    AnimadorIncrustado,
    Exportador,
    ReceptorConfiguracion,
    ReceptorSimulacion,
    SimulacionEscenarios,
)
from view.gui.diseno import DISENO, Estilo, Tema
from view.gui.panel_escenarios import PanelEscenarios
from view.gui.pestanas import (
    PestanaAnimacion,
    PestanaBarrido,
    PestanaCiclos,
    PestanaGraficas,
    PestanaResultados,
    PestanaTraza,
    PestanaVerificacion,
)
from view.gui.tareas import BarraEstado, GestorTareas
from view.gui.widgets import informar
from view.style import PALETA

TITULO = "Simulación de un acceso semaforizado"
SUBTITULO = ("Teoría de colas · llegadas de Poisson · servicio de 1/μ s solo en verde · "
             "resultados del horizonte simulado")
ESTADO_INICIAL = "Listo. F5: simular · F11: pantalla completa."


class VentanaPrincipal:
    """Encabezado, panel de escenarios a la izquierda y pestañas de resultados."""

    def __init__(self, raiz: tk.Tk, servicio: ServicioExperimentos, exportador: Exportador,
                 animador: AnimadorIncrustado) -> None:
        self._raiz = raiz
        self._servicio = servicio
        self._exportador = exportador
        self._simulacion: SimulacionEscenarios | None = None
        self._pantalla_completa = False
        self._d = d = DISENO.escalado(DISENO.factor_para(raiz.winfo_screenwidth()))
        self._configurar_ventana()
        self._tema = Tema(raiz, d)
        self._construir_encabezado()
        barra = BarraEstado(raiz, d, ESTADO_INICIAL)
        barra.pack(side=tk.BOTTOM, fill=tk.X)
        self._tareas = GestorTareas(raiz, barra, d.sondeo_ms)
        self._panel = PanelEscenarios(raiz, d, servicio, self._tareas, self._configuracion_cambiada,
                                      self._mostrar_simulacion)
        self._panel.pack(side=tk.LEFT, fill=tk.Y)
        self._cuaderno = ttk.Notebook(raiz)
        self._cuaderno.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 2 * d.margen), pady=d.margen)
        resultados = PestanaResultados(self._cuaderno, d)
        self._graficas = PestanaGraficas(self._cuaderno, d)
        self._barrido = PestanaBarrido(self._cuaderno, d, self._tema, servicio, self._tareas)
        self._animacion = PestanaAnimacion(self._cuaderno, d, servicio, animador, self._tareas)
        self._verificacion = PestanaVerificacion(self._cuaderno, d, self._tareas, servicio.correr_pruebas)
        ciclos = PestanaCiclos(self._cuaderno, d)
        traza = PestanaTraza(self._cuaderno, d, servicio, self._tareas)
        self._tecnicas = (ciclos.marco, traza.marco)
        self._receptores_simulacion: tuple[ReceptorSimulacion, ...] = (resultados, self._graficas, ciclos)
        self._receptores_configuracion: tuple[ReceptorConfiguracion, ...] = (self._panel, self._animacion, traza)
        self._ver_tecnicas = tk.BooleanVar(value=False)
        self._construir_menu()
        self._vincular_atajos()
        self._mostrar_tecnicas()

    # ------------------------------------------------------------------
    # Construcción
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

    def _construir_encabezado(self) -> None:
        m = self._d.margen
        encabezado = ttk.Frame(self._raiz, style=Estilo.ENCABEZADO, padding=(2 * m, m))
        encabezado.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(encabezado, text=TITULO, style=Estilo.TITULO).pack(anchor="w")
        ttk.Label(encabezado, text=SUBTITULO, style=Estilo.SUBTITULO).pack(anchor="w")

    def _construir_menu(self) -> None:
        barra = tk.Menu(self._raiz)
        archivo = tk.Menu(barra, tearoff=False)
        archivo.add_command(label="Guardar resultados en output/", accelerator="Ctrl+S", command=self._guardar)
        archivo.add_separator()
        archivo.add_command(label="Salir", accelerator="Ctrl+Q", command=self._cerrar)
        simulacion = tk.Menu(barra, tearoff=False)
        simulacion.add_command(label="Simular escenarios seleccionados", accelerator="F5", command=self._panel.simular)
        simulacion.add_command(label="Nuevo escenario…", command=self._panel.nuevo_escenario)
        simulacion.add_command(label="Parámetros de simulación…", command=self._panel.cambiar_parametros)
        ver = tk.Menu(barra, tearoff=False)
        ver.add_command(label="Pantalla completa", accelerator="F11", command=self._alternar_pantalla_completa)
        ver.add_checkbutton(label="Pestañas técnicas (ciclos y traza)", variable=self._ver_tecnicas,
                            command=self._mostrar_tecnicas)
        for etiqueta, menu in (("Archivo", archivo), ("Simulación", simulacion), ("Ver", ver)):
            barra.add_cascade(label=etiqueta, menu=menu)
        self._raiz.configure(menu=barra)

    def _vincular_atajos(self) -> None:
        atajos = {
            "<F5>": self._panel.simular,
            "<F11>": self._alternar_pantalla_completa,
            "<Escape>": self._salir_pantalla_completa,
            "<Control-s>": self._guardar,
            "<Control-q>": self._cerrar,
        }
        for tecla, accion in atajos.items():
            self._raiz.bind(tecla, lambda _evento, accion=accion: accion())

    # ------------------------------------------------------------------
    # Avisos entre componentes
    # ------------------------------------------------------------------
    def _configuracion_cambiada(self) -> None:
        config = self._servicio.config
        for receptor in self._receptores_configuracion:
            receptor.configuracion_cambiada(config)

    def _mostrar_simulacion(self, simulacion: SimulacionEscenarios) -> None:
        self._simulacion = simulacion
        for receptor in self._receptores_simulacion:
            receptor.mostrar_resultados(simulacion)
        self._cuaderno.select(self._graficas.marco)
        n = len(simulacion.resultados[0].metricas)
        self._tareas.informar(f"{len(simulacion.resultados)} escenario(s) simulados con {n} réplicas.")

    # ------------------------------------------------------------------
    # Acciones de la ventana
    # ------------------------------------------------------------------
    def _mostrar_tecnicas(self) -> None:
        """Muestra u oculta las pestañas técnicas según el menú Ver."""
        for marco in self._tecnicas:
            if self._ver_tecnicas.get():
                self._cuaderno.add(marco)
            else:
                self._cuaderno.hide(marco)

    def _alternar_pantalla_completa(self) -> None:
        self._pantalla_completa = not self._pantalla_completa
        self._raiz.attributes("-fullscreen", self._pantalla_completa)

    def _salir_pantalla_completa(self) -> None:
        if self._pantalla_completa:
            self._alternar_pantalla_completa()

    def _guardar(self) -> None:
        """Guarda CSV y PNG de la última simulación de escenarios y del último barrido."""
        if not self._tareas.libre():
            return
        simulacion, barrido = self._simulacion, self._barrido.resultado
        if simulacion is None and barrido is None:
            informar(self._raiz, "Guardar", "Primero simule escenarios o ejecute el barrido.")
            return
        config = self._servicio.config
        with self._tareas.espera("Guardando CSV y gráficas…"):
            rutas = []
            if simulacion is not None:
                rutas += self._exportador.escenarios(simulacion.resultados, simulacion.comparacion)
            if barrido is not None:
                rutas += self._exportador.barrido(barrido, config.barrido.ventana_grafica_s)
        carpeta = rutas[0].parent if rutas else config.salida.carpeta
        self._tareas.informar(f"{len(rutas)} archivos guardados en {carpeta}")
        informar(self._raiz, "Guardar", f"Se guardaron {len(rutas)} archivos (CSV y PNG) en:\n{carpeta}")

    def _cerrar(self) -> None:
        self._animacion.detener()
        self._tareas.cerrar()
        self._raiz.destroy()

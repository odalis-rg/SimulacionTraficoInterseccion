"""Pestaña del barrido de g: parámetros, Tabla I, Fig. 2 y Q̄ / Wq frente a g/T."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from config.settings import ErrorConfiguracion
from controller.analysis import ResultadoBarrido
from controller.experiment_service import ServicioExperimentos
from view.formato import ENCABEZADOS_BARRIDO, fila_barrido, textos_optimo
from view.gui.diseno import DisenoVentana, Tema
from view.gui.entradas import leer_real, leer_reales
from view.gui.pestanas.base import Pestana
from view.gui.tareas import GestorTareas
from view.gui.widgets import Tabla, boton, mostrar_error, texto_tk
from view.plots import dibujar_colas_superpuestas, dibujar_indicadores_vs_g
from view.style import PALETA

AVISO_SIN_BARRIDO = "Pulse «Ejecutar barrido»."


class PestanaBarrido(Pestana):
    """Barrido de g con λ y T fijos; ``resultado`` guarda el último para exportarlo."""

    def __init__(self, cuaderno: ttk.Notebook, diseno: DisenoVentana, tema: Tema, servicio: ServicioExperimentos,
                 tareas: GestorTareas) -> None:
        super().__init__(cuaderno, "Barrido de g", diseno)
        self._servicio = servicio
        self._tareas = tareas
        self.resultado: ResultadoBarrido | None = None
        b, d = servicio.config.barrido, diseno
        self._lam = tk.StringVar(value=f"{b.lam:g}")
        self._T = tk.StringVar(value=f"{b.T:g}")
        self._valores_g = tk.StringVar(value=", ".join(f"{g:g}" for g in b.valores_g))
        fila = self._fila()
        for etiqueta, variable, ancho in (("λ (veh/s)", self._lam, 6), ("T (s)", self._T, 6),
                                          ("Valores de g (s)", self._valores_g, 28)):
            self._campo(fila, etiqueta, ttk.Entry(fila, textvariable=variable, width=ancho))
        tareas.bloqueable(boton(fila, "▶  Ejecutar barrido", self._ejecutar, principal=True)).pack(side=tk.LEFT)
        self._subcuaderno = sub = self._subpestanas()
        self._pestana_tabla = tabla_i = ttk.Frame(sub, padding=d.margen)
        sub.add(tabla_i, text="Tabla I")
        anchos = (d.columna_corta,) * 4 + (d.columna_valor,) * 4
        self._tabla = Tabla(tabla_i, [(t, a, "e") for t, a in zip(ENCABEZADOS_BARRIDO[:-1], anchos)],
                            len(b.valores_g), horizontal=False)
        self._tabla.arbol.tag_configure("optimo", background=PALETA.resaltado, font=tema.tabla_negrita)
        self._tabla.pack(fill=tk.X)
        self._nota_optimo = self._nota(tabla_i, AVISO_SIN_BARRIDO)
        self._nota_optimo.pack(anchor="w", fill=tk.X, pady=(d.separacion, 0))
        self._panel_colas = self._panel_figura(sub, "Fig. 2 · Colas", AVISO_SIN_BARRIDO)
        self._panel_vs_g = self._panel_figura(sub, "Q media y Wq vs g/T", AVISO_SIN_BARRIDO)

    def _ejecutar(self) -> None:
        if not self._tareas.libre():
            return
        try:
            valores = leer_reales(self._valores_g.get(), "Cada valor de g")
            self._servicio.configurar_barrido(leer_real(self._lam.get(), "λ"), leer_real(self._T.get(), "T"), valores)
        except ErrorConfiguracion as error:
            mostrar_error(self.marco, error)
            return
        self._tareas.ejecutar(f"Barrido de {len(valores)} valores de g…",
                              lambda: self._servicio.simular_barrido(self._tareas.progreso), self._mostrar)

    def _mostrar(self, barrido: ResultadoBarrido) -> None:
        self.resultado = barrido
        config = self._servicio.config
        optimo = barrido.indice_optimo
        self._tabla.arbol.configure(height=len(barrido.resultados))
        self._tabla.cargar([fila_barrido(r, False)[:-1] for r in barrido.resultados],
                           ["optimo" if i == optimo else "" for i in range(len(barrido.resultados))])
        self._nota_optimo.configure(text=texto_tk("\n".join(textos_optimo(barrido))))
        self._panel_colas.dibujar(dibujar_colas_superpuestas, barrido, config.barrido.ventana_grafica_s)
        self._panel_vs_g.dibujar(dibujar_indicadores_vs_g, barrido, config.simulacion.confianza)
        self._subcuaderno.select(self._pestana_tabla)

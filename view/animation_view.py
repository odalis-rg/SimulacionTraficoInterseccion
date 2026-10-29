"""Vista animada de una réplica: reproduce con FuncAnimation la traza ya simulada.

El controlador ejecuta primero el modelo y entrega el resultado; esta vista
solo lo reproduce (no consume números aleatorios ni recalcula el modelo), así
que no altera los resultados ni la reproducibilidad.

Zonas: (a) la intersección vista desde arriba, con el semáforo y la fila de
automóviles del acceso, (b) un panel de indicadores en vivo y (c) una mini
gráfica de Q(t) que se dibuja en escalón.
Controles: barra espaciadora = pausa/reanudar; R = reiniciar.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import matplotlib
import matplotlib.pyplot as plt
from matplotlib import animation
from matplotlib.artist import Artist
from matplotlib.backend_bases import KeyEvent
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import Circle, FancyBboxPatch, PathPatch, Rectangle
from matplotlib.path import Path as MplPath

from config.settings import ConfigAnimacion
from model.simulator import ResultadoReplica
from model.traffic_light import Fase
from view.automovil import Automovil, rectangulo
from view.csv_export import nombre_archivo
from view.playback import EstadoInstante, ReproductorTraza
from view.plots import diagnostico_grafico, leyenda_fases, sombrear_fases
from view.style import ESTILO_GRAFICAS, PALETA


@dataclass(frozen=True)
class Geometria:
    """Intersección vista desde arriba, en unidades de datos (aspecto 1:1).

    La calzada principal es horizontal: su carril inferior es el acceso
    modelado (circulación hacia la derecha) y el superior, el sentido contrario
    (sin tráfico en el modelo). La calle transversal es vertical.
    """

    largo: float = 100.0
    base: float = 2.0
    alto: float = 42.0
    """La escena visible va de ``base`` a ``alto`` en y: un alto de 40 aprovecha el espacio de la ventana."""
    calzada_inferior: float = 18.0
    ancho_carril: float = 5.0
    acera: float = 2.6
    cruce_inicio: float = 74.0
    cruce_ancho: float = 12.0
    retiro_cebra: float = 0.2
    franja_cebra: float = 0.75
    hueco_cebra: float = 0.6
    retiro_linea: float = 0.6
    grosor_linea: float = 0.5
    grosor_borde: float = 0.22
    retiro_borde: float = 0.35
    trazo_central: tuple[float, float] = (2.4, 1.6)
    """(largo del trazo, largo del hueco) de las líneas centrales discontinuas."""
    flecha: tuple[float, float, float, float] = (50.0, 6.0, 0.55, 1.7)
    """(x inicial, largo, ancho del astil, ancho de la punta) de la flecha pintada en el acceso."""
    margen_izquierdo: float = 1.0
    separacion_fila: float = 0.5
    proporcion_largo: float = 0.84
    """Largo del auto respecto del espacio que ocupa cada lugar de la fila."""
    proporcion_ancho: float = 0.5
    """Ancho del auto respecto de su largo."""
    umbral_movimiento: float = 0.02
    """Fracción de lugar por debajo de la cual un auto de la fila se considera detenido (luces de freno)."""
    leyenda: tuple[float, float, float] = (2.0, 11.0, 6.0)
    """(x inicial, y del primer renglón, y del segundo) de la leyenda de autos en la manzana inferior."""
    semaforo_ancho: float = 4.6
    semaforo_alto: float = 10.0
    semaforo_base: float = 3.2
    retiro_semaforo: float = 3.6
    grosor_poste: float = 0.5
    radio_lampara: float = 1.55
    radio_halo: float = 2.5
    alfa_halo: float = 0.3

    @property
    def calzada_superior(self) -> float:
        return self.calzada_inferior + 2 * self.ancho_carril

    @property
    def centro_acceso(self) -> float:
        """y del centro del carril de acceso, por donde circulan los autos."""
        return self.calzada_inferior + self.ancho_carril / 2

    @property
    def cruce_fin(self) -> float:
        return self.cruce_inicio + self.cruce_ancho

    @property
    def linea_detencion(self) -> float:
        """x de la línea de detención, antes del paso de cebra del acceso."""
        return self.cruce_inicio - self.acera - self.retiro_linea


@dataclass(frozen=True)
class Disposicion:
    """Tamaño de la figura, proporciones de las tres zonas y tipografía."""

    ancho: float = 12.0
    alto: float = 6.4
    filas: tuple[float, float] = (2.0, 1.0)
    columnas: tuple[float, float] = (3.2, 1.25)
    margenes: tuple[float, float, float, float] = (0.06, 0.98, 0.93, 0.09)
    separacion: tuple[float, float] = (0.06, 0.3)
    texto_titulo: float = 16.0
    texto: float = 12.5
    texto_valor: float = 14.0
    texto_pequeno: float = 10.5
    renglon: float = 0.085
    alfa_franjas: float = 0.9
    holgura_serie: float = 1.3


GEOMETRIA = Geometria()
DISPOSICION = Disposicion()


def _suavizar(p: float) -> float:
    """Curva ease-out cúbica en [0, 1]: arranca rápido y frena suave."""
    p = min(max(p, 0.0), 1.0)
    return 1.0 - (1.0 - p) ** 3


def _fotogramas(fin: float, paso: float) -> int:
    """Número de fotogramas para cubrir [0, fin] con ``paso`` s simulados por fotograma."""
    return math.floor(fin / paso) + 1


def _trazos(inicio: float, fin: float, trazo: float, hueco: float) -> list[tuple[float, float]]:
    """Segmentos (desde, hasta) de una línea discontinua entre ``inicio`` y ``fin``."""
    segmentos, x = [], inicio
    while x < fin:
        segmentos.append((x, min(x + trazo, fin)))
        x += trazo + hueco
    return segmentos


def _franjas(inicio: float, fin: float, franja: float, hueco: float) -> list[float]:
    """Inicio de cada franja de un paso de cebra repartidas entre ``inicio`` y ``fin``."""
    cantidad = int((fin - inicio + hueco) // (franja + hueco))
    sobrante = fin - inicio - cantidad * franja - (cantidad - 1) * hueco
    return [inicio + sobrante / 2 + i * (franja + hueco) for i in range(cantidad)]


def _pintar(ax: plt.Axes, caminos: list[MplPath], color: str, orden: float) -> None:
    """Agrega como una sola pieza estática un conjunto de figuras del mismo color."""
    ax.add_patch(PathPatch(MplPath.make_compound_path(*caminos), facecolor=color, edgecolor="none", zorder=orden))


class _EscenaAnimada:
    """Figura de la animación y su actualización para un instante simulado t."""

    def __init__(self, figura: Figure, reproductor: ReproductorTraza, config: ConfigAnimacion, controles: bool) -> None:
        self._rep = reproductor
        self._cfg = config
        self._d = config.duracion_transicion_s
        self._servicio = reproductor.parametros.tiempo_servicio
        g = GEOMETRIA
        self._paso = (g.linea_detencion - g.separacion_fila - g.margen_izquierdo) / config.max_vehiculos_fila
        self._largo = self._paso * g.proporcion_largo
        disp = DISPOSICION
        rejilla = figura.add_gridspec(
            2, 2, height_ratios=disp.filas, width_ratios=disp.columnas, left=disp.margenes[0],
            right=disp.margenes[1], top=disp.margenes[2], bottom=disp.margenes[3],
            wspace=disp.separacion[0], hspace=disp.separacion[1],
        )
        figura.set_facecolor(PALETA.fondo_animacion)
        self._construir_via(figura.add_subplot(rejilla[0, 0]))
        self._construir_panel(figura.add_subplot(rejilla[0, 1]), controles)
        self._construir_serie(figura.add_subplot(rejilla[1, :]))
        p = reproductor.parametros
        figura.suptitle(
            f"Acceso semaforizado · λ = {p.lam:g} veh/s · g = {p.g:g} s · r = {p.r:g} s · μ = {p.mu:g} veh/s",
            x=disp.margenes[0], ha="left", fontsize=disp.texto_titulo, color=PALETA.texto, fontweight="bold",
        )

    # -- Construcción ------------------------------------------------------
    def _construir_via(self, ax: plt.Axes) -> None:
        g = GEOMETRIA
        ax.set_xlim(0, g.largo)
        ax.set_ylim(g.base, g.alto)
        ax.set_aspect("equal")
        ax.axis("off")
        _pintar(ax, [rectangulo(0, 0, g.largo, g.alto)], PALETA.manzana, 0.0)
        _pintar(ax, [rectangulo(0, g.calzada_inferior - g.acera, g.largo, 2 * (g.ancho_carril + g.acera)),
                     rectangulo(g.cruce_inicio - g.acera, 0, g.cruce_ancho + 2 * g.acera, g.alto)], PALETA.acera, 0.1)
        _pintar(ax, [rectangulo(0, g.calzada_inferior, g.largo, 2 * g.ancho_carril),
                     rectangulo(g.cruce_inicio, 0, g.cruce_ancho, g.alto)], PALETA.asfalto, 0.2)
        _pintar(ax, self._marcas_blancas(), PALETA.marca_vial, 0.3)
        _pintar(ax, self._lineas_centrales(), PALETA.linea_central, 0.3)
        self._construir_semaforo(ax)
        self._construir_leyenda(ax)
        cantidad = self._cfg.max_vehiculos_fila + 2 + math.ceil(self._d / self._servicio)
        self._autos = [Automovil(ax, self._largo, self._largo * g.proporcion_ancho, zorder=3) for _ in range(cantidad)]
        self._exceso = ax.text(g.margen_izquierdo, g.calzada_superior + g.acera + 1.2, "", ha="left", va="bottom",
                               fontsize=DISPOSICION.texto, color=PALETA.texto, fontweight="bold", zorder=5,
                               bbox={"boxstyle": "round,pad=0.35", "facecolor": PALETA.superficie, "edgecolor": "none"})

    def _marcas_blancas(self) -> list[MplPath]:
        """Bordes de carril, línea de detención, pasos de cebra y flecha del acceso."""
        g = GEOMETRIA
        antes, despues = g.cruce_inicio - g.acera, g.cruce_fin + g.acera
        bajo, sobre = g.calzada_inferior - g.acera, g.calzada_superior + g.acera
        marcas = []
        for y in (g.calzada_inferior + g.retiro_borde, g.calzada_superior - g.retiro_borde - g.grosor_borde):
            marcas += [rectangulo(0, y, antes, g.grosor_borde), rectangulo(despues, y, g.largo - despues, g.grosor_borde)]
        for x in (g.cruce_inicio + g.retiro_borde, g.cruce_fin - g.retiro_borde - g.grosor_borde):
            marcas += [rectangulo(x, 0, g.grosor_borde, bajo), rectangulo(x, sobre, g.grosor_borde, g.alto - sobre)]
        marcas.append(rectangulo(g.linea_detencion - g.grosor_linea, g.calzada_inferior, g.grosor_linea, g.ancho_carril))
        profundidad = g.acera - 2 * g.retiro_cebra
        for x in (antes + g.retiro_cebra, g.cruce_fin + g.retiro_cebra):
            marcas += [rectangulo(x, y, profundidad, g.franja_cebra) for y in
                       _franjas(g.calzada_inferior, g.calzada_superior, g.franja_cebra, g.hueco_cebra)]
        for y in (bajo + g.retiro_cebra, g.calzada_superior + g.retiro_cebra):
            marcas += [rectangulo(x, y, g.franja_cebra, profundidad) for x in
                       _franjas(g.cruce_inicio, g.cruce_fin, g.franja_cebra, g.hueco_cebra)]
        marcas.append(self._flecha())
        return marcas

    @staticmethod
    def _flecha() -> MplPath:
        g = GEOMETRIA
        x0, largo, astil, punta = g.flecha
        x1, x2, y = x0 + largo - punta, x0 + largo, g.centro_acceso
        vertices = [(x0, y - astil / 2), (x1, y - astil / 2), (x1, y - punta / 2), (x2, y), (x1, y + punta / 2),
                    (x1, y + astil / 2), (x0, y + astil / 2), (x0, y - astil / 2)]
        return MplPath(vertices, [MplPath.MOVETO] + [MplPath.LINETO] * 6 + [MplPath.CLOSEPOLY])

    @staticmethod
    def _lineas_centrales() -> list[MplPath]:
        """Líneas amarillas discontinuas que separan los sentidos de circulación."""
        g = GEOMETRIA
        trazo, hueco = g.trazo_central
        y = g.calzada_inferior + g.ancho_carril - g.grosor_borde / 2
        x = g.cruce_inicio + g.cruce_ancho / 2 - g.grosor_borde / 2
        tramos_x = _trazos(0, g.cruce_inicio - g.acera, trazo, hueco) + _trazos(g.cruce_fin + g.acera, g.largo, trazo, hueco)
        tramos_y = (_trazos(0, g.calzada_inferior - g.acera, trazo, hueco)
                    + _trazos(g.calzada_superior + g.acera, g.alto, trazo, hueco))
        return ([rectangulo(a, y, b - a, g.grosor_borde) for a, b in tramos_x]
                + [rectangulo(x, a, g.grosor_borde, b - a) for a, b in tramos_y])

    def _construir_leyenda(self, ax: plt.Axes) -> None:
        """Autos de ejemplo que explican los colores (estáticos)."""
        g = GEOMETRIA
        x, *renglones = g.leyenda
        ejemplos = ((PALETA.vehiculo_servicio, False, "En servicio: cruza la intersección"),
                    (PALETA.autos[0], True, "En espera: luces de freno encendidas"))
        for y, (color, frenando, texto) in zip(renglones, ejemplos):
            Automovil(ax, self._largo, self._largo * g.proporcion_ancho, zorder=3).mostrar(
                x + self._largo / 2, y, color, frenando, 1.0)
            ax.text(x + self._largo * 1.25, y, texto, va="center", fontsize=DISPOSICION.texto_pequeno,
                    color=PALETA.texto_secundario, zorder=5)

    def _construir_semaforo(self, ax: plt.Axes) -> None:
        """Semáforo en la esquina, antes del paso de cebra (vista frontal)."""
        g = GEOMETRIA
        x = g.linea_detencion - g.retiro_semaforo
        tope = g.semaforo_base + g.semaforo_alto
        acera_media = g.calzada_inferior - g.acera / 2
        ax.add_patch(Rectangle((x - g.grosor_poste / 2, tope), g.grosor_poste, acera_media - tope,
                               facecolor=PALETA.carcasa_semaforo, edgecolor="none", zorder=4))
        ax.add_patch(Circle((x, acera_media), g.grosor_poste, facecolor=PALETA.carcasa_semaforo, edgecolor="none",
                            zorder=4))
        ax.add_patch(FancyBboxPatch((x - g.semaforo_ancho / 2, g.semaforo_base), g.semaforo_ancho, g.semaforo_alto,
                                    boxstyle="round,pad=0,rounding_size=1.0", facecolor=PALETA.carcasa_semaforo,
                                    edgecolor="none", zorder=4))
        y_rojo = g.semaforo_base + g.semaforo_alto * 0.72
        y_verde = g.semaforo_base + g.semaforo_alto * 0.28
        self._halo = Circle((x, y_rojo), g.radio_halo, edgecolor="none", alpha=g.alfa_halo, zorder=4)
        self._lampara_roja = Circle((x, y_rojo), g.radio_lampara, edgecolor="none", zorder=5)
        self._lampara_verde = Circle((x, y_verde), g.radio_lampara, edgecolor="none", zorder=5)
        self._centros_lamparas = {Fase.ROJO: (x, y_rojo), Fase.VERDE: (x, y_verde)}
        for lampara in (self._halo, self._lampara_roja, self._lampara_verde):
            ax.add_patch(lampara)

    def _construir_panel(self, ax: plt.Axes, controles: bool) -> None:
        disp = DISPOSICION
        ax.axis("off")
        ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.04",
                                    transform=ax.transAxes, facecolor=PALETA.superficie, edgecolor="none"))
        ax.text(0.07, 0.93, "Indicadores en vivo", transform=ax.transAxes, fontsize=disp.texto_valor,
                fontweight="bold", color=PALETA.texto, va="top")
        etiquetas = ("Tiempo simulado", "Semáforo", "Cambio de fase en", "Q(t) en espera",
                     "En servicio", "Llegados", "Salidos", "Ciclo")
        self._valores: dict[str, plt.Text] = {}
        for i, etiqueta in enumerate(etiquetas):
            y = 0.80 - i * disp.renglon
            ax.text(0.07, y, etiqueta, transform=ax.transAxes, fontsize=disp.texto, color=PALETA.texto_secundario,
                    va="center")
            self._valores[etiqueta] = ax.text(0.93, y, "", transform=ax.transAxes, fontsize=disp.texto_valor,
                                              color=PALETA.texto, va="center", ha="right", fontweight="bold")
        ayuda = "Espacio: pausa · R: reiniciar" if controles else ""
        ax.text(0.07, 0.035, ayuda, transform=ax.transAxes, fontsize=disp.texto_pequeno, color=PALETA.texto_tenue,
                va="center")
        self._estado_reproduccion = ax.text(0.07, 0.09, "", transform=ax.transAxes, fontsize=disp.texto_pequeno,
                                            color=PALETA.texto_secundario, va="center")

    def _construir_serie(self, ax: plt.Axes) -> None:
        rep = self._rep
        sombrear_fases(ax, rep.fases, rep.fin)
        for coleccion in ax.collections:
            coleccion.set_alpha(DISPOSICION.alfa_franjas)
        (self._linea,) = ax.plot([], [], drawstyle="steps-post", color=PALETA.serie_principal, lw=1.6, zorder=3)
        self._cursor = ax.axvline(0, color=PALETA.texto, lw=1.0, zorder=4)
        ax.set_xlim(0, rep.fin)
        ax.set_ylim(0, max(float(rep.serie_q.max()), 1.0) * DISPOSICION.holgura_serie + 1)
        ax.set_xlabel("Tiempo simulado (s)")
        ax.set_ylabel("Q(t) (veh)")
        ax.grid(axis="x", visible=False)
        ax.set_title("Q(t): vehículos en espera, sin el vehículo en servicio", loc="left", fontsize=DISPOSICION.texto)
        ax.legend(handles=leyenda_fases(), loc="lower right", bbox_to_anchor=(1.0, 1.0), ncols=3,
                  fontsize=DISPOSICION.texto_pequeno, borderaxespad=0.2)

    # -- Posiciones ----------------------------------------------------------
    def _x_fila(self, posicion: float) -> float:
        """Centro x del auto en la posición (continua) de la fila; 0 = junto a la línea de detención."""
        g = GEOMETRIA
        return g.linea_detencion - g.separacion_fila - self._paso * (posicion + 0.5)

    def _x_cruzado(self) -> float:
        """Centro x del auto al terminar su servicio: ya atravesó la intersección."""
        return GEOMETRIA.cruce_fin + self._largo / 2

    def _x_en_espera(self, vehiculo: int, posicion: float, t: float) -> tuple[float, bool]:
        """Posición en la fila y si el auto todavía está entrando desde la izquierda."""
        destino = self._x_fila(posicion)
        avance = (t - self._rep.t_llegada(vehiculo)) / self._d
        if avance >= 1:
            return destino, False
        entrada = -self._largo
        return entrada + (destino - entrada) * _suavizar(avance), True

    def _recorrido_servicio(self, vehiculo: int) -> tuple[float, float]:
        """(x inicial, distancia) del servicio: desde su lugar en la fila hasta cruzar la intersección."""
        origen, _ = self._x_en_espera(vehiculo, 0.0, self._rep.t_inicio_servicio(vehiculo))
        return origen, self._x_cruzado() - origen

    @staticmethod
    def _color(vehiculo: int) -> str:
        return PALETA.autos[vehiculo % len(PALETA.autos)]

    # -- Dibujo por fotograma ------------------------------------------------
    def dibujar(self, t: float) -> list[Artist]:
        """Actualiza todas las zonas para el instante simulado t; devuelve los artistas que cambian."""
        estado = self._rep.estado(t)
        usados = self._dibujar_fila(estado, t)
        usados = self._dibujar_servicio(estado, t, usados)
        usados = self._dibujar_salidas(t, usados)
        for auto in self._autos[usados:]:
            auto.ocultar()
        self._dibujar_semaforo(estado)
        self._dibujar_panel(estado)
        self._linea.set_data(*self._rep.serie_hasta(t))
        self._cursor.set_xdata([t, t])
        return [*(pieza for auto in self._autos for pieza in auto.artistas), self._halo, self._lampara_roja,
                self._lampara_verde, self._exceso, *self._valores.values(), self._estado_reproduccion,
                self._linea, self._cursor]

    def _mostrar(self, indice: int, x: float, color: str, frenando: bool, alfa: float) -> int:
        """Ubica el auto ``indice`` del conjunto reutilizable; devuelve el siguiente índice libre."""
        if indice < len(self._autos):
            self._autos[indice].mostrar(x, GEOMETRIA.centro_acceso, color, frenando, alfa)
        return indice + 1

    def _dibujar_fila(self, estado: EstadoInstante, t: float) -> int:
        visibles = min(estado.cola, self._cfg.max_vehiculos_fila)
        inicios = self._rep.inicios_recientes(t, self._d)
        usados = 0
        for k in range(visibles):
            vehiculo = estado.primero_en_espera + k
            llegada = self._rep.t_llegada(vehiculo)
            # Tras cada inicio de servicio la fila avanza un lugar de forma suave.
            rezago = sum(1.0 - _suavizar((t - s) / self._d) for s in inicios if s > llegada)
            x, entrando = self._x_en_espera(vehiculo, k + rezago, t)
            detenido = not entrando and rezago < GEOMETRIA.umbral_movimiento
            usados = self._mostrar(usados, x, self._color(vehiculo), detenido, 1.0)
        exceso = estado.cola - visibles
        self._exceso.set_text(f"+{exceso} vehículos más en espera" if exceso > 0 else "")
        self._exceso.set_visible(exceso > 0)
        return usados

    def _dibujar_servicio(self, estado: EstadoInstante, t: float, usados: int) -> int:
        """El auto en servicio acelera desde la fila hasta cruzar la intersección; tarda 1/μ."""
        if estado.en_servicio is None:
            return usados
        origen, distancia = self._recorrido_servicio(estado.en_servicio)
        avance = min((t - self._rep.t_inicio_servicio(estado.en_servicio)) / self._servicio, 1.0)
        return self._mostrar(usados, origen + distancia * avance ** 2, PALETA.vehiculo_servicio, False, 1.0)

    def _dibujar_salidas(self, t: float, usados: int) -> int:
        """Tras salir, el auto sigue con la velocidad con que terminó el servicio y se desvanece."""
        for instante, vehiculo in self._rep.salidas_recientes(t, self._d):
            _, distancia = self._recorrido_servicio(vehiculo)
            x = self._x_cruzado() + 2 * distancia / self._servicio * (t - instante)
            usados = self._mostrar(usados, x, PALETA.vehiculo_servicio, False, 1.0 - (t - instante) / self._d)
        return usados

    def _dibujar_semaforo(self, estado: EstadoInstante) -> None:
        rojo = estado.fase is Fase.ROJO
        self._lampara_roja.set_facecolor(PALETA.rojo if rojo else PALETA.lampara_apagada)
        self._lampara_verde.set_facecolor(PALETA.lampara_apagada if rojo else PALETA.verde)
        self._halo.set_center(self._centros_lamparas[estado.fase])
        self._halo.set_facecolor(PALETA.rojo if rojo else PALETA.verde)

    def _dibujar_panel(self, estado: EstadoInstante) -> None:
        valores = self._valores
        valores["Tiempo simulado"].set_text(f"{estado.tiempo:.1f} s")
        valores["Semáforo"].set_text(estado.fase.value)
        valores["Semáforo"].set_color(PALETA.rojo if estado.fase is Fase.ROJO else PALETA.verde)
        valores["Cambio de fase en"].set_text(f"{estado.restante_fase:.1f} s")
        valores["Q(t) en espera"].set_text(f"{estado.cola} veh")
        valores["En servicio"].set_text("—" if estado.en_servicio is None else f"#{estado.en_servicio}")
        valores["Llegados"].set_text(str(estado.llegados))
        valores["Salidos"].set_text(str(estado.salidos))
        valores["Ciclo"].set_text(str(estado.ciclo))

    def estado_reproduccion(self, texto: str) -> None:
        self._estado_reproduccion.set_text(texto)


class ControlReproduccion:
    """Reproducción en tiempo real con pausa y reinicio.

    El instante simulado se calcula con el reloj real (t = velocidad × tiempo
    transcurrido), así la velocidad configurada se respeta aunque el equipo
    dibuje menos fotogramas por segundo. La pausa congela ese instante; el
    temporizador sigue activo y matplotlib lo detiene al cerrar la ventana.
    Con ``teclas`` la barra espaciadora pausa/reanuda y R reinicia.
    """

    def __init__(self, figura: Figure, escena: _EscenaAnimada, fin: float, velocidad: float,
                 intervalo_ms: float, teclas: bool) -> None:
        self._escena = escena
        self._fin = fin
        self._velocidad = velocidad
        self._t_base = 0.0
        self._reloj: float | None = None
        self._pausado = False
        self._animacion = animation.FuncAnimation(
            figura, self._actualizar, interval=intervalo_ms, blit=True, cache_frame_data=False
        )
        if teclas:
            figura.canvas.mpl_connect("key_press_event", self._tecla)

    @property
    def pausado(self) -> bool:
        return self._pausado

    def _tiempo(self) -> float:
        """Instante simulado actual: el congelado en pausa o el que marca el reloj real."""
        if self._pausado or self._reloj is None:
            return self._t_base
        return min(self._t_base + (time.perf_counter() - self._reloj) * self._velocidad, self._fin)

    def _actualizar(self, _cuadro: int) -> list[Artist]:
        if self._reloj is None:  # el reloj arranca con el primer cuadro visible
            self._reloj = time.perf_counter()
        t = self._tiempo()
        if self._pausado:
            self._escena.estado_reproduccion("❚❚ en pausa")
        elif t >= self._fin:
            self._escena.estado_reproduccion("■ fin de la ventana · R para repetir")
        else:
            self._escena.estado_reproduccion("▶ reproduciendo")
        return self._escena.dibujar(t)

    def alternar_pausa(self) -> None:
        """Pausa o reanuda (sin efecto al final de la ventana)."""
        if self._tiempo() >= self._fin:
            return
        if self._pausado:
            self._reloj = time.perf_counter()
        else:
            self._t_base = self._tiempo()
        self._pausado = not self._pausado

    def reiniciar(self) -> None:
        """Vuelve a t = 0 y reproduce."""
        self._t_base, self._reloj, self._pausado = 0.0, time.perf_counter(), False

    def detener(self) -> None:
        """Detiene el temporizador (al reemplazar la animación por otra)."""
        if self._animacion.event_source is not None:
            self._animacion.event_source.stop()

    def _tecla(self, evento: KeyEvent) -> None:
        if evento.key == " ":
            self.alternar_pausa()
        elif evento.key in ("r", "R"):
            self.reiniciar()


class VistaAnimacion:
    """Muestra la animación en una ventana y, si se pide, la guarda como GIF."""

    def __init__(self, config: ConfigAnimacion, carpeta: Path) -> None:
        self._cfg = config
        self._carpeta = carpeta

    def reproducir(self, nombre: str, replica: int, resultado: ResultadoReplica,
                   informar: Callable[[str], None]) -> None:
        """Reproduce los primeros ``ventana_s`` segundos de la réplica ya simulada."""
        reproductor = ReproductorTraza(resultado, self._cfg.ventana_s)
        if self._cfg.guardar_gif:
            self._guardar_gif(reproductor, nombre, replica, informar)
        causa = diagnostico_grafico()
        if causa:
            informar(f"No se puede abrir la ventana de la animación: {causa}")
            return
        informar(f"Animación de '{nombre}' (réplica {replica}): primeros {reproductor.fin:g} s a "
                 f"×{self._cfg.velocidad:g}. Cierre la ventana para volver.")
        self._mostrar(nombre, reproductor)

    def crear_en(self, figura: Figure, resultado: ResultadoReplica, velocidad: float) -> ControlReproduccion:
        """Prepara la animación sobre una figura ya incrustada (interfaz gráfica).

        Devuelve el control, que debe conservarse mientras la animación esté visible.
        """
        reproductor = ReproductorTraza(resultado, self._cfg.ventana_s)
        with matplotlib.rc_context(ESTILO_GRAFICAS):
            escena = _EscenaAnimada(figura, reproductor, self._cfg, controles=False)
        return ControlReproduccion(figura, escena, reproductor.fin, velocidad, 1000 / self._cfg.fps, teclas=False)

    def _mostrar(self, nombre: str, reproductor: ReproductorTraza) -> None:
        teclas_inicio = [k for k in plt.rcParams["keymap.home"] if k.lower() != "r"]  # R = reiniciar
        with matplotlib.rc_context({**ESTILO_GRAFICAS, "keymap.home": teclas_inicio}):
            figura = plt.figure(figsize=(DISPOSICION.ancho, DISPOSICION.alto))
            if figura.canvas.manager is not None:
                figura.canvas.manager.set_window_title(f"Animación — {nombre}")
            escena = _EscenaAnimada(figura, reproductor, self._cfg, controles=True)
            control = ControlReproduccion(figura, escena, reproductor.fin, self._cfg.velocidad,
                                          1000 / self._cfg.fps, teclas=True)
            plt.show()
        del control

    def _guardar_gif(self, reproductor: ReproductorTraza, nombre: str, replica: int,
                     informar: Callable[[str], None]) -> None:
        if not animation.writers.is_available("pillow"):
            informar("Pillow no está disponible: no se guarda el GIF (instale el paquete 'Pillow').")
            return
        paso = self._cfg.velocidad / self._cfg.fps_gif
        total = _fotogramas(reproductor.fin, paso)
        ruta = self._carpeta / f"animacion_{nombre_archivo(nombre)}_rep{replica}.gif"
        informar(f"Guardando GIF ({total} fotogramas a {self._cfg.fps_gif} fps); puede tardar unos segundos…")
        with matplotlib.rc_context(ESTILO_GRAFICAS):
            figura = Figure(figsize=(DISPOSICION.ancho, DISPOSICION.alto))
            FigureCanvasAgg(figura)
            escena = _EscenaAnimada(figura, reproductor, self._cfg, controles=False)
            grabacion = animation.FuncAnimation(figura, lambda i: escena.dibujar(i * paso), frames=total, blit=False)
            self._carpeta.mkdir(parents=True, exist_ok=True)
            grabacion.save(ruta, writer=animation.PillowWriter(fps=self._cfg.fps_gif), dpi=self._cfg.dpi_gif)
        informar(f"GIF guardado en {ruta}")

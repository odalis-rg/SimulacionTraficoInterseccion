"""Reproducción de la escena: ventana interactiva, figura incrustada y GIF.

El controlador ejecuta primero el modelo y entrega el resultado; aquí solo se
reproduce su traza (no se consumen números aleatorios ni se recalcula el
modelo), así que la animación no altera los resultados ni la reproducibilidad.
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Callable

import matplotlib
import matplotlib.pyplot as plt
from matplotlib import animation
from matplotlib.artist import Artist
from matplotlib.backend_bases import KeyEvent
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from config.settings import ConfigAnimacion
from model.simulator import ResultadoReplica
from view.animacion.escena import EscenaAnimada
from view.animacion.medidas import DISPOSICION
from view.animacion.traza import ReproductorTraza
from view.csv_export import nombre_archivo
from view.entorno_grafico import diagnostico_grafico
from view.style import ESTILO_GRAFICAS


def _fotogramas(fin: float, paso: float) -> int:
    """Número de fotogramas para cubrir [0, fin] con ``paso`` s simulados por fotograma."""
    return math.floor(fin / paso) + 1


class ControlReproduccion:
    """Reproducción en tiempo real con pausa y reinicio.

    El instante simulado se calcula con el reloj real (t = velocidad × tiempo
    transcurrido), así la velocidad configurada se respeta aunque el equipo
    dibuje menos fotogramas por segundo. La pausa congela ese instante; el
    temporizador sigue activo y matplotlib lo detiene al cerrar la ventana.
    Con ``teclas`` la barra espaciadora pausa/reanuda y R reinicia.
    """

    def __init__(self, figura: Figure, escena: EscenaAnimada, fin: float, velocidad: float,
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
    """Muestra la animación en una ventana, la incrusta en la interfaz o la guarda como GIF."""

    def __init__(self, config: ConfigAnimacion, carpeta: Path) -> None:
        self._cfg = config
        self._carpeta = carpeta

    def reproducir(self, nombre: str, replica: int, resultado: ResultadoReplica,
                   informar: Callable[[str], None]) -> None:
        """Reproduce en una ventana los primeros ``ventana_s`` segundos de la réplica ya simulada."""
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
            escena = EscenaAnimada(figura, reproductor, self._cfg, controles=False)
        return ControlReproduccion(figura, escena, reproductor.fin, velocidad, 1000 / self._cfg.fps, teclas=False)

    def _mostrar(self, nombre: str, reproductor: ReproductorTraza) -> None:
        teclas_inicio = [k for k in plt.rcParams["keymap.home"] if k.lower() != "r"]  # R = reiniciar
        with matplotlib.rc_context({**ESTILO_GRAFICAS, "keymap.home": teclas_inicio}):
            figura = plt.figure(figsize=(DISPOSICION.ancho, DISPOSICION.alto))
            if figura.canvas.manager is not None:
                figura.canvas.manager.set_window_title(f"Animación — {nombre}")
            escena = EscenaAnimada(figura, reproductor, self._cfg, controles=True)
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
            escena = EscenaAnimada(figura, reproductor, self._cfg, controles=False)
            grabacion = animation.FuncAnimation(figura, lambda i: escena.dibujar(i * paso), frames=total, blit=False)
            self._carpeta.mkdir(parents=True, exist_ok=True)
            grabacion.save(ruta, writer=animation.PillowWriter(fps=self._cfg.fps_gif), dpi=self._cfg.dpi_gif)
        informar(f"GIF guardado en {ruta}")

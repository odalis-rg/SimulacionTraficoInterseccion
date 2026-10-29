"""Tareas largas sin congelar la ventana: hilo de trabajo, barra de estado y bloqueo de botones."""

from __future__ import annotations

import queue
import tkinter as tk
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from tkinter import ttk
from typing import Callable, Iterator, TypeVar

from view.gui.diseno import DisenoVentana, Estilo
from view.gui.widgets import mostrar_error

T = TypeVar("T")


class EjecutorSegundoPlano:
    """Ejecuta tareas en un hilo y entrega resultados y avisos en el hilo de Tkinter.

    Tkinter no admite llamadas desde otros hilos: la tarea solo calcula y los
    avisos pasan por una cola que se vacía con ``after`` en el hilo principal.
    """

    def __init__(self, raiz: tk.Misc, intervalo_ms: int, al_avisar: Callable[[str], None]) -> None:
        self._raiz = raiz
        self._intervalo = intervalo_ms
        self._al_avisar = al_avisar
        self._avisos: queue.Queue[str] = queue.Queue()
        self._hilo = ThreadPoolExecutor(max_workers=1)

    def avisar(self, texto: str) -> None:
        """Encola un aviso; puede llamarse desde el hilo de trabajo."""
        self._avisos.put(texto)

    def ejecutar(self, tarea: Callable[[], T], al_terminar: Callable[[T], None],
                 al_fallar: Callable[[BaseException], None]) -> None:
        self._esperar(self._hilo.submit(tarea), al_terminar, al_fallar)

    def _esperar(self, futuro: Future[T], al_terminar: Callable[[T], None],
                 al_fallar: Callable[[BaseException], None]) -> None:
        while not self._avisos.empty():
            self._al_avisar(self._avisos.get_nowait())
        if not futuro.done():
            self._raiz.after(self._intervalo, self._esperar, futuro, al_terminar, al_fallar)
            return
        error = futuro.exception()
        if error is not None:
            al_fallar(error)
        else:
            al_terminar(futuro.result())

    def cerrar(self) -> None:
        self._hilo.shutdown(wait=False, cancel_futures=True)


class BarraEstado(ttk.Frame):
    """Línea de estado al pie de la ventana, con barra de progreso mientras hay una tarea."""

    def __init__(self, padre: tk.Misc, diseno: DisenoVentana, texto: str) -> None:
        m = diseno.margen
        super().__init__(padre, padding=(2 * m, 0, 2 * m, m // 2))
        self._texto = tk.StringVar(value=texto)
        ttk.Label(self, textvariable=self._texto, style=Estilo.NOTA).pack(side=tk.LEFT)
        self._progreso = ttk.Progressbar(self, mode="indeterminate", length=diseno.ancho_panel // 2)

    def mostrar(self, texto: str) -> None:
        self._texto.set(texto)

    def trabajando(self, activa: bool) -> None:
        """Muestra (y anima) u oculta la barra de progreso."""
        if activa:
            self._progreso.pack(side=tk.RIGHT)
            self._progreso.start()
        else:
            self._progreso.stop()
            self._progreso.pack_forget()


class GestorTareas:
    """Una tarea a la vez: la ejecuta en segundo plano y refleja su estado en la ventana.

    Mientras hay una tarea, los botones registrados con ``bloqueable`` se
    desactivan y la barra de estado muestra el progreso; si la tarea falla, el
    error se informa en un diálogo.
    """

    def __init__(self, raiz: tk.Misc, barra: BarraEstado, intervalo_ms: int) -> None:
        self._raiz = raiz
        self._barra = barra
        self._ejecutor = EjecutorSegundoPlano(raiz, intervalo_ms, barra.mostrar)
        self._botones: list[ttk.Button] = []
        self._ocupada = False

    def bloqueable(self, boton: ttk.Button) -> ttk.Button:
        """Registra un botón que se desactiva durante las tareas; lo devuelve para ubicarlo."""
        self._botones.append(boton)
        return boton

    def libre(self) -> bool:
        """False (y un aviso en la barra de estado) si hay una tarea en curso."""
        if self._ocupada:
            self.informar("Espere a que termine la tarea en curso…")
        return not self._ocupada

    def informar(self, texto: str) -> None:
        self._barra.mostrar(texto)

    def progreso(self, nombre: str, replicas: int, segundos: float) -> None:
        """Aviso de escenario terminado; lo llama el hilo de trabajo (``Progreso`` del servicio)."""
        self._ejecutor.avisar(f"✓ {nombre}: {replicas} réplicas en {segundos:.2f} s")

    def ejecutar(self, descripcion: str, tarea: Callable[[], T], al_terminar: Callable[[T], None]) -> None:
        """Ejecuta ``tarea`` en el hilo de trabajo y entrega su resultado a ``al_terminar``."""
        self._ocupar(True, descripcion)

        def terminar(resultado: T) -> None:
            self._ocupar(False, "Listo.")
            al_terminar(resultado)

        def fallar(error: BaseException) -> None:
            self._ocupar(False, "Se produjo un error.")
            mostrar_error(self._raiz, error)

        self._ejecutor.ejecutar(tarea, terminar, fallar)

    @contextmanager
    def espera(self, descripcion: str) -> Iterator[None]:
        """Acción breve en el hilo de la interfaz, con cursor de espera mientras dura."""
        self.informar(descripcion)
        self._raiz.configure(cursor="watch")
        self._raiz.update_idletasks()
        try:
            yield
        finally:
            self._raiz.configure(cursor="")

    def cerrar(self) -> None:
        self._ejecutor.cerrar()

    def _ocupar(self, ocupada: bool, texto: str) -> None:
        self._ocupada = ocupada
        for boton in self._botones:
            boton.state(["disabled"] if ocupada else ["!disabled"])
        self._barra.trabajando(ocupada)
        self.informar(texto)

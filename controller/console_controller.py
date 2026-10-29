"""Controlador de consola: flujos del menú y de la línea de comandos.

Recibe por inyección el servicio de experimentos y lo que necesita mostrar
(vista de consola, exportador y animación). No crea a sus colaboradores ni
contiene lógica de simulación: pide los cálculos al servicio y entrega los
resultados a las vistas.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable, Protocol, Sequence

from config.settings import ErrorConfiguracion
from controller.analysis import Comparacion, ResultadoBarrido, ResultadoEscenario
from controller.experiment_service import MODULO_PRUEBAS, ServicioExperimentos
from model.simulator import ResultadoReplica

if TYPE_CHECKING:
    from view.console_view import VistaConsola


class Exportador(Protocol):
    """Lo que la consola necesita para guardar resultados."""

    def escenarios(self, resultados: Sequence[ResultadoEscenario], comparacion: Comparacion | None) -> list[Path]: ...

    def barrido(self, barrido: ResultadoBarrido, ventana: float) -> list[Path]: ...

    def traza(self, nombre: str, replica: int, resultado: ResultadoReplica) -> list[Path]: ...

    def mostrar_graficas(self) -> str | None: ...


class Animador(Protocol):
    """Reproduce la traza de una réplica ya simulada."""

    def reproducir(self, nombre: str, replica: int, resultado: ResultadoReplica,
                   informar: Callable[[str], None]) -> None: ...


class ControladorConsola:
    """Acciones de la consola y menú interactivo."""

    def __init__(self, servicio: ServicioExperimentos, consola: VistaConsola, exportador: Exportador,
                 animador: Animador, lanzar_interfaz: Callable[[], str | None]) -> None:
        self._servicio = servicio
        self._consola = consola
        self._exportador = exportador
        self._animador = animador
        self._lanzar_interfaz = lanzar_interfaz

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def ejecutar_escenarios(self, nombres: Sequence[str]) -> list[ResultadoEscenario]:
        """Simula los escenarios indicados y presenta tablas, comparación, CSV y gráficas."""
        config = self._servicio.config
        escenarios = [config.escenario(nombre) for nombre in nombres]
        self._consola.configuracion(config)
        self._consola.titulo("Simulación")
        resultados = self._servicio.simular_escenarios(escenarios, self._consola.progreso)
        base = self._servicio.resultado_base(
            resultados, lambda nombre, n, segundos: self._consola.progreso(f"{nombre} (referencia)", n, segundos))
        self._presentar_escenarios(resultados, self._servicio.comparar(resultados, base))
        return resultados

    def ejecutar_todos(self) -> list[ResultadoEscenario]:
        return self.ejecutar_escenarios([e.nombre for e in self._servicio.config.escenarios])

    def ejecutar_barrido(self) -> ResultadoBarrido:
        """Barrido de g con λ y T fijos: Tabla I, Fig. 2 y Q̄/Wq frente a g/T."""
        config = self._servicio.config
        b = config.barrido
        self._consola.titulo(f"Barrido de g: λ = {b.lam:g} veh/s, T = {b.T:g} s, r = T − g")
        barrido = self._servicio.simular_barrido(self._consola.progreso)
        self._consola.barrido(barrido, config.simulacion.confianza)
        self._consola.archivos(self._exportador.barrido(barrido, b.ventana_grafica_s))
        self._mostrar_graficas()
        return barrido

    def mostrar_traza(self, nombre: str | None = None, replica: int | None = None) -> ResultadoReplica:
        """Traza de eventos de una réplica (limitada en pantalla, completa en CSV)."""
        config = self._servicio.config
        escenario = config.escenario(nombre or config.escenario_base)
        replica = replica or config.salida.replica_detalle
        resultado = self._servicio.simular_replica(escenario, replica)
        self._consola.traza(escenario.nombre, replica, resultado, config.salida.eventos_traza)
        self._consola.pendientes(resultado.metricas, resultado.parametros.H)
        self._consola.archivos(self._exportador.traza(escenario.nombre, replica, resultado))
        return resultado

    def animar(self, nombre: str | None = None) -> None:
        """Simula la réplica de detalle; luego la vista solo reproduce su traza."""
        config = self._servicio.config
        escenario = config.escenario(nombre or config.animacion.escenario)
        replica = config.salida.replica_detalle
        resultado = self._servicio.simular_replica(escenario, replica)
        self._animador.reproducir(escenario.nombre, replica, resultado, self._consola.mensaje)

    def ejecutar_pruebas(self) -> bool:
        """Ejecuta las pruebas de verificación y muestra OK o FALLÓ."""
        self._consola.titulo("Pruebas de verificación")
        try:
            resultados = self._servicio.correr_pruebas()
        except (ImportError, AttributeError) as error:
            self._consola.error(f"No se pudieron cargar las pruebas ({MODULO_PRUEBAS}): {error}")
            return False
        for r in resultados:
            self._consola.prueba(r.numero, r.descripcion, r.exito, r.detalle)
        exitos = sum(r.exito for r in resultados)
        self._consola.total_pruebas(exitos, len(resultados))
        return exitos == len(resultados)

    def abrir_interfaz(self) -> None:
        """Abre la interfaz gráfica; el control vuelve al cerrarla."""
        error = self._lanzar_interfaz()
        if error:
            self._consola.error(error)

    def _presentar_escenarios(self, resultados: Sequence[ResultadoEscenario], comparacion: Comparacion | None) -> None:
        config = self._servicio.config
        for resultado in resultados:
            self._consola.resumen(resultado, config.simulacion.confianza)
        self._consola.ciclos(resultados, config.salida.ciclos_mostrados)
        if comparacion is not None:
            self._consola.comparacion(comparacion)
        self._consola.archivos(self._exportador.escenarios(resultados, comparacion))
        self._mostrar_graficas()

    def _mostrar_graficas(self) -> None:
        aviso = self._exportador.mostrar_graficas()
        if aviso:
            self._consola.advertencia(aviso)

    # ------------------------------------------------------------------
    # Menú interactivo
    # ------------------------------------------------------------------
    def ejecutar_seguro(self, accion: Callable[[], object]) -> object | None:
        """Ejecuta una acción mostrando los errores de configuración sin cerrar el programa."""
        try:
            return accion()
        except ErrorConfiguracion as error:
            self._consola.error(str(error))
        except KeyboardInterrupt:
            self._consola.advertencia("Operación interrumpida.")
        return None

    def menu(self) -> None:
        opciones: dict[str, tuple[str, Callable[[], object]]] = {
            "1": ("Ejecutar pruebas de verificación", self.ejecutar_pruebas),
            "2": ("Ejecutar un escenario", self._menu_escenario),
            "3": ("Ejecutar todos los escenarios", self.ejecutar_todos),
            "4": ("Ejecutar el barrido de g (Tabla I y Fig. 2)", self.ejecutar_barrido),
            "5": ("Ver la traza de eventos de una réplica", self._menu_traza),
            "6": ("Ver la animación de la simulación de un escenario", self._menu_animacion),
            "7": ("Ver la configuración activa", lambda: self._consola.configuracion(self._servicio.config)),
            "8": ("Abrir la interfaz gráfica (escenarios y gráficas)", self.abrir_interfaz),
            "0": ("Salir", lambda: None),
        }
        while True:
            eleccion = self._consola.pedir_opcion({clave: texto for clave, (texto, _) in opciones.items()})
            if eleccion is None or eleccion == "0":
                self._consola.mensaje("Fin de la sesión.")
                return
            if eleccion not in opciones:
                self._consola.error("Opción no válida.")
                continue
            self.ejecutar_seguro(opciones[eleccion][1])

    def _nombres(self) -> list[str]:
        return [e.nombre for e in self._servicio.config.escenarios]

    def _menu_escenario(self) -> None:
        nombre = self._consola.elegir("Escenarios disponibles:", self._nombres())
        if nombre:
            self.ejecutar_escenarios([nombre])

    def _menu_traza(self) -> None:
        nombre = self._consola.elegir("¿De qué escenario?", self._nombres())
        if nombre is None:
            return
        replica = self._consola.pedir_entero("Réplica", self._servicio.config.salida.replica_detalle)
        if replica is not None:
            self.mostrar_traza(nombre, replica)

    def _menu_animacion(self) -> None:
        nombre = self._consola.elegir("¿Qué escenario animar?", self._nombres())
        if nombre:
            self.animar(nombre)

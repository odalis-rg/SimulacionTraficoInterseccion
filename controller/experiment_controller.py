"""Controlador de experimentos.

Orquesta escenarios, réplicas y semillas, las pruebas de verificación, el
barrido de g, la traza y la animación. Primero ejecuta el modelo y después
entrega los resultados ya calculados a las vistas (consola, interfaz gráfica,
CSV, gráficas y animación); ninguna vista modifica el modelo.

Los métodos de cálculo (``simular_*``, ``correr_pruebas``) no imprimen nada y
los usan tanto la consola como la interfaz gráfica.
"""

from __future__ import annotations

import importlib
import math
import time
from dataclasses import replace
from pathlib import Path
from typing import Callable, Sequence

from config.entorno import es_dependencia, explicar_dependencia_faltante
from config.settings import Configuracion, ErrorConfiguracion, Escenario
from controller.analysis import (
    AcumuladorEscenario,
    Comparacion,
    ResultadoBarrido,
    ResultadoEscenario,
    ResultadoPrueba,
    comparar_con_base,
)
from model.simulator import ResultadoReplica, Simulador
from model.statistics import INDICADORES_POR_CLAVE
from view.animation_view import VistaAnimacion
from view.console_view import VistaConsola
from view.csv_export import ExportadorCSV
from view.plots import GeneradorGraficas

MODULO_PRUEBAS = "tests.test_verification"
"""Módulo con la tupla ``PRUEBAS``; lo usan pytest, el menú y la interfaz gráfica."""

Progreso = Callable[[str, int, float], None]
"""Aviso al terminar un escenario: (nombre, réplicas, segundos)."""


def _descripcion(prueba: Callable[[], None]) -> str:
    """Primera línea del docstring de la prueba."""
    return (prueba.__doc__ or prueba.__name__).strip().splitlines()[0]


def _ejecutar_prueba(prueba: Callable[[], None]) -> tuple[bool, str]:
    try:
        prueba()
    except AssertionError as error:
        return False, str(error) or "aserción no cumplida"
    except Exception as error:  # noqa: BLE001 — cualquier fallo inesperado se informa como FALLÓ
        return False, f"{type(error).__name__}: {error}"
    return True, ""


class ControladorExperimentos:
    """Conecta la configuración, el modelo y las vistas."""

    def __init__(self, config: Configuracion) -> None:
        desconocidos = [c for c in config.salida.indicadores_comparacion if c not in INDICADORES_POR_CLAVE]
        if desconocidos:
            raise ErrorConfiguracion(
                f"Indicadores de comparación desconocidos: {', '.join(desconocidos)}. "
                f"Válidos: {', '.join(INDICADORES_POR_CLAVE)}."
            )
        self.config = config
        carpeta = Path(config.salida.carpeta)
        confianza = config.simulacion.confianza
        self.consola = VistaConsola()
        self.csv = ExportadorCSV(carpeta)
        self.graficas = GeneradorGraficas(carpeta, config.salida.guardar_graficas, config.salida.mostrar_graficas,
                                          confianza)
        self._graficas_archivo = GeneradorGraficas(carpeta, guardar=True, mostrar=False, confianza=confianza)
        self.animacion = VistaAnimacion(config.animacion, carpeta)

    # ------------------------------------------------------------------
    # Configuración en caliente (la usa la interfaz gráfica)
    # ------------------------------------------------------------------
    def configurar_simulacion(self, mu: float, H: float, n_replicas: int) -> None:
        """Cambia μ, H y n; lanza ``ErrorConfiguracion`` si algún valor no es válido."""
        simulacion = replace(self.config.simulacion, mu=mu, H=H, n_replicas=n_replicas)
        self.config = replace(self.config, simulacion=simulacion)

    def configurar_barrido(self, lam: float, T: float, valores_g: Sequence[float]) -> None:
        """Cambia λ, T y los g del barrido; lanza ``ErrorConfiguracion`` si no son válidos."""
        barrido = replace(self.config.barrido, lam=lam, T=T, valores_g=tuple(valores_g))
        self.config = replace(self.config, barrido=barrido)

    def agregar_escenario(self, nombre: str, lam: float, g: float, r: float) -> Escenario:
        """Agrega un escenario validado; lanza ``ErrorConfiguracion`` si no es válido o ya existe."""
        nombre = nombre.strip()
        if self.config.buscar_escenario(nombre) is not None:
            raise ErrorConfiguracion(f"Ya existe un escenario llamado '{nombre}'.")
        escenario = Escenario(nombre, lam, g, r)
        self.config = replace(self.config, escenarios=self.config.escenarios + (escenario,))
        return escenario

    # ------------------------------------------------------------------
    # Cálculo (sin presentación)
    # ------------------------------------------------------------------
    def simular_replica(self, escenario: Escenario, replica: int) -> ResultadoReplica:
        """Una réplica con su semilla registrada (semilla_base + i)."""
        sim = self.config.simulacion
        return Simulador(escenario.parametros(sim), sim.semilla(replica)).ejecutar()

    def simular_escenario(self, escenario: Escenario) -> ResultadoEscenario:
        """Las n réplicas del escenario, consolidadas para el análisis."""
        sim = self.config.simulacion
        parametros = escenario.parametros(sim)
        acumulador = AcumuladorEscenario(escenario, parametros, self.config.salida.replica_detalle)
        for replica in range(1, sim.n_replicas + 1):
            acumulador.agregar(replica, Simulador(parametros, sim.semilla(replica)).ejecutar())
        return acumulador.consolidar(sim.confianza)

    def simular_escenarios(self, escenarios: Sequence[Escenario], progreso: Progreso | None = None) -> list[ResultadoEscenario]:
        """Simula varios escenarios y avisa al terminar cada uno."""
        resultados = []
        for escenario in escenarios:
            inicio = time.perf_counter()
            resultados.append(self.simular_escenario(escenario))
            if progreso:
                progreso(escenario.nombre, self.config.simulacion.n_replicas, time.perf_counter() - inicio)
        return resultados

    def resultado_base(self, resultados: Sequence[ResultadoEscenario],
                       progreso: Progreso | None = None) -> ResultadoEscenario | None:
        """Resultado del escenario base; se simula si hace falta y hay escenarios con su misma λ."""
        base = self.config.escenario(self.config.escenario_base)
        for resultado in resultados:
            if resultado.escenario == base:
                return resultado
        if any(math.isclose(r.parametros.lam, base.lam) for r in resultados):
            return self.simular_escenarios([base], progreso)[0]
        return None

    def comparar(self, resultados: Sequence[ResultadoEscenario],
                 base: ResultadoEscenario | None) -> Comparacion | None:
        """Comparación porcentual frente a la base, o None si no hay nada que comparar."""
        if base is None:
            return None
        comparacion = comparar_con_base(resultados, base, self.config.salida.indicadores_comparacion)
        return comparacion if comparacion.filas or comparacion.no_comparables else None

    def simular_barrido(self, progreso: Progreso | None = None) -> ResultadoBarrido:
        """Barrido de g con λ y T fijos (r = T − g)."""
        b = self.config.barrido
        return ResultadoBarrido.desde(b.lam, b.T, self.simular_escenarios(b.escenarios(), progreso))

    def correr_pruebas(self) -> list[ResultadoPrueba]:
        """Ejecuta las pruebas de ``tests/test_verification.py`` y devuelve su resultado."""
        pruebas = importlib.import_module(MODULO_PRUEBAS).PRUEBAS
        return [ResultadoPrueba(i, _descripcion(p), *_ejecutar_prueba(p)) for i, p in enumerate(pruebas, start=1)]

    # ------------------------------------------------------------------
    # Exportación a output/
    # ------------------------------------------------------------------
    def exportar_escenarios(self, resultados: Sequence[ResultadoEscenario], comparacion: Comparacion | None,
                            desde_interfaz: bool = False) -> list[Path]:
        """Guarda CSV y gráficas de los escenarios; desde la interfaz siempre guarda las gráficas."""
        graficas = self._graficas_archivo if desde_interfaz else self.graficas
        rutas: list[Path | None] = [self.csv.resumen(resultados)]
        rutas += [self.csv.replicas(r) for r in resultados]
        rutas += [self.csv.ciclos(r.nombre, r.replica_detalle, r.detalle) for r in resultados]
        if comparacion is not None and comparacion.filas:
            rutas.append(self.csv.comparacion(resultados, comparacion))
        rutas += [
            graficas.cola_en_el_tiempo(resultados),
            graficas.barras_indicador(resultados, "q_media"),
            graficas.barras_indicador(resultados, "wq_media"),
            graficas.residual_por_ciclo(resultados),
            graficas.histograma_esperas(resultados),
        ]
        return [r for r in rutas if r is not None]

    def exportar_barrido(self, barrido: ResultadoBarrido, desde_interfaz: bool = False) -> list[Path]:
        """Guarda la Tabla I y sus dos figuras."""
        graficas = self._graficas_archivo if desde_interfaz else self.graficas
        rutas = [
            self.csv.barrido(barrido),
            graficas.colas_superpuestas(barrido, self.config.barrido.ventana_grafica_s),
            graficas.indicadores_vs_g(barrido),
        ]
        return [r for r in rutas if r is not None]

    # ------------------------------------------------------------------
    # Acciones de consola (menú y línea de comandos)
    # ------------------------------------------------------------------
    def ejecutar_escenarios(self, nombres: Sequence[str]) -> list[ResultadoEscenario]:
        """Simula los escenarios indicados y presenta tablas, comparación, CSV y gráficas."""
        escenarios = [self.config.escenario(nombre) for nombre in nombres]
        self.consola.configuracion(self.config)
        self.consola.titulo("Simulación")
        resultados = self.simular_escenarios(escenarios, self.consola.progreso)
        base = self.resultado_base(resultados, lambda n, k, s: self.consola.progreso(f"{n} (referencia)", k, s))
        comparacion = self.comparar(resultados, base)
        for resultado in resultados:
            self.consola.resumen(resultado, self.config.simulacion.confianza)
        self.consola.ciclos(resultados, self.config.salida.ciclos_mostrados)
        if comparacion is not None:
            self.consola.comparacion(comparacion)
        self.consola.archivos(self.exportar_escenarios(resultados, comparacion))
        self._mostrar_graficas()
        return resultados

    def ejecutar_todos(self) -> list[ResultadoEscenario]:
        return self.ejecutar_escenarios([e.nombre for e in self.config.escenarios])

    def ejecutar_barrido(self) -> ResultadoBarrido:
        """Barrido de g con λ y T fijos: Tabla I, Fig. 2 y Q̄/Wq frente a g/T."""
        b = self.config.barrido
        self.consola.titulo(f"Barrido de g: λ = {b.lam:g} veh/s, T = {b.T:g} s, r = T − g")
        barrido = self.simular_barrido(self.consola.progreso)
        self.consola.barrido(barrido, self.config.simulacion.confianza)
        self.consola.archivos(self.exportar_barrido(barrido))
        self._mostrar_graficas()
        return barrido

    def mostrar_traza(self, nombre: str | None = None, replica: int | None = None) -> ResultadoReplica:
        """Traza de eventos de una réplica (limitada en pantalla, completa en CSV)."""
        escenario = self.config.escenario(nombre or self.config.escenario_base)
        replica = replica or self.config.salida.replica_detalle
        resultado = self.simular_replica(escenario, replica)
        self.consola.traza(escenario.nombre, replica, resultado, self.config.salida.eventos_traza)
        self.consola.pendientes(resultado.metricas, resultado.parametros.H)
        self.consola.archivos([
            self.csv.traza(escenario.nombre, replica, resultado),
            self.csv.ciclos(escenario.nombre, replica, resultado),
        ])
        return resultado

    def animar(self, nombre: str | None = None) -> None:
        """Simula la réplica de detalle y luego la vista solo reproduce su traza."""
        escenario = self.config.escenario(nombre or self.config.animacion.escenario)
        replica = self.config.salida.replica_detalle
        resultado = self.simular_replica(escenario, replica)
        self.animacion.reproducir(escenario.nombre, replica, resultado, self.consola.mensaje)

    def ejecutar_pruebas(self) -> bool:
        """Ejecuta las pruebas de verificación y muestra OK o FALLÓ en consola."""
        self.consola.titulo("Pruebas de verificación")
        try:
            resultados = self.correr_pruebas()
        except (ImportError, AttributeError) as error:
            self.consola.error(f"No se pudieron cargar las pruebas ({MODULO_PRUEBAS}): {error}")
            return False
        for r in resultados:
            self.consola.prueba(r.numero, r.descripcion, r.exito, r.detalle)
        exitos = sum(r.exito for r in resultados)
        self.consola.total_pruebas(exitos, len(resultados))
        return exitos == len(resultados)

    def abrir_interfaz(self) -> None:
        """Abre la interfaz gráfica; el control vuelve al cerrarla."""
        try:
            from view.gui_view import abrir_interfaz  # Tkinter solo se carga si se usa la interfaz
        except ModuleNotFoundError as error:
            if not es_dependencia(error):
                raise
            self.consola.error(explicar_dependencia_faltante(error))
            return
        error = abrir_interfaz(self)
        if error:
            self.consola.error(error)

    def _mostrar_graficas(self) -> None:
        aviso = self.graficas.mostrar()
        if aviso:
            self.consola.advertencia(aviso)

    # ------------------------------------------------------------------
    # Menú interactivo
    # ------------------------------------------------------------------
    def ejecutar_seguro(self, accion: Callable[[], object]) -> object | None:
        """Ejecuta una acción mostrando los errores de configuración sin cerrar el programa."""
        try:
            return accion()
        except ErrorConfiguracion as error:
            self.consola.error(str(error))
        except KeyboardInterrupt:
            self.consola.advertencia("Operación interrumpida.")
        return None

    def menu(self) -> None:
        opciones: dict[str, tuple[str, Callable[[], object]]] = {
            "1": ("Ejecutar pruebas de verificación", self.ejecutar_pruebas),
            "2": ("Ejecutar un escenario", self._menu_escenario),
            "3": ("Ejecutar todos los escenarios", self.ejecutar_todos),
            "4": ("Ejecutar el barrido de g (Tabla I y Fig. 2)", self.ejecutar_barrido),
            "5": ("Ver la traza de eventos de una réplica", self._menu_traza),
            "6": ("Ver la animación de la simulación de un escenario", self._menu_animacion),
            "7": ("Ver la configuración activa", lambda: self.consola.configuracion(self.config)),
            "8": ("Abrir la interfaz gráfica (escenarios y gráficas)", self.abrir_interfaz),
            "0": ("Salir", lambda: None),
        }
        while True:
            eleccion = self.consola.pedir_opcion({clave: texto for clave, (texto, _) in opciones.items()})
            if eleccion is None or eleccion == "0":
                self.consola.mensaje("Fin de la sesión.")
                return
            if eleccion not in opciones:
                self.consola.error("Opción no válida.")
                continue
            self.ejecutar_seguro(opciones[eleccion][1])

    def _nombres(self) -> list[str]:
        return [e.nombre for e in self.config.escenarios]

    def _menu_escenario(self) -> None:
        nombre = self.consola.elegir("Escenarios disponibles:", self._nombres())
        if nombre:
            self.ejecutar_escenarios([nombre])

    def _menu_traza(self) -> None:
        nombre = self.consola.elegir("¿De qué escenario?", self._nombres())
        if nombre is None:
            return
        replica = self.consola.pedir_entero("Réplica", self.config.salida.replica_detalle)
        if replica is not None:
            self.mostrar_traza(nombre, replica)

    def _menu_animacion(self) -> None:
        nombre = self.consola.elegir("¿Qué escenario animar?", self._nombres())
        if nombre:
            self.animar(nombre)

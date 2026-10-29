"""Motor de simulación de eventos discretos de un acceso semaforizado.

Reglas del modelo (una cola FIFO ilimitada y un servidor):

* Llegadas Poisson homogéneas (intervalos exponenciales de media 1/λ).
* En rojo no se atiende; en verde, un servicio determinista dura 1/μ s y solo
  comienza si termina antes o exactamente al final del verde.
* La simulación arranca en t = 0 al inicio de un rojo, con la cola vacía y el
  servidor libre, sin período de calentamiento.
* No se programa ningún evento posterior al horizonte H. Si un servicio
  iniciado no alcanza a terminar antes de H, el vehículo queda en servicio y
  se reporta como pendiente.
* Eventos simultáneos: salida, luego cambio de fase y luego llegada
  (ver ``model/events.py``).

Aleatoriedad: las llegadas vienen de un ``ProcesoLlegadas`` inyectado (por
defecto ``LlegadasPoisson``, con un generador dedicado solo a las llegadas).
Como ninguna otra parte del modelo consume números aleatorios, la misma
semilla produce el mismo flujo de llegadas aunque cambien g o r (números
aleatorios comunes). Así, al comparar configuraciones, las diferencias se
deben a los tiempos de fase y no al ruido de muestreo, y la misma
configuración con la misma semilla reproduce la misma traza y las mismas
métricas.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from config.settings import ParametrosModelo
from model.arrivals import LlegadasPoisson, ProcesoLlegadas
from model.events import AgendaEventos, Evento, RegistroTraza, TipoEvento
from model.statistics import ContadorCiclos, MetricasReplica, RegistroCiclo, calcular_metricas
from model.traffic_light import Fase, IntervaloFase, Semaforo
from model.vehicle import Vehiculo

TOLERANCIA_TIEMPO = 1e-9
"""Holgura (s) al comparar instantes en punto flotante, p. ej. fin de servicio = fin de verde."""


def _dentro_de(t: float, limite: float) -> float | None:
    """``t`` si no supera ``limite`` (recortado a él si lo excede solo por redondeo); si no, None."""
    if t > limite + TOLERANCIA_TIEMPO:
        return None
    return min(t, limite)


@dataclass(frozen=True)
class ResultadoReplica:
    """Salida completa de una réplica: traza, vehículos, ciclos, fases y métricas."""

    parametros: ParametrosModelo
    semilla: int
    traza: tuple[RegistroTraza, ...]
    vehiculos: tuple[Vehiculo, ...]
    ciclos: tuple[RegistroCiclo, ...]
    fases: tuple[IntervaloFase, ...]
    metricas: MetricasReplica


class Simulador:
    """Simula una réplica del acceso semaforizado. Cada instancia se ejecuta una vez.

    ``llegadas`` permite inyectar otro proceso de llegadas; por defecto son de
    Poisson con tasa λ y la semilla de la réplica.
    """

    def __init__(self, parametros: ParametrosModelo, semilla: int, llegadas: ProcesoLlegadas | None = None) -> None:
        self._p = parametros
        self._semilla = semilla
        self._llegadas = llegadas if llegadas is not None else LlegadasPoisson(parametros.lam, semilla)
        self._agenda = AgendaEventos()
        self._semaforo = Semaforo(parametros)
        self._ciclos = ContadorCiclos()
        self._cola: deque[Vehiculo] = deque()
        self._en_servicio: Vehiculo | None = None
        self._vehiculos: list[Vehiculo] = []
        self._traza: list[RegistroTraza] = []
        self._fases: list[IntervaloFase] = []

    def ejecutar(self) -> ResultadoReplica:
        """Procesa la agenda en orden cronológico hasta agotar los eventos de [0, H]."""
        self._iniciar_fase()
        self._programar_llegada(desde=0.0)
        while self._agenda:
            evento = self._agenda.extraer()
            vehiculo_id = self._procesar(evento)
            self._intentar_iniciar_servicio(evento.tiempo)
            self._registrar(evento, vehiculo_id)
        metricas = calcular_metricas(self._traza, self._vehiculos, self._ciclos.ciclos, self._p.H)
        return ResultadoReplica(
            parametros=self._p,
            semilla=self._semilla,
            traza=tuple(self._traza),
            vehiculos=tuple(self._vehiculos),
            ciclos=tuple(self._ciclos.ciclos),
            fases=tuple(self._fases),
            metricas=metricas,
        )

    # ------------------------------------------------------------------
    # Programación de eventos
    # ------------------------------------------------------------------
    def _programar_llegada(self, desde: float) -> None:
        """Programa la siguiente llegada del proceso si cae dentro del horizonte."""
        siguiente = self._llegadas.siguiente(desde)
        t = None if siguiente is None else _dentro_de(siguiente, self._p.H)
        if t is not None:
            self._agenda.programar(t, TipoEvento.LLEGADA)

    def _iniciar_fase(self) -> None:
        """Registra la fase vigente y programa su final si ocurre dentro de H."""
        intervalo = self._semaforo.intervalo_actual()
        self._fases.append(intervalo)
        fin = _dentro_de(intervalo.fin, self._p.H)
        if fin is not None:
            self._agenda.programar(fin, TipoEvento.CAMBIO_FASE)

    # ------------------------------------------------------------------
    # Procesamiento de eventos
    # ------------------------------------------------------------------
    def _procesar(self, evento: Evento) -> int | None:
        """Aplica el evento al estado; devuelve el id del vehículo involucrado."""
        if evento.tipo is TipoEvento.SALIDA:
            return self._procesar_salida(evento)
        if evento.tipo is TipoEvento.CAMBIO_FASE:
            self._procesar_cambio_fase()
            return None
        return self._procesar_llegada(evento.tiempo)

    def _procesar_llegada(self, t: float) -> int:
        """El vehículo entra al final de la cola y se programa la llegada siguiente."""
        vehiculo = Vehiculo(id=len(self._vehiculos) + 1, t_llegada=t)
        self._vehiculos.append(vehiculo)
        self._cola.append(vehiculo)
        self._programar_llegada(desde=t)
        return vehiculo.id

    def _procesar_salida(self, evento: Evento) -> int:
        """El vehículo en servicio sale, se libera el servidor y se cuenta en el ciclo."""
        vehiculo = self._en_servicio
        assert vehiculo is not None and vehiculo.id == evento.vehiculo_id, "Salida sin vehículo en servicio"
        vehiculo.t_salida = evento.tiempo
        self._en_servicio = None
        self._ciclos.registrar_salida(self._semaforo.ciclo)
        return vehiculo.id

    def _procesar_cambio_fase(self) -> None:
        """Al terminar un verde registra atendidos y cola residual; luego cambia la fase."""
        if self._semaforo.fase is Fase.VERDE:
            verde = self._semaforo.intervalo_actual()
            self._ciclos.registrar_fin_verde(verde.ciclo, verde.inicio, verde.fin, len(self._cola))
        self._semaforo.cambiar_fase()
        self._iniciar_fase()

    def _intentar_iniciar_servicio(self, t: float) -> None:
        """Inicia el servicio del primero de la cola si hay verde, servidor libre y
        el servicio termina dentro del verde. La salida solo se programa si ocurre
        dentro de H."""
        if self._semaforo.fase is not Fase.VERDE or self._en_servicio is not None or not self._cola:
            return
        fin_servicio = _dentro_de(t + self._p.tiempo_servicio, self._semaforo.fin_fase_actual())
        if fin_servicio is None:
            return
        vehiculo = self._cola.popleft()
        vehiculo.t_inicio_servicio = t
        self._en_servicio = vehiculo
        salida = _dentro_de(fin_servicio, self._p.H)
        if salida is not None:
            self._agenda.programar(salida, TipoEvento.SALIDA, vehiculo.id)

    def _registrar(self, evento: Evento, vehiculo_id: int | None) -> None:
        """Agrega a la traza el evento y el estado resultante (Q(t) sin el que está en servicio)."""
        self._traza.append(
            RegistroTraza(
                tiempo=evento.tiempo,
                tipo=evento.tipo,
                vehiculo_id=vehiculo_id,
                fase=self._semaforo.fase,
                cola=len(self._cola),
                en_servicio=self._en_servicio.id if self._en_servicio else None,
                ciclo=self._semaforo.ciclo,
            )
        )

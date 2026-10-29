"""Configuración del simulador.

Contiene las dataclasses de configuración (con los valores por defecto del
informe), la carga desde ``config.json`` y todas las validaciones de entrada.
La sobrescritura con argumentos de línea de comandos está en
``controller/cli.py``. Cualquier parámetro fuera de su dominio lanza
``ErrorConfiguracion`` con un mensaje claro.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Mapping


class ErrorConfiguracion(ValueError):
    """Parámetro de configuración inválido o inexistente."""


# ---------------------------------------------------------------------------
# Validaciones elementales
# ---------------------------------------------------------------------------
def _exigir(condicion: bool, mensaje: str) -> None:
    """Lanza ``ErrorConfiguracion`` con ``mensaje`` si la condición es falsa."""
    if not condicion:
        raise ErrorConfiguracion(mensaje)


def _es_real(valor: Any) -> bool:
    """True si ``valor`` es un número real finito (los booleanos no cuentan)."""
    return isinstance(valor, (int, float)) and not isinstance(valor, bool) and math.isfinite(valor)


def _exigir_positivo(nombre: str, valor: Any, *, admite_cero: bool = False) -> None:
    """Exige un real finito > 0 (o ≥ 0 si ``admite_cero``)."""
    cota = "≥ 0" if admite_cero else "> 0"
    valido = _es_real(valor) and (valor >= 0 if admite_cero else valor > 0)
    _exigir(valido, f"{nombre} debe ser un número {cota} (recibido: {valor!r}).")


def _exigir_entero(nombre: str, valor: Any, minimo: int) -> None:
    """Exige un entero ≥ ``minimo``."""
    valido = isinstance(valor, int) and not isinstance(valor, bool) and valor >= minimo
    _exigir(valido, f"{nombre} debe ser un entero ≥ {minimo} (recibido: {valor!r}).")


def _exigir_booleano(nombre: str, valor: Any) -> None:
    """Exige un valor true/false."""
    _exigir(isinstance(valor, bool), f"{nombre} debe ser true o false (recibido: {valor!r}).")


def _exigir_texto(nombre: str, valor: Any) -> None:
    """Exige una cadena no vacía."""
    _exigir(isinstance(valor, str) and valor.strip() != "", f"{nombre} debe ser un texto no vacío.")


# ---------------------------------------------------------------------------
# Parámetros del modelo y escenarios
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ParametrosModelo:
    """Parámetros de una corrida del modelo de un acceso; se validan al crearse.

    Attributes:
        lam: Tasa de llegada λ (veh/s); con λ = 0 no hay llegadas.
        g: Duración del verde (s).
        r: Duración del rojo (s).
        mu: Tasa de servicio en verde μ (veh/s): un vehículo cada 1/μ s.
        H: Horizonte de simulación (s).
    """

    lam: float
    g: float
    r: float
    mu: float
    H: float

    def __post_init__(self) -> None:
        _exigir_positivo("λ (tasa de llegada)", self.lam, admite_cero=True)
        _exigir_positivo("g (duración del verde)", self.g)
        _exigir_positivo("r (duración del rojo)", self.r)
        _exigir_positivo("μ (tasa de servicio)", self.mu)
        _exigir_positivo("H (horizonte)", self.H)
        for nombre in ("lam", "g", "r", "mu", "H"):  # enteros del JSON → float uniforme
            object.__setattr__(self, nombre, float(getattr(self, nombre)))

    @property
    def T(self) -> float:
        """Duración del ciclo, T = g + r (s)."""
        return self.g + self.r

    @property
    def tiempo_servicio(self) -> float:
        """Duración determinista de un servicio, 1/μ (s)."""
        return 1.0 / self.mu

    @property
    def fraccion_verde(self) -> float:
        """Fracción del ciclo en verde, g/T."""
        return self.g / self.T


@dataclass(frozen=True)
class Escenario:
    """Escenario de demanda y tiempos de fase (λ en veh/s; g y r en s)."""

    nombre: str
    lam: float
    g: float
    r: float

    def parametros(self, simulacion: ConfigSimulacion) -> ParametrosModelo:
        """Combina el escenario con μ y H; valida todos los parámetros del modelo."""
        try:
            return ParametrosModelo(self.lam, self.g, self.r, simulacion.mu, simulacion.H)
        except ErrorConfiguracion as error:
            raise ErrorConfiguracion(f"Escenario '{self.nombre}': {error}") from None


ESCENARIOS_INFORME: tuple[Escenario, ...] = (
    Escenario("Base", 0.15, 30.0, 30.0),
    Escenario("Verde corto", 0.15, 20.0, 40.0),
    Escenario("Verde largo", 0.15, 40.0, 20.0),
    Escenario("Demanda alta", 0.25, 30.0, 30.0),
    Escenario("Sobresaturado", 0.35, 30.0, 30.0),
)


# ---------------------------------------------------------------------------
# Secciones de la configuración
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ConfigSimulacion:
    """Parámetros comunes a todas las corridas (diseño experimental del informe)."""

    mu: float = 0.5
    H: float = 3600.0
    n_replicas: int = 30
    semilla_base: int = 2025
    confianza: float = 0.95

    def semilla(self, replica: int) -> int:
        """Semilla registrada de la réplica i (i = 1..n): semilla_base + i."""
        return self.semilla_base + replica

    def validar(self) -> None:
        _exigir_positivo("μ (tasa de servicio)", self.mu)
        _exigir_positivo("H (horizonte)", self.H)
        _exigir_entero("n (número de réplicas)", self.n_replicas, 2)
        _exigir_entero("semilla_base", self.semilla_base, 0)
        _exigir(
            _es_real(self.confianza) and 0 < self.confianza < 1,
            f"confianza debe estar en (0, 1) (recibido: {self.confianza!r}).",
        )


@dataclass(frozen=True)
class ConfigBarrido:
    """Barrido de g con λ y T fijos (r = T − g). Alimenta la Tabla I y la Fig. 2."""

    lam: float = 0.15
    T: float = 60.0
    valores_g: tuple[float, ...] = (10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0)
    ventana_grafica_s: float = 600.0

    def escenarios(self) -> tuple[Escenario, ...]:
        """Un escenario por cada g probado, con r = T − g."""
        return tuple(Escenario(f"g={g:g}", self.lam, g, self.T - g) for g in self.valores_g)

    def validar(self) -> None:
        _exigir_positivo("barrido.lam", self.lam, admite_cero=True)
        _exigir_positivo("barrido.T", self.T)
        _exigir_positivo("barrido.ventana_grafica_s", self.ventana_grafica_s)
        _exigir(len(self.valores_g) > 0, "barrido.valores_g no puede estar vacío.")
        _exigir(len(set(self.valores_g)) == len(self.valores_g), "barrido.valores_g no admite repetidos.")
        for g in self.valores_g:
            _exigir(
                _es_real(g) and 0 < g < self.T,
                f"Cada g del barrido debe cumplir 0 < g < T = {self.T:g} s para que r > 0 (recibido: {g!r}).",
            )


@dataclass(frozen=True)
class ConfigSalida:
    """Opciones de presentación y archivos generados."""

    carpeta: str = "output"
    eventos_traza: int = 40
    ciclos_mostrados: int = 20
    replica_detalle: int = 1
    guardar_graficas: bool = True
    mostrar_graficas: bool = False
    indicadores_comparacion: tuple[str, ...] = ("q_media", "q_max", "wq_media", "w_media", "residual_medio")

    def validar(self, simulacion: ConfigSimulacion) -> None:
        _exigir_texto("salida.carpeta", self.carpeta)
        _exigir_entero("salida.eventos_traza", self.eventos_traza, 1)
        _exigir_entero("salida.ciclos_mostrados", self.ciclos_mostrados, 1)
        _exigir_entero("salida.replica_detalle", self.replica_detalle, 1)
        _exigir(
            self.replica_detalle <= simulacion.n_replicas,
            f"salida.replica_detalle ({self.replica_detalle}) no puede superar n = {simulacion.n_replicas}.",
        )
        _exigir_booleano("salida.guardar_graficas", self.guardar_graficas)
        _exigir_booleano("salida.mostrar_graficas", self.mostrar_graficas)
        _exigir(len(self.indicadores_comparacion) > 0, "salida.indicadores_comparacion no puede estar vacío.")


@dataclass(frozen=True)
class ConfigAnimacion:
    """Parámetros de la vista animada (reproduce la traza de la réplica de detalle)."""

    escenario: str = "Base"
    ventana_s: float = 300.0
    velocidad: float = 6.0
    fps: int = 20
    max_vehiculos_fila: int = 10
    duracion_transicion_s: float = 1.2
    guardar_gif: bool = False
    fps_gif: int = 10
    dpi_gif: int = 80

    def validar(self) -> None:
        _exigir_texto("animacion.escenario", self.escenario)
        _exigir_positivo("animacion.ventana_s", self.ventana_s)
        _exigir_positivo("animacion.velocidad (s simulados por s real)", self.velocidad)
        _exigir_entero("animacion.fps", self.fps, 1)
        _exigir_entero("animacion.max_vehiculos_fila", self.max_vehiculos_fila, 1)
        _exigir_positivo("animacion.duracion_transicion_s", self.duracion_transicion_s)
        _exigir_booleano("animacion.guardar_gif", self.guardar_gif)
        _exigir_entero("animacion.fps_gif", self.fps_gif, 1)
        _exigir_entero("animacion.dpi_gif", self.dpi_gif, 1)


@dataclass(frozen=True)
class Configuracion:
    """Configuración completa. Se valida al crearse y en cada ``replace``."""

    simulacion: ConfigSimulacion = field(default_factory=ConfigSimulacion)
    escenarios: tuple[Escenario, ...] = ESCENARIOS_INFORME
    escenario_base: str = "Base"
    barrido: ConfigBarrido = field(default_factory=ConfigBarrido)
    salida: ConfigSalida = field(default_factory=ConfigSalida)
    animacion: ConfigAnimacion = field(default_factory=ConfigAnimacion)

    def __post_init__(self) -> None:
        self.validar()

    def buscar_escenario(self, nombre: str) -> Escenario | None:
        """Escenario por nombre (sin distinguir mayúsculas) o None si no existe."""
        clave = nombre.strip().casefold()
        return next((e for e in self.escenarios if e.nombre.strip().casefold() == clave), None)

    def escenario(self, nombre: str) -> Escenario:
        """Escenario por nombre; lanza ``ErrorConfiguracion`` si no existe."""
        encontrado = self.buscar_escenario(nombre)
        if encontrado is None:
            disponibles = ", ".join(e.nombre for e in self.escenarios)
            raise ErrorConfiguracion(f"No existe el escenario '{nombre}'. Disponibles: {disponibles}.")
        return encontrado

    def validar(self) -> None:
        self.simulacion.validar()
        _exigir(len(self.escenarios) > 0, "Debe definirse al menos un escenario.")
        for escenario in self.escenarios:
            _exigir_texto("El nombre de cada escenario", escenario.nombre)
            escenario.parametros(self.simulacion)
        nombres = [e.nombre.strip().casefold() for e in self.escenarios]
        _exigir(len(set(nombres)) == len(nombres), "Los nombres de escenario deben ser únicos.")
        _exigir_texto("escenario_base", self.escenario_base)
        self.escenario(self.escenario_base)
        self.barrido.validar()
        self.salida.validar(self.simulacion)
        self.animacion.validar()
        self.escenario(self.animacion.escenario)


# ---------------------------------------------------------------------------
# Carga desde JSON
# ---------------------------------------------------------------------------
_SECCIONES: dict[str, type] = {
    "simulacion": ConfigSimulacion,
    "barrido": ConfigBarrido,
    "salida": ConfigSalida,
    "animacion": ConfigAnimacion,
}


def _sin_comentarios(datos: Mapping[str, Any]) -> dict[str, Any]:
    """Descarta las claves que empiezan con '_' (comentarios dentro del JSON)."""
    return {clave: valor for clave, valor in datos.items() if not clave.startswith("_")}


def _crear(clase: type, datos: Any, seccion: str) -> Any:
    """Instancia una dataclass desde un objeto JSON, rechazando claves desconocidas."""
    _exigir(isinstance(datos, Mapping), f"La sección '{seccion}' debe ser un objeto JSON.")
    datos = _sin_comentarios(datos)
    validas = {campo.name for campo in fields(clase)}
    desconocidas = sorted(set(datos) - validas)
    _exigir(
        not desconocidas,
        f"Claves desconocidas en '{seccion}': {', '.join(desconocidas)}. Válidas: {', '.join(sorted(validas))}.",
    )
    try:
        return clase(**{k: tuple(v) if isinstance(v, list) else v for k, v in datos.items()})
    except TypeError as error:
        raise ErrorConfiguracion(f"Sección '{seccion}' incompleta o inválida: {error}") from None


def desde_diccionario(datos: Mapping[str, Any]) -> Configuracion:
    """Construye y valida la configuración a partir del contenido de ``config.json``."""
    _exigir(isinstance(datos, Mapping), "config.json debe contener un objeto JSON.")
    datos = _sin_comentarios(datos)
    validas = set(_SECCIONES) | {"escenarios", "escenario_base"}
    desconocidas = sorted(set(datos) - validas)
    _exigir(not desconocidas, f"Secciones desconocidas en config.json: {', '.join(desconocidas)}.")
    argumentos: dict[str, Any] = {
        nombre: _crear(clase, datos.get(nombre, {}), nombre) for nombre, clase in _SECCIONES.items()
    }
    if "escenarios" in datos:
        _exigir(isinstance(datos["escenarios"], list), "'escenarios' debe ser una lista.")
        argumentos["escenarios"] = tuple(_crear(Escenario, e, "escenarios") for e in datos["escenarios"])
    if "escenario_base" in datos:
        argumentos["escenario_base"] = datos["escenario_base"]
    return Configuracion(**argumentos)


def cargar_configuracion(ruta: Path) -> Configuracion:
    """Lee ``config.json``; lanza ``ErrorConfiguracion`` si falta o está mal formado."""
    try:
        contenido = json.loads(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ErrorConfiguracion(f"No se encontró el archivo de configuración: {ruta}") from None
    except json.JSONDecodeError as error:
        raise ErrorConfiguracion(
            f"{ruta.name} está mal formado (línea {error.lineno}, columna {error.colno}): {error.msg}"
        ) from None
    return desde_diccionario(contenido)

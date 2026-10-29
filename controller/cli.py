"""Línea de comandos: opciones, sobrescritura de la configuración y acciones pedidas.

Solo traduce argumentos; no simula ni presenta. No importa numpy, scipy ni
matplotlib, para que ``main.py`` pueda revisar el entorno antes de cargarlos.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Mapping

from config.settings import Configuracion

if TYPE_CHECKING:
    from controller.console_controller import ControladorConsola

ARGUMENTOS_CONFIGURACION: dict[str, tuple[str, str]] = {
    "mu": ("simulacion", "mu"),
    "H": ("simulacion", "H"),
    "replicas": ("simulacion", "n_replicas"),
    "semilla": ("simulacion", "semilla_base"),
    "confianza": ("simulacion", "confianza"),
    "barrido_lam": ("barrido", "lam"),
    "barrido_T": ("barrido", "T"),
    "barrido_g": ("barrido", "valores_g"),
    "carpeta_salida": ("salida", "carpeta"),
    "eventos": ("salida", "eventos_traza"),
    "ciclos": ("salida", "ciclos_mostrados"),
    "replica": ("salida", "replica_detalle"),
    "guardar_graficas": ("salida", "guardar_graficas"),
    "mostrar_graficas": ("salida", "mostrar_graficas"),
    "ventana": ("animacion", "ventana_s"),
    "velocidad": ("animacion", "velocidad"),
    "fps": ("animacion", "fps"),
    "max_fila": ("animacion", "max_vehiculos_fila"),
    "transicion": ("animacion", "duracion_transicion_s"),
    "gif": ("animacion", "guardar_gif"),
}
"""Argumento (``dest`` de argparse) → (sección, campo) de la configuración que sobrescribe."""


def crear_parser(ruta_config: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Simulación de eventos discretos de un acceso semaforizado (una cola, un servidor).",
        epilog="Los argumentos sobrescriben config.json solo durante esta ejecución.",
    )
    acciones = parser.add_argument_group("acciones (en este orden; después se abre el menú salvo --no-menu o --gui)")
    acciones.add_argument("--gui", "--interfaz", dest="gui", action="store_true",
                          help="abrir la interfaz gráfica interactiva (al cerrarla termina el programa)")
    acciones.add_argument("--pruebas", action="store_true", help="ejecutar las pruebas de verificación")
    acciones.add_argument("--escenario", metavar="NOMBRE",
                          help="ejecutar un escenario; también es el destino de --lam/--g/--r (si no existe, se crea)")
    acciones.add_argument("--all", "--todos", dest="todos", action="store_true", help="ejecutar todos los escenarios")
    acciones.add_argument("--barrido", action="store_true", help="ejecutar el barrido de g (Tabla I y Fig. 2)")
    acciones.add_argument("--traza", nargs="?", const="", metavar="NOMBRE",
                          help="mostrar la traza de eventos de una réplica (por defecto, el escenario base)")
    acciones.add_argument("--animate", "--animar", dest="animar", nargs="?", const="", metavar="NOMBRE",
                          help="ver la animación de un escenario (por defecto, animacion.escenario)")
    acciones.add_argument("--no-menu", action="store_true", help="no abrir el menú interactivo")

    modelo = parser.add_argument_group("modelo y réplicas")
    modelo.add_argument("--config", type=Path, default=ruta_config, help="archivo de configuración JSON")
    modelo.add_argument("--lam", type=float, help="tasa de llegada λ (veh/s) del escenario indicado")
    modelo.add_argument("--g", type=float, help="duración del verde g (s) del escenario indicado")
    modelo.add_argument("--r", type=float, help="duración del rojo r (s) del escenario indicado")
    modelo.add_argument("--mu", type=float, help="tasa de servicio en verde μ (veh/s)")
    modelo.add_argument("--H", type=float, help="horizonte de simulación H (s)")
    modelo.add_argument("-n", "--replicas", type=int, help="número de réplicas n (≥ 2)")
    modelo.add_argument("--semilla", type=int, help="semilla base: la réplica i usa semilla + i")
    modelo.add_argument("--confianza", type=float, help="nivel de confianza del IC, p. ej. 0.95")

    barrido = parser.add_argument_group("barrido de g")
    barrido.add_argument("--barrido-lam", type=float, help="λ fija del barrido (veh/s)")
    barrido.add_argument("--barrido-T", type=float, help="ciclo T fijo del barrido (s)")
    barrido.add_argument("--barrido-g", type=float, nargs="+", metavar="G", help="valores de g a probar (s)")

    salida = parser.add_argument_group("salida")
    salida.add_argument("--salida", dest="carpeta_salida", metavar="CARPETA", help="carpeta de resultados")
    salida.add_argument("--eventos", type=int, help="eventos de la traza que se muestran en consola")
    salida.add_argument("--ciclos", type=int, help="ciclos que se muestran en la tabla por ciclo")
    salida.add_argument("--replica", type=int, help="réplica de detalle (traza, ciclos, Q(t) y animación)")
    salida.add_argument("--mostrar", dest="mostrar_graficas", action="store_const", const=True,
                        help="mostrar las gráficas en pantalla")
    salida.add_argument("--no-guardar", dest="guardar_graficas", action="store_const", const=False,
                        help="no guardar las gráficas PNG")

    animacion = parser.add_argument_group("animación")
    animacion.add_argument("--ventana", type=float, help="segundos simulados que se reproducen")
    animacion.add_argument("--velocidad", type=float, help="segundos simulados por segundo real")
    animacion.add_argument("--fps", type=int, help="fotogramas por segundo")
    animacion.add_argument("--max-fila", type=int, help="máximo de vehículos dibujados en la fila")
    animacion.add_argument("--transicion", type=float, help="duración (s simulados) de entradas y salidas")
    animacion.add_argument("--gif", action="store_const", const=True, help="guardar la animación como GIF")
    return parser


def _con_escenario(config: Configuracion, nombre: str | None, cambios: dict[str, float]) -> Configuracion:
    """Aplica λ, g y r al escenario ``nombre`` (por defecto, el base).

    Si el escenario no existe, se crea copiando el base y aplicando los cambios.
    """
    if not cambios:
        return config
    objetivo = config.buscar_escenario(nombre or config.escenario_base)
    if objetivo is None:
        nuevo = replace(config.escenario(config.escenario_base), nombre=nombre.strip(), **cambios)
        return replace(config, escenarios=config.escenarios + (nuevo,))
    escenarios = tuple(replace(e, **cambios) if e is objetivo else e for e in config.escenarios)
    return replace(config, escenarios=escenarios)


def aplicar_argumentos(config: Configuracion, argumentos: Mapping[str, Any]) -> Configuracion:
    """Devuelve la configuración con los argumentos distintos de None aplicados (se valida al crearse)."""
    cambios: dict[str, dict[str, Any]] = {}
    for argumento, (seccion, campo) in ARGUMENTOS_CONFIGURACION.items():
        valor = argumentos.get(argumento)
        if valor is not None:
            cambios.setdefault(seccion, {})[campo] = tuple(valor) if isinstance(valor, list) else valor
    if cambios:
        config = replace(config, **{s: replace(getattr(config, s), **c) for s, c in cambios.items()})
    valores_escenario = {k: argumentos[k] for k in ("lam", "g", "r") if argumentos.get(k) is not None}
    config = _con_escenario(config, argumentos.get("escenario"), valores_escenario)
    if argumentos.get("animar"):
        config = replace(config, animacion=replace(config.animacion, escenario=argumentos["animar"]))
    return config


def acciones(args: argparse.Namespace, controlador: ControladorConsola) -> list[Callable[[], object]]:
    """Acciones pedidas por línea de comandos, en orden de ejecución."""
    pedidas: list[Callable[[], object]] = []
    if args.pruebas:
        pedidas.append(controlador.ejecutar_pruebas)
    if args.todos:
        pedidas.append(controlador.ejecutar_todos)
    elif args.escenario:
        pedidas.append(lambda: controlador.ejecutar_escenarios([args.escenario]))
    if args.barrido:
        pedidas.append(controlador.ejecutar_barrido)
    if args.traza is not None:
        pedidas.append(lambda: controlador.mostrar_traza(args.traza or args.escenario))
    if args.animar is not None:
        pedidas.append(controlador.animar)
    if args.gui:
        pedidas.append(controlador.abrir_interfaz)
    return pedidas

"""Punto de entrada: lee config.json, aplica los argumentos de línea de comandos y
arranca el controlador (acciones directas y/o menú interactivo).

Ejemplos:
    python main.py --gui                    # interfaz gráfica (escenarios, tablas y gráficas)
    python main.py                          # menú interactivo en consola
    python main.py --all --no-menu          # todos los escenarios y salir
    python main.py --animate Base           # animación del escenario Base y luego el menú
    python main.py --barrido --barrido-g 20 25 30 35 40 --no-menu
    python main.py --escenario Prueba --lam 0.2 --g 25 --r 35 --no-menu

Antes de cargar numpy, scipy y matplotlib se revisa el entorno: dentro de un
sandbox Flatpak (terminal de VS Code Flatpak) el programa se relanza en el
sistema, y si falta un paquete se explica cómo instalarlo.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Sequence

from config.entorno import es_dependencia, explicar_dependencia_faltante, relanzar_fuera_del_sandbox
from config.settings import Configuracion, ErrorConfiguracion, aplicar_argumentos, cargar_configuracion

if TYPE_CHECKING:
    from controller.experiment_controller import ControladorExperimentos

RAIZ = Path(__file__).resolve().parent
RUTA_CONFIG = RAIZ / "config" / "config.json"


def crear_parser() -> argparse.ArgumentParser:
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
    modelo.add_argument("--config", type=Path, default=RUTA_CONFIG, help="archivo de configuración JSON")
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


def _con_salida_absoluta(config: Configuracion) -> Configuracion:
    """Una carpeta de salida relativa se interpreta respecto de la carpeta del proyecto."""
    carpeta = Path(config.salida.carpeta)
    if carpeta.is_absolute():
        return config
    return replace(config, salida=replace(config.salida, carpeta=str(RAIZ / carpeta)))


def _acciones(args: argparse.Namespace, controlador: ControladorExperimentos) -> list[Callable[[], object]]:
    """Acciones pedidas por línea de comandos, en orden de ejecución."""
    acciones: list[Callable[[], object]] = []
    if args.pruebas:
        acciones.append(controlador.ejecutar_pruebas)
    if args.todos:
        acciones.append(controlador.ejecutar_todos)
    elif args.escenario:
        acciones.append(lambda: controlador.ejecutar_escenarios([args.escenario]))
    if args.barrido:
        acciones.append(controlador.ejecutar_barrido)
    if args.traza is not None:
        acciones.append(lambda: controlador.mostrar_traza(args.traza or args.escenario))
    if args.animar is not None:
        acciones.append(controlador.animar)
    if args.gui:
        acciones.append(controlador.abrir_interfaz)
    return acciones


def main(argv: Sequence[str] | None = None) -> int:
    args = crear_parser().parse_args(argv)
    relanzar_fuera_del_sandbox(RAIZ, sys.argv[1:] if argv is None else argv)
    try:
        # Importación diferida: primero se comprueba el entorno y se explica lo que falte.
        from controller.experiment_controller import ControladorExperimentos
    except ModuleNotFoundError as error:
        if not es_dependencia(error):
            raise
        print(explicar_dependencia_faltante(error), file=sys.stderr)
        return 1
    try:
        config = _con_salida_absoluta(aplicar_argumentos(cargar_configuracion(args.config), vars(args)))
        controlador = ControladorExperimentos(config)
        acciones = _acciones(args, controlador)
        if not acciones and args.no_menu:
            print("No se indicó ninguna acción. Use --help para ver las opciones.")
            return 0
        codigo = 0
        for accion in acciones:
            if accion() is False:  # las pruebas devuelven False si alguna falla
                codigo = 1
        if not (args.no_menu or args.gui):
            controlador.menu()
        return codigo
    except ErrorConfiguracion as error:
        print(f"Error de configuración: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.")
        return 130


if __name__ == "__main__":
    sys.exit(main())

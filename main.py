"""Punto de entrada: revisa el entorno, lee la configuración y arranca la aplicación.

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

import sys
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from config.entorno import es_dependencia, explicar_dependencia_faltante, relanzar_fuera_del_sandbox
from config.settings import Configuracion, ErrorConfiguracion, cargar_configuracion
from controller.cli import acciones, aplicar_argumentos, crear_parser

RAIZ = Path(__file__).resolve().parent
RUTA_CONFIG = RAIZ / "config" / "config.json"


def _con_salida_absoluta(config: Configuracion) -> Configuracion:
    """Una carpeta de salida relativa se interpreta respecto de la carpeta del proyecto."""
    carpeta = Path(config.salida.carpeta)
    if carpeta.is_absolute():
        return config
    return replace(config, salida=replace(config.salida, carpeta=str(RAIZ / carpeta)))


def main(argv: Sequence[str] | None = None) -> int:
    args = crear_parser(RUTA_CONFIG).parse_args(argv)
    relanzar_fuera_del_sandbox(RAIZ, sys.argv[1:] if argv is None else argv)
    try:
        # Importación diferida: primero se comprueba el entorno y se explica lo que falte.
        from controller.aplicacion import construir
    except ModuleNotFoundError as error:
        if not es_dependencia(error):
            raise
        print(explicar_dependencia_faltante(error), file=sys.stderr)
        return 1
    try:
        controlador = construir(_con_salida_absoluta(aplicar_argumentos(cargar_configuracion(args.config), vars(args))))
        pedidas = acciones(args, controlador)
        if not pedidas and args.no_menu:
            print("No se indicó ninguna acción. Use --help para ver las opciones.")
            return 0
        codigo = 0
        for accion in pedidas:
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

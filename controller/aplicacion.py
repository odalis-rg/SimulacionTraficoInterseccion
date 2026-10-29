"""Ensamblado de la aplicación (raíz de composición).

Es el único lugar que crea las piezas concretas (servicio, vistas, exportadores
y controlador) y las conecta por inyección de dependencias; ninguna otra clase
crea por su cuenta a sus colaboradores.
"""

from __future__ import annotations

from pathlib import Path

from config.entorno import es_dependencia, explicar_dependencia_faltante
from config.settings import Configuracion
from controller.console_controller import ControladorConsola
from controller.experiment_service import ServicioExperimentos
from view.animacion import VistaAnimacion
from view.console_view import VistaConsola
from view.csv_export import ExportadorCSV
from view.exportacion import ExportadorResultados
from view.plots import GeneradorGraficas


def construir(config: Configuracion) -> ControladorConsola:
    """Controlador de consola con todas sus dependencias conectadas."""
    carpeta = Path(config.salida.carpeta)
    confianza = config.simulacion.confianza
    servicio = ServicioExperimentos(config)
    csv = ExportadorCSV(carpeta)
    animacion = VistaAnimacion(config.animacion, carpeta)
    exportador_consola = ExportadorResultados(
        csv, GeneradorGraficas(carpeta, config.salida.guardar_graficas, config.salida.mostrar_graficas, confianza))
    exportador_interfaz = ExportadorResultados(csv, GeneradorGraficas(carpeta, True, False, confianza))
    return ControladorConsola(servicio, VistaConsola(), exportador_consola, animacion,
                              lambda: _abrir_interfaz(servicio, exportador_interfaz, animacion))


def _abrir_interfaz(servicio: ServicioExperimentos, exportador: ExportadorResultados,
                    animacion: VistaAnimacion) -> str | None:
    """Abre la interfaz gráfica; devuelve un mensaje si no puede. Tkinter solo se carga aquí."""
    try:
        from view.gui import abrir_interfaz
    except ModuleNotFoundError as error:
        if not es_dependencia(error):
            raise
        return explicar_dependencia_faltante(error)
    return abrir_interfaz(servicio, exportador, animacion)

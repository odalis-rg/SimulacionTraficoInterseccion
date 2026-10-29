"""Medidas de la escena animada: geometría de la intersección y disposición de la figura."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Geometria:
    """Intersección vista desde arriba, en unidades de datos (aspecto 1:1).

    La calzada principal es horizontal: su carril inferior es el acceso
    modelado (circulación hacia la derecha) y el superior, el sentido contrario
    (sin tráfico en el modelo). La calle transversal es vertical.
    """

    largo: float = 100.0
    base: float = 2.0
    alto: float = 42.0
    """La escena visible va de ``base`` a ``alto`` en y: un alto de 40 aprovecha el espacio de la ventana."""
    calzada_inferior: float = 18.0
    ancho_carril: float = 5.0
    acera: float = 2.6
    cruce_inicio: float = 74.0
    cruce_ancho: float = 12.0
    retiro_cebra: float = 0.2
    franja_cebra: float = 0.75
    hueco_cebra: float = 0.6
    retiro_linea: float = 0.6
    grosor_linea: float = 0.5
    grosor_borde: float = 0.22
    retiro_borde: float = 0.35
    trazo_central: tuple[float, float] = (2.4, 1.6)
    """(largo del trazo, largo del hueco) de las líneas centrales discontinuas."""
    flecha: tuple[float, float, float, float] = (50.0, 6.0, 0.55, 1.7)
    """(x inicial, largo, ancho del astil, ancho de la punta) de la flecha pintada en el acceso."""
    margen_izquierdo: float = 1.0
    separacion_fila: float = 0.5
    proporcion_largo: float = 0.84
    """Largo del auto respecto del espacio que ocupa cada lugar de la fila."""
    proporcion_ancho: float = 0.5
    """Ancho del auto respecto de su largo."""
    umbral_movimiento: float = 0.02
    """Fracción de lugar por debajo de la cual un auto de la fila se considera detenido (luces de freno)."""
    leyenda: tuple[float, float, float] = (2.0, 11.0, 6.0)
    """(x inicial, y del primer renglón, y del segundo) de la leyenda de autos en la manzana inferior."""
    semaforo_ancho: float = 4.6
    semaforo_alto: float = 10.0
    semaforo_base: float = 3.2
    retiro_semaforo: float = 3.6
    grosor_poste: float = 0.5
    radio_lampara: float = 1.55
    radio_halo: float = 2.5
    alfa_halo: float = 0.3

    @property
    def calzada_superior(self) -> float:
        return self.calzada_inferior + 2 * self.ancho_carril

    @property
    def centro_acceso(self) -> float:
        """y del centro del carril de acceso, por donde circulan los autos."""
        return self.calzada_inferior + self.ancho_carril / 2

    @property
    def cruce_fin(self) -> float:
        return self.cruce_inicio + self.cruce_ancho

    @property
    def linea_detencion(self) -> float:
        """x de la línea de detención, antes del paso de cebra del acceso."""
        return self.cruce_inicio - self.acera - self.retiro_linea

    def paso_fila(self, max_vehiculos: int) -> float:
        """Espacio que ocupa cada lugar de la fila para que quepan ``max_vehiculos`` autos."""
        return (self.linea_detencion - self.separacion_fila - self.margen_izquierdo) / max_vehiculos

    def tamano_auto(self, max_vehiculos: int) -> tuple[float, float]:
        """(largo, ancho) de cada auto para una fila de ``max_vehiculos`` autos."""
        largo = self.paso_fila(max_vehiculos) * self.proporcion_largo
        return largo, largo * self.proporcion_ancho


@dataclass(frozen=True)
class Disposicion:
    """Tamaño de la figura, proporciones de las tres zonas y tipografía."""

    ancho: float = 12.0
    alto: float = 6.4
    filas: tuple[float, float] = (2.0, 1.0)
    columnas: tuple[float, float] = (3.2, 1.25)
    margenes: tuple[float, float, float, float] = (0.06, 0.98, 0.93, 0.09)
    separacion: tuple[float, float] = (0.06, 0.3)
    texto_titulo: float = 16.0
    texto: float = 12.5
    texto_valor: float = 14.0
    texto_pequeno: float = 10.5
    renglon: float = 0.085
    alfa_franjas: float = 0.9
    holgura_serie: float = 1.3


GEOMETRIA = Geometria()
DISPOSICION = Disposicion()


def suavizar(p: float) -> float:
    """Curva ease-out cúbica en [0, 1]: arranca rápido y frena suave."""
    p = min(max(p, 0.0), 1.0)
    return 1.0 - (1.0 - p) ** 3

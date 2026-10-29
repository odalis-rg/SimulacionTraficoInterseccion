"""Pestañas del cuaderno principal, una por módulo."""

from view.gui.pestanas.animacion import PestanaAnimacion
from view.gui.pestanas.barrido import PestanaBarrido
from view.gui.pestanas.resultados import PestanaCiclos, PestanaGraficas, PestanaResultados
from view.gui.pestanas.traza import PestanaTraza
from view.gui.pestanas.verificacion import PestanaVerificacion

__all__ = ["PestanaAnimacion", "PestanaBarrido", "PestanaCiclos", "PestanaGraficas", "PestanaResultados",
           "PestanaTraza", "PestanaVerificacion"]

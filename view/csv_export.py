"""Exportación de resultados a CSV en la carpeta de salida."""

from __future__ import annotations

import csv
import unicodedata
from dataclasses import asdict, fields
from pathlib import Path
from typing import Iterable, Sequence

from controller.analysis import Comparacion, ResultadoBarrido, ResultadoEscenario
from model.simulator import ResultadoReplica
from model.statistics import INDICADORES, MetricasReplica


def nombre_archivo(texto: str) -> str:
    """Convierte un nombre de escenario en un fragmento de archivo seguro (sin tildes ni espacios)."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    limpio = "".join(c.lower() if c.isalnum() else "_" for c in sin_tildes)
    return "_".join(parte for parte in limpio.split("_") if parte) or "escenario"


def sufijo_archivo(resultados: Sequence[ResultadoEscenario]) -> str:
    """'escenarios' si hay varios resultados; si no, el nombre del único escenario."""
    return "escenarios" if len(resultados) > 1 else nombre_archivo(resultados[0].nombre)


class ExportadorCSV:
    """Escribe tablas de resultados como CSV (separador coma, UTF-8)."""

    def __init__(self, carpeta: Path) -> None:
        self._carpeta = carpeta

    def _escribir(self, nombre: str, encabezados: Sequence[str], filas: Iterable[Sequence[object]]) -> Path:
        self._carpeta.mkdir(parents=True, exist_ok=True)
        ruta = self._carpeta / nombre
        with ruta.open("w", newline="", encoding="utf-8") as archivo:
            escritor = csv.writer(archivo)
            escritor.writerow(encabezados)
            escritor.writerows(filas)
        return ruta

    def resumen(self, resultados: Sequence[ResultadoEscenario]) -> Path:
        """Media, desviación estándar e IC de cada indicador por escenario."""
        filas = [
            (r.nombre, r.parametros.lam, r.parametros.g, r.parametros.r, r.parametros.T, r.rho_ef,
             ind.clave, ind.unidad, s.media, s.desviacion, s.ic_inferior, s.ic_superior, s.n)
            for r in resultados
            for ind in INDICADORES
            for s in (r.resumen[ind.clave],)
        ]
        encabezados = ("escenario", "lam", "g", "r", "T", "rho_ef", "indicador", "unidad",
                       "media", "desv_estandar", "ic_inferior", "ic_superior", "n_replicas")
        return self._escribir(f"resumen_{sufijo_archivo(resultados)}.csv", encabezados, filas)

    def replicas(self, resultado: ResultadoEscenario) -> Path:
        """Métricas de cada réplica con su semilla registrada."""
        campos = [f.name for f in fields(MetricasReplica)]
        filas = [
            (i, semilla, *(asdict(m)[c] for c in campos))
            for i, (semilla, m) in enumerate(zip(resultado.semillas, resultado.metricas), start=1)
        ]
        return self._escribir(f"replicas_{nombre_archivo(resultado.nombre)}.csv", ("replica", "semilla", *campos), filas)

    def ciclos(self, nombre: str, replica: int, detalle: ResultadoReplica) -> Path:
        """Vehículos atendidos y cola residual de cada ciclo de una réplica."""
        filas = [(c.ciclo, c.inicio_verde, c.fin_verde, c.atendidos, c.cola_residual) for c in detalle.ciclos]
        encabezados = ("ciclo", "inicio_verde_s", "fin_verde_s", "atendidos", "cola_residual")
        return self._escribir(f"ciclos_{nombre_archivo(nombre)}_rep{replica}.csv", encabezados, filas)

    def traza(self, nombre: str, replica: int, detalle: ResultadoReplica) -> Path:
        """Traza completa de eventos de una réplica (Q(t) sin el vehículo en servicio)."""
        filas = [
            (f.tiempo, f.tipo.name, f.vehiculo_id if f.vehiculo_id is not None else "", f.fase.value, f.cola,
             f.en_servicio if f.en_servicio is not None else "", f.ciclo)
            for f in detalle.traza
        ]
        encabezados = ("tiempo_s", "evento", "vehiculo", "semaforo", "Q_t", "en_servicio", "ciclo")
        return self._escribir(f"traza_{nombre_archivo(nombre)}_rep{replica}.csv", encabezados, filas)

    def comparacion(self, resultados: Sequence[ResultadoEscenario], comparacion: Comparacion) -> Path:
        """Reducción porcentual de cada indicador frente a la base (solo escenarios con su misma λ)."""
        datos = [
            (f.escenario, comparacion.base, f.indicador.clave, f.indicador.unidad, f.base, f.valor, f.reduccion)
            for f in comparacion.filas
        ]
        encabezados = ("escenario", "base", "indicador", "unidad", "media_base", "media_escenario", "reduccion_pct")
        return self._escribir(f"comparacion_base_{sufijo_archivo(resultados)}.csv", encabezados, datos)

    def barrido(self, barrido: ResultadoBarrido) -> Path:
        """Tabla I: configuraciones de g con λ y T fijos (media e IC de cada indicador)."""
        claves = ("capacidad_efectiva", "q_max", "q_media", "wq_media", "area_cola")
        filas = []
        for i, r in enumerate(barrido.resultados):
            valores = [v for c in claves for s in (r.resumen[c],) for v in (s.media, s.ic_inferior, s.ic_superior)]
            filas.append((r.parametros.g, r.parametros.T, r.parametros.fraccion_verde, r.rho_ef, *valores,
                          "si" if i == barrido.indice_optimo else ""))
        encabezados = ("g_s", "T_s", "g_T", "rho_ef",
                       *(f"{c}_{e}" for c in claves for e in ("media", "ic_inf", "ic_sup")),
                       "minimo_Q_media")
        return self._escribir("barrido_g.csv", encabezados, filas)

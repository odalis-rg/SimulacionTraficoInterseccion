"""Gráficas con matplotlib.

Cada gráfica tiene una función ``dibujar_*`` que dibuja sobre una ``Figure``
recibida. La usan tanto ``GeneradorGraficas`` (PNG y ventanas de pyplot) como
la interfaz gráfica (figuras incrustadas en Tkinter), sin duplicar código.
Las series Q(t) y el área acumulada se obtienen de ``model/statistics.py``,
así que Q(t) significa lo mismo que en las tablas (vehículos en espera, sin el
vehículo en servicio).
"""

from __future__ import annotations

import functools
import math
import os
from pathlib import Path
from typing import Callable, Sequence, TypeVar

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from config.entorno import consejo_sandbox
from controller.analysis import ResultadoBarrido, ResultadoEscenario
from model.statistics import INDICADORES_POR_CLAVE, area_acumulada, serie_cola
from model.traffic_light import Fase, IntervaloFase
from view.csv_export import sufijo_archivo
from view.style import ESTILO_GRAFICAS, PALETA, colores_ordinales

ANCHO_FIGURA = 10.0
"""Ancho de las figuras guardadas (pulgadas)."""
ALTO_FIGURA = 4.6
ALTO_FILA = 2.2
"""Alto (pulgadas) de cada fila de subgráficas apiladas."""
ALTO_EXTRA = 1.0
"""Alto adicional (pulgadas) para el título general de las figuras de varias filas."""
COLUMNAS_MAX = 3
"""Columnas máximas en las figuras de múltiplos pequeños."""
ETIQUETAS_EJE: dict[str, str] = {"q_media": r"$\bar{Q}$ (veh)", "wq_media": r"$W_q$ (s/veh)"}
_BACKENDS_NO_INTERACTIVOS = {"agg", "pdf", "ps", "svg", "pgf", "cairo", "template"}
_BACKENDS_ALTERNATIVOS = ("TkAgg", "GTK4Agg", "GTK3Agg", "QtAgg")
"""Backends con ventanas que se prueban si matplotlib eligió uno sin ventanas."""

F = TypeVar("F", bound=Callable[..., object])


# ---------------------------------------------------------------------------
# Entorno gráfico
# ---------------------------------------------------------------------------
def _es_interactivo(backend: str) -> bool:
    nombre = backend.lower()
    return nombre not in _BACKENDS_NO_INTERACTIVOS and "inline" not in nombre


def diagnostico_grafico() -> str | None:
    """None si matplotlib puede abrir ventanas; si no, la causa y cómo resolverla.

    Si matplotlib eligió un backend sin ventanas pero el proceso tiene sesión
    gráfica y MPLBACKEND no lo impone, prueba antes otros backends con ventanas.
    """
    try:
        backend = matplotlib.get_backend()
    except Exception as error:  # noqa: BLE001 — se informa la causa al usuario
        return f"matplotlib no pudo iniciar un backend gráfico ({error})."
    if _es_interactivo(backend):
        return None
    sandbox = consejo_sandbox()
    if sandbox:
        return sandbox
    forzado = os.environ.get("MPLBACKEND")
    if forzado:
        return f"la variable MPLBACKEND={forzado} impone un backend sin ventanas; ejecute «unset MPLBACKEND»."
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return ("este proceso no tiene DISPLAY ni WAYLAND_DISPLAY (sesión SSH, consola TTY o terminal sin acceso "
                "al escritorio); ejecútelo desde una terminal abierta en el escritorio.")
    for alternativo in _BACKENDS_ALTERNATIVOS:
        try:
            plt.switch_backend(alternativo)
            return None
        except Exception:  # noqa: BLE001 — se prueba el siguiente backend
            continue
    return f"matplotlib usa «{backend}» y no hay toolkit con ventanas; instale Tk: sudo apt install python3-tk."


# ---------------------------------------------------------------------------
# Utilidades de dibujo
# ---------------------------------------------------------------------------
def _con_estilo(funcion: F) -> F:
    """Ejecuta la función dentro del estilo común (rc_context) de las gráficas."""

    @functools.wraps(funcion)
    def envoltura(*args: object, **kwargs: object) -> object:
        with matplotlib.rc_context(ESTILO_GRAFICAS):
            return funcion(*args, **kwargs)

    return envoltura  # type: ignore[return-value]


def _preparar(fig: Figure) -> None:
    """Limpia la figura para volver a dibujarla y fija fondo y diseño automático."""
    fig.clear()
    fig.set_facecolor(PALETA.superficie)
    fig.set_layout_engine("constrained")


def _rejilla(cantidad: int) -> tuple[int, int]:
    columnas = min(COLUMNAS_MAX, cantidad)
    return math.ceil(cantidad / columnas), columnas


def sombrear_fases(ax: Axes, fases: Sequence[IntervaloFase], fin: float) -> None:
    """Franjas verticales rojo/verde del calendario de fases dentro de [0, fin]."""
    for fase, color in ((Fase.ROJO, PALETA.franja_roja), (Fase.VERDE, PALETA.franja_verde)):
        tramos = [(f.inicio, min(f.fin, fin) - f.inicio) for f in fases if f.fase is fase and f.inicio < fin]
        ax.broken_barh(tramos, (0, 1), transform=ax.get_xaxis_transform(), facecolors=color, edgecolors="none", zorder=0)


def leyenda_fases() -> list[object]:
    return [
        Line2D([], [], color=PALETA.serie_principal, lw=1.6, label="Q(t)"),
        Patch(facecolor=PALETA.franja_roja, edgecolor=PALETA.rojo, linewidth=0.8, label="Rojo"),
        Patch(facecolor=PALETA.franja_verde, edgecolor=PALETA.verde, linewidth=0.8, label="Verde"),
    ]


def _etiquetar_eje_x(ejes: np.ndarray, usados: int, texto: str) -> None:
    """Pone la etiqueta x en cada subgráfica visible que no tiene otra debajo."""
    columnas = ejes.shape[1]
    for i, ax in enumerate(ejes.flat[:usados]):
        if i + columnas >= usados:
            ax.set_xlabel(texto)
    for ax in ejes.flat[usados:]:
        ax.set_visible(False)


# ---------------------------------------------------------------------------
# Gráficas (cada una dibuja sobre la figura recibida)
# ---------------------------------------------------------------------------
@_con_estilo
def dibujar_cola_en_el_tiempo(fig: Figure, resultados: Sequence[ResultadoEscenario]) -> None:
    """1. Q(t) de la réplica de detalle de cada escenario, con franjas rojo/verde."""
    _preparar(fig)
    ejes = fig.subplots(len(resultados), 1, sharex=True, squeeze=False)
    for ax, r in zip(ejes[:, 0], resultados):
        p, H = r.parametros, r.parametros.H
        tiempos, colas = serie_cola(r.detalle.traza, H)
        sombrear_fases(ax, r.detalle.fases, H)
        ax.step(tiempos, colas, where="post", color=PALETA.serie_principal, lw=1.1, zorder=2)
        ax.set_xlim(0, H)
        ax.set_ylim(0, max(float(colas.max()), 1.0) * 1.12)
        ax.set_ylabel("Q(t) (veh)")
        ax.grid(axis="x", visible=False)
        ax.set_title(f"{r.nombre} · λ = {p.lam:g} veh/s, g = {p.g:g} s, r = {p.r:g} s, ρef = {r.rho_ef:.2f}",
                     loc="left", fontsize="medium")
    ejes[-1, 0].set_xlabel("Tiempo simulado (s)")
    ejes[0, 0].legend(handles=leyenda_fases(), loc="upper left", ncols=3)
    fig.suptitle(f"Q(t): vehículos en espera, sin el vehículo en servicio (réplica {resultados[0].replica_detalle})")


@_con_estilo
def dibujar_colas_superpuestas(fig: Figure, barrido: ResultadoBarrido, ventana: float) -> None:
    """2. Fig. 2: Q(t) inicial y área acumulada bajo Q(t) de cada configuración de g."""
    _preparar(fig)
    ax_q, ax_a = fig.subplots(2, 1)
    colores = colores_ordinales(len(barrido.resultados))
    H = barrido.resultados[0].parametros.H
    fin_ventana = min(ventana, H)
    pico = 1.0
    for i, (r, color) in enumerate(zip(barrido.resultados, colores)):
        tiempos, colas = serie_cola(r.detalle.traza, H)
        pico = max(pico, float(colas[tiempos <= fin_ventana].max()))
        grosor = 2.6 if i == barrido.indice_optimo else 1.3
        etiqueta = f"g = {r.parametros.g:g} s (g/T = {r.parametros.fraccion_verde:.2f})"
        ax_q.step(tiempos, colas, where="post", color=color, lw=grosor, label=etiqueta)
        ax_a.plot(tiempos, area_acumulada(tiempos, colas), color=color, lw=grosor, label=etiqueta)
    ax_q.set_xlim(0, fin_ventana)
    ax_q.set_ylim(0, pico * 1.35)
    ax_q.set_xlabel("Tiempo simulado (s)")
    ax_q.set_ylabel("Q(t) (veh)")
    ax_q.set_title(f"(a) Q(t) en los primeros {fin_ventana:g} s", loc="left", fontsize="medium")
    ax_q.legend(loc="upper left", ncols=3, fontsize="small")
    ax_a.set_yscale("log")
    ax_a.set_xlim(0, H)
    ax_a.set_xlabel("Tiempo simulado (s)")
    ax_a.set_ylabel(r"$\int_0^t Q\,ds$ (veh·s, log)")
    ax_a.set_title("(b) Área acumulada bajo Q(t) = demora total acumulada en cola", loc="left", fontsize="medium")
    if barrido.indice_optimo is not None:
        g_opt = barrido.resultados[barrido.indice_optimo].parametros.g
        ax_a.annotate(f"menor área: g = {g_opt:g} s", xy=(0.99, 0.04), xycoords="axes fraction", ha="right",
                      fontsize="small", color=PALETA.texto)
    fig.suptitle(f"Fig. 2 — Colas por configuración de g (λ = {barrido.lam:g} veh/s, T = {barrido.T:g} s, "
                 f"réplica {barrido.resultados[0].replica_detalle})")


@_con_estilo
def dibujar_barras_indicador(fig: Figure, resultados: Sequence[ResultadoEscenario], clave: str,
                             confianza: float) -> None:
    """3 y 4. Media entre réplicas de un indicador por escenario, con su IC."""
    _preparar(fig)
    indicador = INDICADORES_POR_CLAVE[clave]
    ax = fig.subplots()
    x = np.arange(len(resultados))
    medias = np.array([r.resumen[clave].media for r in resultados])
    semianchos = np.array([r.resumen[clave].semiancho for r in resultados])
    ax.bar(x, medias, width=0.6, color=PALETA.serie_principal, zorder=2)
    ax.errorbar(x, medias, yerr=semianchos, fmt="none", ecolor=PALETA.texto, elinewidth=1.2, capsize=4, zorder=3)
    for xi, media, h in zip(x, medias, semianchos):
        if np.isfinite(media):
            tope = media + (h if np.isfinite(h) else 0.0)
            ax.annotate(f"{media:.2f}", (xi, tope), xytext=(0, 4), textcoords="offset points", ha="center",
                        va="bottom", fontsize="small", color=PALETA.texto_secundario)
    ax.set_xticks(x, [r.nombre for r in resultados])
    ax.set_ylabel(ETIQUETAS_EJE.get(clave, f"{indicador.simbolo} ({indicador.unidad})"))
    ax.set_ylim(bottom=0)
    ax.margins(y=0.15)
    ax.grid(axis="x", visible=False)
    ax.set_title(f"{indicador.descripcion}: media e IC {confianza:.0%} ({len(resultados[0].metricas)} réplicas)")


@_con_estilo
def dibujar_residual_por_ciclo(fig: Figure, resultados: Sequence[ResultadoEscenario]) -> None:
    """5. Cola residual media al final de cada verde, ciclo a ciclo, por escenario."""
    _preparar(fig)
    filas, columnas = _rejilla(len(resultados))
    ejes = fig.subplots(filas, columnas, squeeze=False)
    for ax, r in zip(ejes.flat, resultados):
        ciclos = np.arange(1, r.residual_por_ciclo.size + 1)
        ax.plot(ciclos, r.residual_por_ciclo, color=PALETA.serie_principal, lw=1.6)
        ax.set_ylim(bottom=0)
        ax.set_title(f"{r.nombre} (ρef = {r.rho_ef:.2f})", loc="left", fontsize="medium")
    for ax in ejes[:, 0]:
        ax.set_ylabel("Cola residual (veh)")
    _etiquetar_eje_x(ejes, len(resultados), "Ciclo")
    fig.suptitle(f"Cola residual al final de cada verde — media de {len(resultados[0].metricas)} réplicas")


@_con_estilo
def dibujar_histograma_esperas(fig: Figure, resultados: Sequence[ResultadoEscenario]) -> None:
    """6. Distribución de la espera de los vehículos que iniciaron servicio."""
    _preparar(fig)
    filas, columnas = _rejilla(len(resultados))
    ejes = fig.subplots(filas, columnas, squeeze=False)
    for ax, r in zip(ejes.flat, resultados):
        ax.set_title(r.nombre, loc="left", fontsize="medium")
        if r.esperas.size == 0:
            ax.text(0.5, 0.5, "Sin vehículos atendidos", transform=ax.transAxes, ha="center",
                    color=PALETA.texto_secundario)
            continue
        pesos = np.full(r.esperas.size, 100.0 / r.esperas.size)
        bordes = np.histogram_bin_edges(r.esperas, bins="auto")
        ax.hist(r.esperas, bins=bordes, weights=pesos, color=PALETA.serie_principal,
                edgecolor=PALETA.superficie, linewidth=0.4)
        wq = r.resumen["wq_media"].media
        ax.axvline(wq, color=PALETA.texto, lw=1.2)
        ax.annotate(f"Wq = {wq:.1f} s", xy=(wq, 1.0), xycoords=("data", "axes fraction"), xytext=(4, -12),
                    textcoords="offset points", fontsize="small", color=PALETA.texto,
                    bbox={"boxstyle": "round,pad=0.2", "facecolor": PALETA.superficie, "edgecolor": "none"})
        ax.grid(axis="x", visible=False)
    for ax in ejes[:, 0]:
        ax.set_ylabel("% de vehículos")
    _etiquetar_eje_x(ejes, len(resultados), "Espera (s)")
    fig.suptitle(f"Distribución de la espera (inicio de servicio − llegada), {len(resultados[0].metricas)} réplicas")


@_con_estilo
def dibujar_indicadores_vs_g(fig: Figure, barrido: ResultadoBarrido, confianza: float) -> None:
    """7. Q̄ y Wq frente a g/T en el barrido, con el mínimo marcado."""
    _preparar(fig)
    ejes = fig.subplots(1, 2)
    x = np.array([r.parametros.fraccion_verde for r in barrido.resultados])
    for ax, clave, minimo in zip(ejes, ("q_media", "wq_media"), (barrido.indice_optimo, barrido.indice_min_wq)):
        medias = np.array([r.resumen[clave].media for r in barrido.resultados])
        semianchos = np.array([r.resumen[clave].semiancho for r in barrido.resultados])
        ax.errorbar(x, medias, yerr=semianchos, fmt="-o", color=PALETA.serie_principal,
                    ecolor=PALETA.texto_secundario, capsize=3, ms=5, lw=1.6)
        if minimo is not None:
            ax.plot(x[minimo], medias[minimo], marker="o", ms=13, mfc="none", mec=PALETA.texto, mew=1.6)
            ax.annotate(f"mínimo\ng = {barrido.resultados[minimo].parametros.g:g} s", (x[minimo], medias[minimo]),
                        xytext=(-14, -14), textcoords="offset points", ha="right", va="top", fontsize="small",
                        color=PALETA.texto)
        ax.set_yscale("log")
        ax.set_xlabel("g/T (fracción de verde del ciclo)")
        ax.set_ylabel(f"{ETIQUETAS_EJE[clave]}, escala log")
        ax.set_title(INDICADORES_POR_CLAVE[clave].descripcion, loc="left", fontsize="medium")
    fig.suptitle(f"Barrido de g (λ = {barrido.lam:g} veh/s, T = {barrido.T:g} s): media e IC {confianza:.0%}")


# ---------------------------------------------------------------------------
# Archivos PNG y ventanas de pyplot
# ---------------------------------------------------------------------------
class GeneradorGraficas:
    """Guarda las figuras del informe como PNG y, si se pide, las muestra con pyplot."""

    def __init__(self, carpeta: Path, guardar: bool, mostrar: bool, confianza: float) -> None:
        self._carpeta = carpeta
        self._guardar = guardar
        self._mostrar = mostrar
        self._confianza = confianza

    def _nueva(self, alto: float) -> Figure:
        """Figura administrada por pyplot si se van a mostrar; si no, una figura independiente."""
        tamano = (ANCHO_FIGURA, alto)
        return plt.figure(figsize=tamano) if self._mostrar else Figure(figsize=tamano)

    def _finalizar(self, figura: Figure, nombre: str) -> Path | None:
        """Guarda la figura si corresponde."""
        if not self._guardar:
            return None
        self._carpeta.mkdir(parents=True, exist_ok=True)
        ruta = self._carpeta / nombre
        with matplotlib.rc_context(ESTILO_GRAFICAS):
            figura.savefig(ruta)
        return ruta

    def mostrar(self) -> str | None:
        """Abre las figuras pendientes; devuelve un aviso con la causa si no se puede."""
        if not self._mostrar or not plt.get_fignums():
            return None
        causa = diagnostico_grafico()
        if causa:
            plt.close("all")
            return f"Las gráficas se guardaron, pero no se pueden mostrar: {causa}"
        plt.show()
        return None

    def cola_en_el_tiempo(self, resultados: Sequence[ResultadoEscenario]) -> Path | None:
        figura = self._nueva(ALTO_FILA * len(resultados) + ALTO_EXTRA)
        dibujar_cola_en_el_tiempo(figura, resultados)
        return self._finalizar(figura, f"q_t_{sufijo_archivo(resultados)}.png")

    def colas_superpuestas(self, barrido: ResultadoBarrido, ventana: float) -> Path | None:
        figura = self._nueva(2 * ALTO_FIGURA * 0.8)
        dibujar_colas_superpuestas(figura, barrido, ventana)
        return self._finalizar(figura, "fig2_colas_configuraciones_g.png")

    def barras_indicador(self, resultados: Sequence[ResultadoEscenario], clave: str) -> Path | None:
        figura = self._nueva(ALTO_FIGURA)
        dibujar_barras_indicador(figura, resultados, clave, self._confianza)
        return self._finalizar(figura, f"barras_{clave}_{sufijo_archivo(resultados)}.png")

    def residual_por_ciclo(self, resultados: Sequence[ResultadoEscenario]) -> Path | None:
        figura = self._nueva(ALTO_FILA * _rejilla(len(resultados))[0] + ALTO_EXTRA)
        dibujar_residual_por_ciclo(figura, resultados)
        return self._finalizar(figura, f"residual_ciclos_{sufijo_archivo(resultados)}.png")

    def histograma_esperas(self, resultados: Sequence[ResultadoEscenario]) -> Path | None:
        figura = self._nueva(ALTO_FILA * _rejilla(len(resultados))[0] + ALTO_EXTRA)
        dibujar_histograma_esperas(figura, resultados)
        return self._finalizar(figura, f"histograma_espera_{sufijo_archivo(resultados)}.png")

    def indicadores_vs_g(self, barrido: ResultadoBarrido) -> Path | None:
        figura = self._nueva(ALTO_FIGURA)
        dibujar_indicadores_vs_g(figura, barrido, self._confianza)
        return self._finalizar(figura, "barrido_indicadores_g.png")

"""Formato compartido por la consola y la interfaz gráfica.

Números, filas de tablas y frases de resultado se construyen solo aquí, para
que ambas vistas muestren exactamente lo mismo.
"""

from __future__ import annotations

import math

from controller.analysis import Comparacion, FilaComparacion, ResultadoBarrido, ResultadoEscenario, Resumen
from model.events import RegistroTraza
from model.statistics import MetricasReplica, RegistroCiclo

DECIMALES = 2
"""Decimales con que se muestran medias, desviaciones e intervalos."""
SIN_DATO = "—"

ENCABEZADOS_TRAZA = ("Tiempo (s)", "Evento", "Vehículo", "Semáforo", "Q(t)", "En servicio", "Ciclo")
ENCABEZADOS_BARRIDO = ("g (s)", "T (s)", "g/T", "ρef", "C (veh/h)", "Qmáx (veh)", "Q̄ (veh)", "Wq (s/veh)", "")
ENCABEZADOS_COMPARACION = ("Escenario", "Indicador", "Base", "Escenario", "Reducción")
MARCA_OPTIMO = "◄ mínimo Q̄"
NOTA_REDUCCION = "Reducción = 100·(base − escenario)/base; positiva = el escenario reduce el indicador."
NOTA_REDUCCION_TABLA = ("Entre paréntesis, la reducción respecto de la base: 100·(base − escenario)/base; "
                        "positiva = el escenario reduce el indicador.")


def numero(valor: float | None, decimales: int = DECIMALES) -> str:
    """Número con decimales fijos; '—' si no está definido."""
    return SIN_DATO if valor is None or not math.isfinite(valor) else f"{valor:.{decimales}f}"


def media_ic(resumen: Resumen) -> str:
    """'media ± semiancho' (solo la media si el IC no está definido)."""
    if not math.isfinite(resumen.semiancho):
        return numero(resumen.media)
    return f"{numero(resumen.media)} ± {numero(resumen.semiancho)}"


def porcentaje(valor: float) -> str:
    """Variación porcentual con signo; '—' si no está definida."""
    return SIN_DATO if not math.isfinite(valor) else f"{valor:+.1f} %"


def vehiculo(identificador: int | None) -> str:
    """'#id' del vehículo o '—'."""
    return SIN_DATO if identificador is None else f"#{identificador}"


def fila_traza(fila: RegistroTraza) -> tuple[str, ...]:
    """Fila de la traza: evento y estado justo después (Q(t) sin el vehículo en servicio)."""
    return (f"{fila.tiempo:.3f}", fila.tipo.name, vehiculo(fila.vehiculo_id), fila.fase.value, str(fila.cola),
            vehiculo(fila.en_servicio), str(fila.ciclo))


def celda_ciclo(ciclo: RegistroCiclo | None) -> str:
    """'atendidos / cola residual' de un ciclo."""
    return SIN_DATO if ciclo is None else f"{ciclo.atendidos} / {ciclo.cola_residual}"


def fila_barrido(resultado: ResultadoEscenario, es_optimo: bool) -> tuple[str, ...]:
    """Fila de la Tabla I (media ± IC de cada indicador)."""
    p, s = resultado.parametros, resultado.resumen
    return (f"{p.g:g}", f"{p.T:g}", f"{p.fraccion_verde:.3f}", f"{resultado.rho_ef:.2f}",
            media_ic(s["capacidad_efectiva"]), media_ic(s["q_max"]), media_ic(s["q_media"]), media_ic(s["wq_media"]),
            MARCA_OPTIMO if es_optimo else "")


def fila_comparacion(fila: FilaComparacion) -> tuple[str, ...]:
    """Fila de la comparación porcentual frente a la base."""
    return (fila.escenario, f"{fila.indicador.simbolo} ({fila.indicador.unidad})", numero(fila.base),
            numero(fila.valor), porcentaje(fila.reduccion))


def tabla_comparacion(comparacion: Comparacion) -> tuple[list[str], list[tuple[str, ...]]]:
    """Comparación de doble entrada: un renglón por indicador y una columna por escenario.

    Cada celda muestra la media del escenario y, entre paréntesis, su reducción respecto de la base.
    """
    escenarios = list(dict.fromkeys(f.escenario for f in comparacion.filas))
    celdas = {(f.indicador.clave, f.escenario): f for f in comparacion.filas}
    filas = []
    for clave in dict.fromkeys(f.indicador.clave for f in comparacion.filas):
        referencia = celdas[(clave, escenarios[0])]
        valores = (celdas[(clave, e)] for e in escenarios)
        filas.append((f"{referencia.indicador.simbolo} ({referencia.indicador.unidad})", numero(referencia.base),
                      *(f"{numero(f.valor)}  ({porcentaje(f.reduccion)})" for f in valores)))
    return ["Indicador", comparacion.base, *escenarios], filas


def texto_no_comparables(nombres: tuple[str, ...]) -> str:
    return f"No se comparan por tener otra λ (cambia la demanda, no solo las fases): {', '.join(nombres)}."


def texto_balance(m: MetricasReplica, H: float) -> str:
    """Balance de vehículos al terminar el horizonte."""
    return (f"Al terminar H = {H:g} s: llegados {m.llegados} = salidos {m.salidos} + en cola {m.en_cola_final} "
            f"+ en servicio {m.en_servicio_final} → balance {'OK' if m.balance_ok else 'FALLÓ'}.")


def texto_censura(m: MetricasReplica) -> str | None:
    """Pendientes al terminar H (observación censurada) o None si no hay."""
    if not m.pendientes:
        return None
    return (f"Pendientes (observación censurada): {m.pendientes}; tiempo desde la llegada hasta H: "
            f"media {numero(m.censura_media)} s, máximo {numero(m.censura_max)} s (no incluido en W).")


def textos_optimo(barrido: ResultadoBarrido) -> list[str]:
    """Configuración con menor área bajo Q(t) y alcance de esa conclusión."""
    textos = []
    if barrido.indice_optimo is not None:
        optimo = barrido.resultados[barrido.indice_optimo].parametros
        textos.append(f"Menor área bajo Q(t) (Q̄ y demora total en cola): g = {optimo.g:g} s, r = {optimo.r:g} s "
                      f"(g/T = {optimo.fraccion_verde:.3f}).")
    if barrido.indice_min_wq is not None and barrido.indice_min_wq != barrido.indice_optimo:
        g_min_wq = barrido.resultados[barrido.indice_min_wq].parametros.g
        textos.append(f"El menor Wq medio se obtiene con g = {g_min_wq:g} s.")
    textos.append("Es el mejor valor solo entre los g probados y para este modelo de un acceso; no es una "
                  "optimización global de la intersección (con T fijo, más verde aquí implica más rojo en los "
                  "accesos en conflicto, que este modelo no representa).")
    return textos

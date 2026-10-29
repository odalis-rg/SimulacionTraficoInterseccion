"""Vista de consola: menú, tablas y mensajes. No contiene lógica del modelo."""

from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Sequence

from config.settings import Configuracion
from controller.analysis import Comparacion, ResultadoBarrido, ResultadoEscenario
from model.simulator import ResultadoReplica
from model.statistics import INDICADORES, MetricasReplica, capacidad_nominal, rho_efectivo
from view.formato import (
    ENCABEZADOS_BARRIDO,
    ENCABEZADOS_COMPARACION,
    ENCABEZADOS_TRAZA,
    NOTA_REDUCCION,
    celda_ciclo,
    fila_barrido,
    fila_comparacion,
    fila_traza,
    media_ic,
    numero,
    texto_balance,
    texto_censura,
    texto_no_comparables,
    textos_optimo,
)

NOTA_RHO = "ρef = λT/(μg) compara demanda y capacidad nominal por ciclo; no garantiza régimen estacionario."
NOTA_HORIZONTE = "Los resultados describen el horizonte simulado [0, H], no un régimen estacionario."


# ---------------------------------------------------------------------------
# Formato
# ---------------------------------------------------------------------------
def _ancho(texto: str) -> int:
    """Columnas visibles: los caracteres combinantes (la barra de Q̄) no ocupan espacio."""
    return sum(0 if unicodedata.combining(c) else 1 for c in texto)


def _ajustar(texto: str, ancho: int, alineacion: str) -> str:
    relleno = " " * max(0, ancho - _ancho(texto))
    return texto + relleno if alineacion == "<" else relleno + texto


def tabla(encabezados: Sequence[str], filas: Sequence[Sequence[str]], alineaciones: str | None = None) -> str:
    """Tabla de texto con columnas alineadas; ``alineaciones`` tiene '<' o '>' por columna."""
    alineaciones = alineaciones or "<" + ">" * (len(encabezados) - 1)
    anchos = [max(_ancho(str(fila[i])) for fila in (encabezados, *filas)) for i in range(len(encabezados))]

    def linea(celdas: Sequence[str]) -> str:
        return "  ".join(_ajustar(str(c), a, al) for c, a, al in zip(celdas, anchos, alineaciones)).rstrip()

    return "\n".join([linea(encabezados), "  ".join("─" * a for a in anchos), *(linea(f) for f in filas)])


# ---------------------------------------------------------------------------
# Vista
# ---------------------------------------------------------------------------
class VistaConsola:
    """Presenta en la terminal los datos que le entrega el controlador."""

    # -- Mensajes ---------------------------------------------------------
    def titulo(self, texto: str) -> None:
        print(f"\n{texto}\n{'═' * _ancho(texto)}")

    def mensaje(self, texto: str) -> None:
        print(f"  {texto}")

    def advertencia(self, texto: str) -> None:
        print(f"  ⚠ {texto}")

    def error(self, texto: str) -> None:
        print(f"  ✖ {texto}")

    def progreso(self, nombre: str, replicas: int, segundos: float) -> None:
        print(f"  ✓ {nombre}: {replicas} réplicas simuladas en {segundos:.2f} s")

    def archivos(self, rutas: Sequence[Path]) -> None:
        if rutas:
            print("  Archivos generados:")
            for ruta in rutas:
                print(f"    • {ruta.relative_to(Path.cwd()) if ruta.is_relative_to(Path.cwd()) else ruta}")

    # -- Entrada ----------------------------------------------------------
    @staticmethod
    def _leer(texto: str) -> str | None:
        """Lee una línea; devuelve None si se cierra la entrada (Ctrl+D)."""
        try:
            return input(texto).strip()
        except EOFError:
            print()
            return None

    def pedir_opcion(self, opciones: dict[str, str]) -> str | None:
        self.titulo("Simulación de un acceso semaforizado — menú principal")
        for clave, texto in opciones.items():
            print(f"  {clave}) {texto}")
        return self._leer("Opción: ")

    def elegir(self, titulo: str, nombres: Sequence[str]) -> str | None:
        """Selección por número o por nombre; None si se cancela o no es válida."""
        print(f"\n{titulo}")
        for i, nombre in enumerate(nombres, start=1):
            print(f"  {i}) {nombre}")
        respuesta = self._leer("Número o nombre (Enter para cancelar): ")
        if not respuesta:
            return None
        if respuesta.isdigit() and 1 <= int(respuesta) <= len(nombres):
            return nombres[int(respuesta) - 1]
        elegido = next((n for n in nombres if n.casefold() == respuesta.casefold()), None)
        if elegido is None:
            self.error("Selección no válida.")
        return elegido

    def pedir_entero(self, texto: str, por_defecto: int) -> int | None:
        """Entero ≥ 1; Enter acepta el valor por defecto."""
        respuesta = self._leer(f"{texto} [{por_defecto}]: ")
        if respuesta is None:
            return None
        if respuesta == "":
            return por_defecto
        if respuesta.isdigit() and int(respuesta) >= 1:
            return int(respuesta)
        self.error("Debe ser un entero ≥ 1.")
        return None

    # -- Configuración ------------------------------------------------------
    def configuracion(self, config: Configuracion) -> None:
        sim, b, s, a = config.simulacion, config.barrido, config.salida, config.animacion
        self.titulo("Configuración activa")
        filas = [
            ("μ (tasa de servicio en verde)", f"{sim.mu:g} veh/s"),
            ("H (horizonte)", f"{sim.H:g} s"),
            ("n (réplicas por escenario)", str(sim.n_replicas)),
            ("Semillas (semilla_base + i)", f"{sim.semilla(1)} … {sim.semilla(sim.n_replicas)}"),
            ("Nivel de confianza", f"{sim.confianza:.0%} (t de Student)"),
            ("Escenario base", config.escenario_base),
            ("Barrido de g", f"λ = {b.lam:g} veh/s, T = {b.T:g} s, g = {', '.join(f'{g:g}' for g in b.valores_g)} s"),
            ("Réplica de detalle", f"{s.replica_detalle} (traza, ciclos, Q(t) y animación)"),
            ("Carpeta de salida", s.carpeta),
            ("Gráficas", f"guardar: {'sí' if s.guardar_graficas else 'no'}, mostrar: {'sí' if s.mostrar_graficas else 'no'}"),
            ("Animación", f"{a.escenario}: primeros {a.ventana_s:g} s a ×{a.velocidad:g}, {a.fps} fps, "
                          f"máx. {a.max_vehiculos_fila} veh. en fila, GIF: {'sí' if a.guardar_gif else 'no'}"),
        ]
        print(tabla(("Parámetro", "Valor"), filas, "<<"))
        self.escenarios(config)

    def escenarios(self, config: Configuracion) -> None:
        self.titulo("Escenarios")
        filas = []
        for e in config.escenarios:
            p = e.parametros(config.simulacion)
            filas.append((e.nombre, f"{p.lam:g}", f"{p.g:g}", f"{p.r:g}", f"{p.T:g}",
                          f"{rho_efectivo(p):.2f}", f"{capacidad_nominal(p):.0f}"))
        print(tabla(("Escenario", "λ (veh/s)", "g (s)", "r (s)", "T (s)", "ρef", "Cap. nominal (veh/h)"), filas))
        self.mensaje(NOTA_RHO)

    # -- Resultados por escenario ------------------------------------------
    def resumen(self, r: ResultadoEscenario, confianza: float) -> None:
        p = r.parametros
        self.titulo(f"Resumen — {r.nombre}: λ = {p.lam:g} veh/s, g = {p.g:g} s, r = {p.r:g} s, "
                    f"T = {p.T:g} s, ρef = {r.rho_ef:.2f}")
        filas = []
        for ind in INDICADORES:
            s = r.resumen[ind.clave]
            filas.append((f"{ind.simbolo:<9} {ind.descripcion}", ind.unidad, media_ic(s), numero(s.desviacion),
                          numero(s.ic_inferior), numero(s.ic_superior), str(s.n)))
        encabezados = ("Indicador", "Unidad", f"Media ± IC {confianza:.0%}", "Desv. est.", "IC inf.", "IC sup.", "n")
        print(tabla(encabezados, filas, "<<>>>>>"))
        fallos = sum(not m.balance_ok for m in r.metricas)
        balance = "OK en todas las réplicas" if fallos == 0 else f"FALLÓ en {fallos} réplicas"
        self.mensaje(f"Balance llegados = salidos + pendientes (en cola y en servicio): {balance}.")
        self.mensaje("Pend.(H) y Cens.(H) son observaciones censuradas: no se mezclan con W ni con Wq.")
        if r.rho_ef >= 1:
            self.advertencia("ρef ≥ 1: la cola puede crecer ciclo a ciclo. " + NOTA_HORIZONTE)

    def ciclos(self, resultados: Sequence[ResultadoEscenario], max_filas: int) -> None:
        replica = resultados[0].replica_detalle
        self.titulo(f"Atendidos / cola residual al final de cada verde (réplica {replica})")
        total = max(len(r.detalle.ciclos) for r in resultados)
        filas = []
        for k in range(min(total, max_filas)):
            fila = [str(k + 1)]
            for r in resultados:
                fila.append(celda_ciclo(r.detalle.ciclos[k] if k < len(r.detalle.ciclos) else None))
            filas.append(fila)
        print(tabla(("Ciclo", *(r.nombre for r in resultados)), filas))
        if total > max_filas:
            self.mensaje(f"… {total - max_filas} ciclos más en los archivos ciclos_*.csv")

    def comparacion(self, comparacion: Comparacion) -> None:
        self.titulo(f"Comparación porcentual frente a '{comparacion.base}' (misma λ, medias entre réplicas)")
        if comparacion.filas:
            print(tabla(ENCABEZADOS_COMPARACION, [fila_comparacion(f) for f in comparacion.filas], "<<>>>"))
            self.mensaje(NOTA_REDUCCION)
        if comparacion.no_comparables:
            self.mensaje(texto_no_comparables(comparacion.no_comparables))

    # -- Barrido ------------------------------------------------------------
    def barrido(self, barrido: ResultadoBarrido, confianza: float) -> None:
        self.titulo(f"Tabla I — Configuraciones semafóricas (λ = {barrido.lam:g} veh/s, T = {barrido.T:g} s, "
                    f"media ± IC {confianza:.0%})")
        filas = [fila_barrido(r, i == barrido.indice_optimo) for i, r in enumerate(barrido.resultados)]
        print(tabla(ENCABEZADOS_BARRIDO, filas, ">>>>>>>><"))
        for texto in textos_optimo(barrido):
            self.mensaje(texto)

    # -- Traza --------------------------------------------------------------
    def traza(self, nombre: str, replica: int, resultado: ResultadoReplica, max_eventos: int) -> None:
        self.titulo(f"Traza de eventos — {nombre}, réplica {replica} (semilla {resultado.semilla})")
        filas = [fila_traza(f) for f in resultado.traza[:max_eventos]]
        print(tabla(ENCABEZADOS_TRAZA, filas, "><<<>>>"))
        self.mensaje(f"Se muestran {len(filas)} de {len(resultado.traza)} eventos; estado justo después de cada evento.")
        self.mensaje("Q(t) = vehículos en espera, sin el que está en servicio. "
                     "Eventos simultáneos: SALIDA → CAMBIO_FASE → LLEGADA.")

    def pendientes(self, m: MetricasReplica, H: float) -> None:
        self.mensaje(texto_balance(m, H))
        censura = texto_censura(m)
        if censura:
            self.mensaje(censura)

    # -- Pruebas ------------------------------------------------------------
    def prueba(self, numero: int, descripcion: str, exito: bool, detalle: str) -> None:
        print(f"  [{'OK' if exito else 'FALLÓ':^5}] {numero}. {descripcion}")
        if detalle:
            print(f"           → {detalle}")

    def total_pruebas(self, exitos: int, total: int) -> None:
        estado = "todas superadas" if exitos == total else f"{total - exitos} con fallos"
        self.mensaje(f"Resultado: {exitos}/{total} pruebas OK ({estado}).")

"""Lectura validada de los campos de texto de la interfaz.

Convierten el texto que escribe el usuario y lanzan ``ErrorConfiguracion``
con un mensaje legible si no es válido; no dependen de Tkinter.
"""

from __future__ import annotations

from config.settings import ErrorConfiguracion


def leer_real(texto: str, nombre: str, mayor_que: float | None = None) -> float:
    """Número decimal (acepta coma decimal), opcionalmente mayor que ``mayor_que``."""
    try:
        valor = float(texto.replace(",", "."))
    except ValueError:
        raise ErrorConfiguracion(f"{nombre} debe ser un número (recibido: «{texto}»).") from None
    if mayor_que is not None and valor <= mayor_que:
        raise ErrorConfiguracion(f"{nombre} debe ser mayor que {mayor_que:g}.")
    return valor


def leer_entero(texto: str, nombre: str, minimo: int | None = None) -> int:
    """Número entero, opcionalmente ≥ ``minimo``."""
    try:
        valor = int(texto)
    except ValueError:
        raise ErrorConfiguracion(f"{nombre} debe ser un entero (recibido: «{texto}»).") from None
    if minimo is not None and valor < minimo:
        raise ErrorConfiguracion(f"{nombre} debe ser un entero ≥ {minimo}.")
    return valor


def leer_reales(texto: str, nombre: str) -> list[float]:
    """Lista de números separados por comas o punto y coma; se ignoran los vacíos."""
    return [leer_real(parte.strip(), nombre) for parte in texto.replace(";", ",").split(",") if parte.strip()]

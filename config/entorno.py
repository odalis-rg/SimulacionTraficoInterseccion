"""Diagnóstico del entorno de ejecución (solo biblioteca estándar).

Detecta el caso de una terminal dentro de un sandbox Flatpak, como la terminal
integrada de VS Code instalado como Flatpak. Su Python es el del sandbox: no
ve los paquetes del sistema (numpy, scipy, matplotlib, tkinter) ni tiene
DISPLAY, así que no puede ejecutar el simulador ni abrir ventanas. En ese caso
el programa se relanza en el sistema anfitrión con ``flatpak-spawn --host``.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path
from typing import Sequence

PAQUETES_DEBIAN: dict[str, str] = {
    "numpy": "python3-numpy",
    "scipy": "python3-scipy",
    "matplotlib": "python3-matplotlib",
    "PIL": "python3-pil",
    "tkinter": "python3-tk",
    "_tkinter": "python3-tk",
}
"""Módulo requerido → paquete de Debian/Ubuntu que lo instala."""
MODULOS_REQUERIDOS = ("numpy", "scipy", "matplotlib", "tkinter")


def sandbox_flatpak() -> str | None:
    """Id de la aplicación Flatpak si el proceso corre dentro de su sandbox; si no, None."""
    if os.environ.get("FLATPAK_ID"):
        return os.environ["FLATPAK_ID"]
    return "Flatpak" if Path("/.flatpak-info").exists() else None


def consejo_sandbox() -> str | None:
    """Cómo ejecutar fuera del sandbox, o None si no se está en uno."""
    app = sandbox_flatpak()
    if app is None:
        return None
    return (f"Esta terminal corre dentro del sandbox Flatpak de {app}: su Python no ve los paquetes del sistema "
            "ni puede abrir ventanas. Use una terminal del sistema (python3 main.py --gui) o, en VS Code, "
            "abra una terminal del anfitrión con «flatpak-spawn --host bash».")


def modulos_faltantes() -> list[str]:
    """Módulos requeridos que no puede importar este intérprete."""
    return [modulo for modulo in MODULOS_REQUERIDOS if importlib.util.find_spec(modulo) is None]


def es_dependencia(error: ModuleNotFoundError) -> bool:
    """True si el módulo ausente es una dependencia externa (no un módulo del proyecto)."""
    return (error.name or "").split(".")[0] in PAQUETES_DEBIAN


def explicar_dependencia_faltante(error: ModuleNotFoundError) -> str:
    """Mensaje con el módulo ausente, el intérprete usado y cómo resolverlo."""
    modulo = (error.name or "").split(".")[0]
    lineas = [f"Falta el módulo «{modulo}» en el Python que ejecuta el programa "
              f"({sys.executable}, versión {sys.version.split()[0]})."]
    consejo = consejo_sandbox()
    if consejo:
        lineas.append(consejo)
    else:
        lineas.append(f"Instálelo con «sudo apt install {PAQUETES_DEBIAN.get(modulo, modulo)}» o, dentro de un "
                      "entorno virtual, con «pip install -r requirements.txt».")
    return "\n".join(lineas)


def python_del_anfitrion(raiz: Path) -> str:
    """Intérprete para el anfitrión: el .venv del proyecto si existe; si no, python3 del sistema."""
    for carpeta in (raiz / ".venv", raiz.parent / ".venv"):
        if (carpeta / "pyvenv.cfg").is_file():
            return str(carpeta / "bin" / "python")
    return "python3"


def relanzar_fuera_del_sandbox(raiz: Path, argumentos: Sequence[str]) -> None:
    """Dentro de un sandbox Flatpak sin las dependencias, reemplaza este proceso por el
    mismo comando ejecutado en el anfitrión. En cualquier otro caso no hace nada."""
    app = sandbox_flatpak()
    faltantes = modulos_faltantes()
    if app is None or not faltantes or shutil.which("flatpak-spawn") is None:
        return
    python = python_del_anfitrion(raiz)
    print(f"Terminal dentro del sandbox Flatpak de {app} (sin {', '.join(faltantes)}): "
          f"se ejecuta en el sistema con {python}.", file=sys.stderr, flush=True)
    os.execvp("flatpak-spawn", ["flatpak-spawn", "--host", "--watch-bus", f"--directory={raiz}",
                                python, str(raiz / "main.py"), *argumentos])

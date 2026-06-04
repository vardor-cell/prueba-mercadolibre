"""prueba-mercadolibre file for ensuring the package is executable
as `prueba-mercadolibre` and `python -m prueba_mercadolibre`
"""
import sys
from pathlib import Path
from typing import Any

from kedro.framework.cli.utils import find_run_command
from kedro.framework.project import configure_project


def main(*args, **kwargs) -> Any:
    """Punto de entrada del proyecto: configura el package de Kedro y delega en el
    comando ``run`` del CLI. Permite ejecutar el proyecto como ``prueba-mercadolibre``
    o ``python -m prueba_mercadolibre``."""
    package_name = Path(__file__).parent.name
    configure_project(package_name)

    interactive = hasattr(sys, 'ps1')
    kwargs["standalone_mode"] = not interactive

    run = find_run_command(package_name)
    return run(*args, **kwargs)


if __name__ == "__main__":
    main()

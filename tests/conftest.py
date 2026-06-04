"""Fixtures compartidas para los tests."""
from pathlib import Path

import pytest
from kedro.config import OmegaConfigLoader

CONF = str(Path(__file__).resolve().parents[1] / "conf")


@pytest.fixture(scope="session")
def params() -> dict:
    """Parámetros reales del modelo, cargados desde conf/ (sin credenciales)."""
    loader = OmegaConfigLoader(conf_source=CONF, base_env="base", default_run_env="local")
    return loader["parameters"]["risk_scoring"]

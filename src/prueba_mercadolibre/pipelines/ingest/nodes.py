"""Ingest pipeline nodes.

Sube los CSV raw locales (data/01_raw/) a BigQuery. Cada nodo es un passthrough:
lee el CSV local (input) y lo devuelve tal cual para que Kedro lo guarde en la
tabla de BigQuery correspondiente (output del catálogo → GBQTableDataset).
"""
import pandas as pd


def passthrough(df: pd.DataFrame) -> pd.DataFrame:
    """Devuelve el DataFrame sin cambios (el upload lo hace el catálogo destino)."""
    return df

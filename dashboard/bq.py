"""Acceso a BigQuery para el dashboard de risk profiling.

Lee EN VIVO las tablas que produce el pipeline Kedro:
  - `l5_risk_scores`   → score final, categoría, señales e ingredientes por usuario
  - `l3_user_features` → features de comportamiento (para la comparativa vs peer group)

Reutiliza el mismo patrón de credenciales con fallback que la API (env var
`GCP_SA_KEY` en prod / archivo local en dev), de modo que el dashboard corre con
las mismas credenciales que el resto del proyecto, sin configuración extra.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account

DATASET = "risk_profiling"
SCORES_TABLE = "l5_risk_scores"
FEATURES_TABLE = "l3_user_features"

# Ruta a la llave local (dev). En el contenedor se monta en conf/local/.
_LOCAL_KEY = Path(__file__).resolve().parent.parent / "conf" / "local" / "gcp-key.json"


def _load_credentials():
    """Credenciales con fallback: env var GCP_SA_KEY (prod) o archivo local (dev)."""
    raw = os.environ.get("GCP_SA_KEY")
    if raw:
        info = json.loads(raw)
        creds = service_account.Credentials.from_service_account_info(info)
        return creds, info["project_id"]

    key_path = os.environ.get("GCP_KEY_PATH", str(_LOCAL_KEY))
    if Path(key_path).exists():
        creds = service_account.Credentials.from_service_account_file(key_path)
        project = json.loads(Path(key_path).read_text())["project_id"]
        return creds, project

    raise RuntimeError(
        "No hay credenciales: definí GCP_SA_KEY o colocá conf/local/gcp-key.json"
    )


@lru_cache(maxsize=1)
def _client() -> bigquery.Client:
    """Cliente de BigQuery (cacheado). El project sale de GCP_PROJECT_ID o, en su
    defecto, del project_id de la llave."""
    creds, key_project = _load_credentials()
    project = os.environ.get("GCP_PROJECT_ID", key_project)
    return bigquery.Client(project=project, credentials=creds)


def _table_fqn(table: str) -> str:
    """Nombre totalmente calificado de una tabla del dataset, con backticks."""
    return f"`{_client().project}.{DATASET}.{table}`"


def _query_df(sql: str) -> pd.DataFrame:
    """Ejecuta una query y devuelve un DataFrame.

    Construye el frame fila a fila (sin `to_dataframe`) para no exigir db-dtypes /
    pyarrow como dependencia extra del dashboard.
    """
    rows = _client().query(sql).result()
    return pd.DataFrame([dict(r) for r in rows])


def load_scores() -> pd.DataFrame:
    """Tabla de scores (`l5_risk_scores`) completa, con `top_signals` ya parseado
    de JSON a lista de strings."""
    df = _query_df(
        f"""
        SELECT user_id, score, category, top_signals,
               base_score, rule_score, anomaly_score, impact,
               department, role, user_type, status
        FROM {_table_fqn(SCORES_TABLE)}
        """
    )

    def _parse_signals(raw) -> list:
        """top_signals viene como string JSON; lo convertimos a lista (o [] si falla)."""
        try:
            return json.loads(raw) if raw else []
        except (json.JSONDecodeError, TypeError):
            return []

    if not df.empty:
        df["top_signals"] = df["top_signals"].apply(_parse_signals)
    return df


def load_features() -> pd.DataFrame:
    """Subconjunto de features de comportamiento (`l3_user_features`) usado en la
    comparativa contra el peer group."""
    return _query_df(
        f"""
        SELECT user_id, total_accesses, distinct_resources, perm_count,
               z_volume_peers, after_hours_ratio, exfil_ratio
        FROM {_table_fqn(FEATURES_TABLE)}
        """
    )

"""Acceso a BigQuery para la API de risk scoring.

Carga las credenciales con fallback (env var en Render, archivo local en dev) y
expone funciones para consultar la tabla de scores. Las queries son parametrizadas.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from google.cloud import bigquery
from google.oauth2 import service_account

DATASET = "risk_profiling"
TABLE = "l5_risk_scores"
VALID_CATEGORIES = {"LOW", "MEDIUM", "HIGH", "VERY_HIGH"}

# Ruta a la llave local (dev). En el contenedor se monta en conf/local/.
_LOCAL_KEY = Path(__file__).resolve().parent.parent / "conf" / "local" / "gcp-key.json"


def _load_credentials():
    """Credenciales con fallback: env var GCP_SA_KEY (Render) o archivo local (dev)."""
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
    """Devuelve un cliente de BigQuery (cacheado). El project sale de GCP_PROJECT_ID
    o, en su defecto, del project_id de la llave."""
    creds, key_project = _load_credentials()
    project = os.environ.get("GCP_PROJECT_ID", key_project)
    return bigquery.Client(project=project, credentials=creds)


def _table_fqn() -> str:
    """Nombre totalmente calificado de la tabla de scores, con backticks para SQL."""
    return f"`{_client().project}.{DATASET}.{TABLE}`"


def _row_to_dict(row) -> dict:
    """Normaliza una fila de BQ a la forma de respuesta de la API."""
    signals = row.get("top_signals")
    try:
        signals = json.loads(signals) if signals else []
    except (json.JSONDecodeError, TypeError):
        signals = []
    return {
        "user_id": row["user_id"],
        "score": float(row["score"]),
        "category": row["category"],
        "top_signals": signals,
    }


def get_user_risk(user_id: str) -> dict | None:
    """Devuelve el risk de un usuario, o None si no existe."""
    sql = f"""
        SELECT user_id, score, category, top_signals
        FROM {_table_fqn()}
        WHERE user_id = @user_id
        LIMIT 1
    """
    cfg = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("user_id", "STRING", user_id)]
    )
    rows = list(_client().query(sql, job_config=cfg).result())
    return _row_to_dict(rows[0]) if rows else None


def list_users(category: str | None, limit: int) -> list[dict]:
    """Lista usuarios ordenados por score desc, opcionalmente filtrados por categoría."""
    where = "WHERE category = @category" if category else ""
    sql = f"""
        SELECT user_id, score, category, top_signals
        FROM {_table_fqn()}
        {where}
        ORDER BY score DESC
        LIMIT @limit
    """
    params = [bigquery.ScalarQueryParameter("limit", "INT64", limit)]
    if category:
        params.append(bigquery.ScalarQueryParameter("category", "STRING", category))
    cfg = bigquery.QueryJobConfig(query_parameters=params)
    return [_row_to_dict(r) for r in _client().query(sql, job_config=cfg).result()]

"""API REST de risk scoring — consulta los scores desde BigQuery.

Endpoints:
  GET /users/{user_id}/risk        → risk de un usuario
  GET /users?category=&limit=      → ranking por score desc, opcional por categoría
  GET /health                      → status
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

import bq

app = FastAPI(
    title="User Risk Profiling API",
    description="Expone el risk score por usuario calculado por el pipeline (datos en BigQuery).",
    version="1.0.0",
)


class RiskResponse(BaseModel):
    user_id: str
    score: float
    category: str
    top_signals: list[str]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/users/{user_id}/risk", response_model=RiskResponse)
def user_risk(user_id: str) -> dict:
    result = bq.get_user_risk(user_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Usuario '{user_id}' no encontrado")
    return result


@app.get("/users", response_model=list[RiskResponse])
def users(
    category: str | None = Query(
        default=None, description="Filtrar por categoría: LOW, MEDIUM, HIGH, VERY_HIGH"
    ),
    limit: int = Query(default=10, ge=1, le=500, description="Máximo de usuarios a devolver"),
) -> list[dict]:
    if category is not None:
        category = category.upper()
        if category not in bq.VALID_CATEGORIES:
            raise HTTPException(
                status_code=422,
                detail=f"category inválida. Usá una de: {sorted(bq.VALID_CATEGORIES)}",
            )
    return bq.list_users(category, limit)

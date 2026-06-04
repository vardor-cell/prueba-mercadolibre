# Risk Profiling API

API REST (FastAPI) que expone el risk score por usuario. Consulta en vivo la tabla
`risk_profiling.l5_risk_scores` de BigQuery (la genera el pipeline de Kedro).

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/users/{user_id}/risk` | Risk de un usuario (404 si no existe) |
| GET | `/users?category=HIGH&limit=10` | Ranking por score desc, opcional por categoría |
| GET | `/health` | Status |
| GET | `/docs` | Swagger UI (automático de FastAPI) |

Respuesta:
```json
{"user_id": "USR0042", "score": 87.4, "category": "HIGH",
 "top_signals": ["R1: ...", "ML: ...", "Impact: ..."]}
```

## Correr local (Docker Compose, desde la raíz del repo)

```bash
docker compose up --build api          # API en http://localhost:8000
curl localhost:8000/users/USR0010/risk
curl "localhost:8000/users?category=VERY_HIGH&limit=5"
```

Requiere `conf/local/gcp-key.json` (se monta como volumen). El loader usa
`GCP_KEY_PATH` (seteado en docker-compose) o cae a `conf/local/gcp-key.json`.

## Correr local (sin Docker)

```bash
pip install -r api/requirements.txt
cd api && uvicorn main:app --reload     # usa conf/local/gcp-key.json automáticamente
```

## Credenciales

El loader (`bq.py`) busca, en orden:
1. Env var `GCP_SA_KEY` (contenido JSON completo) — usado en Render.
2. Archivo en `GCP_KEY_PATH` o `conf/local/gcp-key.json` — dev local.

## Deploy en Render (free, sin tarjeta)

1. Cuenta en [render.com](https://render.com) (login con GitHub).
2. **New → Blueprint** → seleccionar el repo. Render lee `render.yaml` (raíz).
3. Setear el secreto **`GCP_SA_KEY`** = contenido del `gcp-key.json`.
4. Deploy → URL pública. Cada push que toque `api/` redespliega solo.

> Nota: en el plan free, el servicio se duerme tras 15 min inactivo (primera request
> luego ~30-60s de cold start).

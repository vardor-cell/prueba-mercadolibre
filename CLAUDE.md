# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Qué es

Sistema de **User Risk Profiling (UEBA)**: calcula un risk score por usuario combinando reglas
deterministas + ML no supervisado. Pipeline en **Kedro 1.4**, datos en **BigQuery** (Sandbox),
API en **FastAPI** desplegada en Render, orquestación con GitHub Actions. Idioma del proyecto:
español (docstrings, comentarios y docs).

## Comandos

> Atajos: `make help` lista todos los targets (`install`, `full`, `pipeline`, `api`,
> `dashboard`, `test`, `docker`…). **Requirements:** `requirements.txt` es el core
> (pipeline + notebooks) y lo usa la imagen Docker del pipeline → liviano, sin FastAPI/
> Streamlit. `requirements-dev.txt` (`-r` de core + api/ + dashboard/) arma un entorno
> local único con TODO → lo instala `make install`.

```bash
# Pipeline (lee/escribe BigQuery — requiere conf/local/gcp-key.json)
kedro run                          # proceso completo SIN ingesta (default)
kedro run --pipeline=ingest        # sube los CSV locales de data/01_raw a BQ
kedro run --pipeline=full          # ingesta + proceso completo
kedro run --tags=train             # solo entrenar el modelo
kedro run --tags=score             # solo inferencia

# Tests
pytest                             # todo
pytest -m "not integration"        # solo unitarios (sin red ni BQ)
pytest -m integration              # solo contra la API productiva (Render)
pytest tests/test_risk_scoring.py::test_access_without_permission_fires_r1   # un test

# API local
cd api && uvicorn main:app --reload      # http://localhost:8000 ( /docs = Swagger )

# Dashboard local (Streamlit, bonus track)
streamlit run dashboard/app.py           # http://localhost:8501

# Docker (kedro + api + dashboard juntos)
docker compose up --build                # rebuild OBLIGATORIO tras cambiar código
docker compose up --build dashboard      # solo el dashboard → http://localhost:8501
docker compose run --rm kedro kedro run --pipeline=ingest
```

## Credenciales y configuración

- **`conf/local/gcp-key.json`** (gitignored) — service account de BigQuery. Sin esto nada que
  toque BQ funciona. La provee el dueño del repo.
- **`conf/base/globals.yml`** — `gcp.project` (versionado, no es secreto) y `gcp.dataset`.
- Todo `conf/local/**` está gitignored (excepto `.gitkeep`). En CI/Render el secret `GCP_SA_KEY`
  recrea el archivo en runtime. Los CSV de `data/` también están gitignored.

## Arquitectura

### Flujo de datos — capas en BigQuery
Todo vive en el dataset `risk_profiling`, con prefijo de capa para agruparse en la consola:
`l1_*` raw → `l2_*` intermediate (limpieza) → `l3_*` primary (features) → `l4_*` model_input
(reglas/ML/impacto) → `l5_*` output (`l5_risk_scores`). El catálogo (`conf/base/catalog.yml`)
mapea cada dataset Kedro a su tabla GBQ vía un anchor YAML `_gbq` + globals.

### Pipelines (auto-descubiertos por `find_pipelines`)
- `ingest` — sube CSV locales (`*_local`, CSVDataset) a las tablas raw de BQ. Nodos passthrough.
- `data_processing` — limpia los 3 raw (l1→l2).
- `risk_scoring` — features → reglas → ensemble ML → impacto → score final (l2→l5).

**`pipeline_registry.py` es custom:** saca `ingest` del `__default__` (por eso `kedro run` NO
ingesta) y agrega `full` (ingesta + todo). Edita ahí si cambian estas reglas.

### El modelo (`pipelines/risk_scoring/nodes.py`)
Fórmula final: `score = clip(rule_score[0-60] + anomaly_score[0-40], 0, 100) × (0.7 + 0.3·impacto)`.
Override: usuario Inactive con accesos (regla R2) → categoría VERY_HIGH, score ≥ 85.
- **Capa 1** `compute_hard_rule_scores`: 7 reglas deterministas (R1–R7), pesos sumados (cap 60).
- **Capa 2** `train_anomaly_ensemble` + `score_anomaly_ensemble`: ensemble de **Isolation Forest +
  LOF + Z-score**. **Solo el IF se persiste** (`data/06_models/anomaly_ensemble.pkl`, local — BQ no
  guarda binarios); LOF y Z-score son transductivos y se recalculan al puntuar.
- **Impacto** `compute_impact_factor`: blast radius por criticidad de recursos (multiplica, no domina).
- `combine_and_categorize`: junta todo, aplica umbrales y genera `top_signals` (reglas + features ML).
- Toda la justificación del modelo está en **`docs/MODELO_RIESGO.md`**.

### API (`api/`)
Standalone (deps propias en `api/requirements.txt`, su propio Dockerfile). `bq.py` consulta
`l5_risk_scores` en vivo con queries parametrizadas; carga credenciales con fallback (env var
`GCP_SA_KEY` en prod / archivo local en dev). `main.py` expone `GET /users/{id}/risk`,
`GET /users?category=&limit=`, `/health`.

### Dashboard (`dashboard/`)
Standalone (deps propias en `dashboard/requirements.txt`, su propio Dockerfile), **Streamlit +
Plotly**. Cubre el bonus track: distribución por categoría, top 10 con señales, comparativa vs
peer group (mismo dept+rol). `bq.py` lee en vivo `l5_risk_scores` (scores) y `l3_user_features`
(comportamiento) con el mismo fallback de credenciales que la API; construye DataFrames fila a
fila (sin `to_dataframe`) para no exigir db-dtypes/pyarrow. `app.py` agrega el dir del script a
`sys.path` para que `import bq` no choque con el directorio `data/` de la raíz. Caché de 5 min
(`st.cache_data`). Smoke test: `streamlit.testing.v1.AppTest`.

## Gotchas

- **Nombres de tabla no pueden empezar con dígito.** La query de lectura de `GBQTableDataset` no
  usa backticks, por eso las capas usan prefijo `l1_`…`l5_` (no `01_`).
- **`contamination` del Isolation Forest no afecta el ranking** (se cancela en la normalización
  min-max). No perder tiempo tuneándolo.
- **Tras cambiar código, `docker compose build`** — el código se copia a la imagen (data y
  credenciales van por volumen, esos no requieren rebuild).
- **Tablas del Sandbox expiran a 60 días** — la corrida programada las refresca.
- Notebooks (`notebooks/`) son entregables del análisis; no requieren las convenciones del código
  fuente (docstrings, etc.), pero el código de `src/` y `api/` sí.

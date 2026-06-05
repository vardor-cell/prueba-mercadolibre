# Risk Profiling Dashboard

Dashboard interactivo (Streamlit + Plotly) que lee **en vivo** desde BigQuery
(`risk_profiling.l5_risk_scores` y `l3_user_features`, generadas por el pipeline Kedro).
Cubre el **bonus track** del challenge:

1. **Distribución de usuarios por categoría de riesgo** (+ histograma del score).
2. **Top 10 usuarios más críticos** con sus señales explicativas desplegables.
3. **Comparativa de comportamiento vs. peer group** (mismo departamento + rol).

Más KPIs arriba (total de usuarios, % HIGH+, score máximo) y filtros por departamento /
tipo de usuario en la barra lateral.

## Correr local (un comando, desde la raíz del repo)

```bash
pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py            # abre http://localhost:8501
```

Requiere `conf/local/gcp-key.json` (lo encuentra automáticamente) y que el pipeline ya
haya poblado las tablas (`kedro run`).

## Correr con Docker Compose (desde la raíz del repo)

```bash
docker compose up --build dashboard       # http://localhost:8501
```

Monta `conf/local/` como volumen de solo lectura, igual que la API.

## Credenciales

Mismo loader con fallback que la API (`bq.py`), en orden:
1. Env var `GCP_SA_KEY` (contenido JSON completo) — entornos cloud.
2. Archivo en `GCP_KEY_PATH` o `conf/local/gcp-key.json` — dev local.

## Notas

- Los datos se cachean **5 minutos** (`st.cache_data`) para no golpear BigQuery en cada
  interacción. Para ver datos nuevos, recorré el pipeline y recargá la página.
- El **peer group** de la comparativa siempre se calcula sobre la población completa,
  independientemente de los filtros de la barra lateral, para que el análisis de un
  usuario no dependa de lo que esté mirando el analista.

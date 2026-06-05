# Makefile — atajos para correr el proyecto localmente (un comando por tarea).
# Requiere: los 3 CSV del challenge en data/01_raw/ y conf/local/gcp-key.json
# (+ conf/local/credentials.yml). Ver README → "Reproducir desde cero".
#
# Uso:  make <target>     ·     make help  (lista todo)

.DEFAULT_GOAL := help
.PHONY: help install install-core ingest pipeline full train score api dashboard test test-all docker docker-down lint clean

help:  ## Muestra esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install:  ## Instala TODO en un solo entorno (pipeline + notebooks + API + dashboard)
	pip install -r requirements-dev.txt

install-core:  ## Instala solo el core (pipeline + notebooks), sin API ni dashboard
	pip install -r requirements.txt

ingest:  ## Sube los CSV de data/01_raw a BigQuery (carga inicial)
	kedro run --pipeline=ingest

pipeline:  ## Corre el proceso completo SIN ingesta (lee raw de BQ → escribe scores)
	kedro run

full:  ## Ingesta + proceso completo (todo de una)
	kedro run --pipeline=full

train:  ## Solo entrena el modelo de anomalía
	kedro run --tags=train

score:  ## Solo inferencia (scoring)
	kedro run --tags=score

api:  ## Levanta la API REST → http://localhost:8000  (/docs = Swagger)
	cd api && uvicorn main:app --reload

dashboard:  ## Levanta el dashboard Streamlit → http://localhost:8501
	streamlit run dashboard/app.py

test:  ## Tests unitarios (sin red ni BigQuery)
	pytest -m "not integration"

test-all:  ## Todos los tests (incluye integración contra la API productiva)
	pytest

docker:  ## Build + levanta pipeline + API + dashboard en Docker
	docker compose up --build

docker-down:  ## Baja los contenedores de Docker
	docker compose down

clean:  ## Limpia caches de Python y pytest
	find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache

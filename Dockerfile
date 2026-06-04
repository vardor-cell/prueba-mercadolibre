FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# 1) Dependencias primero (mejor cache de capas Docker)
COPY requirements.txt .
RUN pip install -r requirements.txt

# 2) Código del proyecto.
#    conf/local (credenciales) y data/ se montan como volúmenes en runtime,
#    NO se copian a la imagen → los secretos nunca quedan dentro del contenedor.
COPY pyproject.toml ./
COPY src/ ./src/
COPY conf/base/ ./conf/base/

# Kedro espera que conf/local y data/ existan (se sobrescriben con los volúmenes).
RUN mkdir -p conf/local data/06_models

# Por defecto corre el pipeline completo contra BigQuery.
CMD ["kedro", "run"]

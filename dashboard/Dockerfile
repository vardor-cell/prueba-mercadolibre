FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8501

# Shell form para expandir $PORT (si el host lo inyecta; en local cae a 8501).
CMD streamlit run app.py --server.port ${PORT:-8501} --server.address 0.0.0.0

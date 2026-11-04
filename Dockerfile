# Imagen propia, siguiendo la práctica: Python slim, versiones fijas y usuario no root.
FROM python:3.12.8-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MLFLOW_ENABLE_ARTIFACTS_PROGRESS_BAR=false \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && pip check

RUN groupadd --gid 10001 appgroup \
    && useradd --uid 10001 --gid appgroup --create-home appuser \
    && mkdir -p /mlflow /app/data /app/artifacts \
    && chown -R appuser:appgroup /app /mlflow

COPY --chown=appuser:appgroup src/ src/
COPY --chown=appuser:appgroup scripts/probar_servicio.py scripts/probar_servicio.py
USER 10001:10001
EXPOSE 8000 5000

CMD ["python", "-m", "uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]

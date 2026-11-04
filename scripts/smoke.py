"""Prueba integrada aislada con datos sintéticos; no toca el Registry desplegado."""

import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from src.api import crear_app
from src.entrenar import entrenar


def main():
    with TemporaryDirectory() as temporal:
        raiz = Path(temporal)
        os.environ["MLFLOW_TRACKING_URI"] = f"sqlite:///{(raiz / 'mlflow.db').as_posix()}"
        os.environ.pop("MODEL_VERSION_EXPECTED", None)
        datos = raiz / "temperatura.csv"
        pd.DataFrame({"timestamp": pd.date_range("2020-01-01", periods=1200, freq="h", tz="UTC"),
                      "temperatura": 25 + np.sin(np.arange(1200) / 24)}).to_csv(datos, index=False)
        resumen, _, _ = entrenar(datos, salida=raiz)
        assert len(resumen["runs"]) == 6
        with TestClient(crear_app()) as api:
            assert api.get("/health/ready").status_code == 200
            respuesta = api.post("/predecir", json={"hora": "2020-03-01T06:00:00Z", "temperaturas": [25] * 6})
            assert respuesta.status_code == 200, respuesta.text
            assert respuesta.json()["run_id"] == resumen["mejor_run_id"]
            assert api.post("/predecir", json={}).status_code == 422
        print("SMOKE OK: seis runs, Registry, artefacto descargado, API y entrada invalida.")


if __name__ == "__main__":
    main()

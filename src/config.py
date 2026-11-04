"""Rutas y configuración compartida del laboratorio."""

import json
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DATOS = RAIZ / "data/temperatura.csv"
MODELO = "colmena-temperatura-1h"
FEATURES = ["temperatura_actual", "temperatura_hace_1h", "temperatura_hace_2h", "media_6h"]


def guardar_json(ruta, contenido):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(contenido, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def conectar_mlflow():
    import mlflow
    (RAIZ / "artifacts").mkdir(exist_ok=True)
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", f"sqlite:///{(RAIZ / 'artifacts/mlflow.db').as_posix()}"))

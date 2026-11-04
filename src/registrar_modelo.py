"""Registro y carga por alias; no se cargan archivos joblib independientes."""

import argparse
import json
import os
from tempfile import TemporaryDirectory

import mlflow
import mlflow.sklearn

from src.config import MODELO, FEATURES, conectar_mlflow


def registrar(run_id, alias="candidate"):
    conectar_mlflow()
    version = mlflow.register_model(f"runs:/{run_id}/modelo", MODELO)
    mlflow.MlflowClient().set_registered_model_alias(MODELO, alias, version.version)
    return str(version.version)


def cargar_modelo(alias="champion"):
    conectar_mlflow()
    version = mlflow.MlflowClient().get_model_version_by_alias(MODELO, alias)
    esperada = os.getenv("MODEL_VERSION_EXPECTED")
    if esperada and str(version.version) != esperada:
        raise ValueError(f"El alias resuelve v{version.version}, pero el despliegue exige v{esperada}.")
    modelo = mlflow.sklearn.load_model(f"models:/{MODELO}/{version.version}")
    with TemporaryDirectory() as temporal:
        archivo = mlflow.artifacts.download_artifacts(run_id=version.run_id,
                                                       artifact_path="metadatos.json", dst_path=temporal)
        with open(archivo, encoding="utf-8") as f:
            meta = json.load(f)
    if meta["features"] != FEATURES:
        raise ValueError("El modelo registrado utiliza otro esquema de entradas.")
    identidad = {"modelo": MODELO, "version": str(version.version), "run_id": version.run_id}
    return modelo, identidad, meta


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    print("Versión candidata:", registrar(args.run_id))

"""Inicialización idempotente del Registry remoto para Docker y Kubernetes."""

import argparse
import json
from pathlib import Path

import mlflow

from src.config import DATOS, MODELO, conectar_mlflow
from src.entrenar import entrenar
from src.preparar_datos import preparar
from src.registrar_modelo import cargar_modelo


def inicializar(entrada, hasta):
    """Entrena una sola vez si no existe champion; después verifica su descarga."""
    conectar_mlflow()
    cliente = mlflow.MlflowClient()
    versiones = cliente.search_model_versions(f"name='{MODELO}'")
    existe = bool(versiones and cliente.get_registered_model(MODELO).aliases.get("champion"))
    if not existe:
        preparar(entrada, DATOS)
        entrenar(DATOS, hasta=hasta)
    _, identidad, _ = cargar_modelo()
    return identidad


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=Path("/entrada/temperature_schwartau.csv"))
    parser.add_argument("--hasta", default="2017-12-31T23:00:00Z")
    parser.add_argument("--informar", action="store_true", help="Solo resuelve la versión, sin entrenar.")
    args = parser.parse_args()
    if args.informar:
        _, identidad, _ = cargar_modelo()
    else:
        identidad = inicializar(args.entrada, args.hasta)
    print(json.dumps(identidad))

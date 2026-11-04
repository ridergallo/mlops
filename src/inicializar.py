"""Inicialización idempotente del Registry remoto para Docker y Kubernetes."""

import argparse
import json
from pathlib import Path

import mlflow

from src.config import MODELO, conectar_mlflow
from src.entrenar import entrenar
from src.registrar_modelo import cargar_modelo


def inicializar(entrada, hasta, actualizar_politica=False):
    """Entrena una sola vez si no existe champion; después verifica su descarga."""
    conectar_mlflow()
    cliente = mlflow.MlflowClient()
    versiones = cliente.search_model_versions(f"name='{MODELO}'")
    existe = bool(versiones and cliente.get_registered_model(MODELO).aliases.get("champion"))
    if not existe:
        entrenar(entrada, hasta=hasta)
    elif actualizar_politica:
        _, anterior, meta = cargar_modelo()
        if meta.get("politica_seleccion") != "validacion_con_persistencia_v1":
            resumen, _, _ = entrenar(entrada, hasta=hasta)
            cliente.set_registered_model_alias(MODELO, "previous", anterior["version"])
            cliente.set_registered_model_alias(MODELO, "champion", resumen["version"])
    _, identidad, _ = cargar_modelo()
    return identidad


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=Path("/entrada/temperatura.csv"))
    parser.add_argument("--hasta", default="2017-12-31T23:00:00Z")
    parser.add_argument("--informar", action="store_true", help="Solo resuelve la versión, sin entrenar.")
    parser.add_argument("--actualizar-politica", action="store_true", help="Migra el bootstrap antiguo a selección con persistencia.")
    args = parser.parse_args()
    if args.informar:
        _, identidad, _ = cargar_modelo()
    else:
        identidad = inicializar(args.entrada, args.hasta, args.actualizar_politica)
    print(json.dumps(identidad))

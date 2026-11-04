"""Reentrena ante una alarma real y compara antes de cambiar el alias champion."""

import argparse
import json
from pathlib import Path

import mlflow
import pandas as pd
from sklearn.metrics import mean_absolute_error

from src.config import DATOS, FEATURES, MODELO, RAIZ, guardar_json
from src.entrenar import entrenar
from src.features import cargar, crear_features, dividir
from src.registrar_modelo import cargar_modelo, registrar


def reentrenar(ruta, informe, promover=False, salida=None):
    if not informe.get("reentrenar"):
        return {"estado": "sin_alarma", "promovido": False}
    if informe.get("escenario") != "normal":
        raise ValueError("Las inyecciones de demostración no autorizan CT sobre etiquetas reales.")
    campeon, identidad, meta = cargar_modelo()
    if any(informe.get(k) != identidad[k] for k in ("modelo", "version", "run_id")):
        raise ValueError("La alarma pertenece a otra versión del modelo.")
    _, valid, _ = dividir(crear_features(cargar(ruta)))
    cliente = mlflow.MlflowClient()
    consumido = cliente.get_model_version(MODELO, identidad["version"]).tags.get("ct_test_fin")
    frontera = max(pd.Timestamp(meta["test_fin"]), pd.Timestamp(informe["hasta"]))
    if isinstance(consumido, str):
        frontera = max(frontera, pd.Timestamp(consumido))
    if valid.index.min() <= frontera:
        raise ValueError("Faltan datos posteriores: reservar validación y test nuevos después de la alarma.")
    # Reservar también los periodos de candidatos rechazados: no reutilizar su test.
    _, _, reservado = dividir(crear_features(cargar(ruta)))
    cliente.set_model_version_tag(MODELO, identidad["version"], "ct_test_fin", str(reservado.target_at.max()))
    resumen, _, test = entrenar(ruta, registrar_inicial=False, incluir_persistencia=False, salida=salida)
    error_anterior = float(mean_absolute_error(test.objetivo, campeon.predict(test[FEATURES])))
    aprobado = resumen["mae_test"] < min(error_anterior * 0.95, resumen["mae_persistencia_test"])
    version = registrar(resumen["mejor_run_id"], "candidate")
    decision = {"estado": "aprobado" if aprobado else "rechazado", "promovido": False,
                "mae_anterior": error_anterior, "mae_candidato": resumen["mae_test"],
                "version_anterior": identidad["version"], "version_candidata": version}
    decision.update({"run_candidato": resumen["mejor_run_id"], "mae_persistencia": resumen["mae_persistencia_test"],
                     "test_fin": str(test.target_at.max())})
    if aprobado and promover:
        cliente = mlflow.MlflowClient()
        if str(cliente.get_model_version_by_alias(MODELO, "champion").version) != identidad["version"]:
            raise ValueError("Champion cambió durante CT; repetir la comparación.")
        cliente.set_registered_model_alias(MODELO, "previous", identidad["version"])
        cliente.set_registered_model_alias(MODELO, "champion", version)
        decision["promovido"] = True
    with mlflow.start_run(run_id=resumen["mejor_run_id"]):
        mlflow.log_dict(decision, "decision_ct.json")
    return decision


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datos", type=Path, default=DATOS)
    parser.add_argument("--informe", type=Path, default=RAIZ / "artifacts/monitoreo_normal.json")
    parser.add_argument("--promover", action="store_true")
    args = parser.parse_args()
    decision = reentrenar(args.datos, json.loads(args.informe.read_text(encoding="utf-8")), args.promover)
    guardar_json(RAIZ / "artifacts/reentrenamiento.json", decision)
    print(decision)

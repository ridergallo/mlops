"""Cinco Random Forest, comparación temporal y trazabilidad con MLflow."""

import argparse
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

import mlflow
import mlflow.sklearn
import pandas as pd
from mlflow.models import infer_signature
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

from src.config import DATOS, FEATURES, MODELO, RAIZ, conectar_mlflow, guardar_json
from src.features import cargar, crear_features, dividir
from src.registrar_modelo import registrar

CONFIGURACIONES = [(50, 5), (100, 5), (100, 10), (150, 10), (150, None)]


def entrenar(ruta=DATOS, hasta=None, registrar_inicial=True):
    conectar_mlflow()
    cliente = mlflow.MlflowClient()
    nombre = "Temperatura-1h"
    if cliente.get_experiment_by_name(nombre) is None:
        destino = (RAIZ / "artifacts/runs").as_uri() if mlflow.get_tracking_uri().startswith("sqlite:") else None
        cliente.create_experiment(nombre, artifact_location=destino)
    mlflow.set_experiment(nombre)
    datos = cargar(ruta)
    if hasta:
        limite = pd.Timestamp(hasta)
        if limite.tzinfo is None:
            raise ValueError("--hasta debe incluir zona horaria, por ejemplo Z.")
        datos = datos.loc[:limite]
    train, valid, test = dividir(crear_features(datos))
    resultados, modelos = [], []
    for arboles, profundidad in CONFIGURACIONES:
        with mlflow.start_run(run_name=f"RF-{arboles}-{profundidad}") as run:
            modelo = RandomForestRegressor(n_estimators=arboles, max_depth=profundidad,
                                           min_samples_leaf=3, random_state=42, n_jobs=1)
            modelo.fit(train[FEATURES], train.objetivo)
            mae = float(mean_absolute_error(valid.objetivo, modelo.predict(valid[FEATURES])))
            baseline = float(mean_absolute_error(valid.objetivo, valid.temperatura_actual))
            mlflow.log_params({"arboles": arboles, "profundidad": profundidad, "semilla": 42})
            mlflow.log_metrics({"mae_validacion": mae, "mae_persistencia_validacion": baseline})
            mlflow.sklearn.log_model(modelo, "modelo", input_example=train[FEATURES].head(2),
                                    signature=infer_signature(train[FEATURES], train.objetivo),
                                    pip_requirements=["scikit-learn==1.5.2", "numpy==2.1.3", "pandas==2.2.3"])
            meta = {"features": FEATURES, "mae_validacion": mae, "train_fin": str(train.target_at.max()),
                    "test_inicio": str(test.index.min()), "test_fin": str(test.target_at.max()),
                    "dataset_sha256": hashlib.sha256(Path(ruta).read_bytes()).hexdigest(),
                    "filas": {"train": len(train), "valid": len(valid), "test": len(test)}}
            mlflow.log_dict(meta, "metadatos.json")
            with TemporaryDirectory() as temporal:
                archivo = Path(temporal) / "referencia.csv"
                train[FEATURES].to_csv(archivo)
                mlflow.log_artifact(str(archivo))
            resultados.append({"run_id": run.info.run_id, "mae_validacion": mae})
            modelos.append(modelo)

    orden = sorted(range(len(resultados)), key=lambda i: resultados[i]["mae_validacion"])
    ganador = resultados[orden[0]]
    modelo = modelos[orden[0]]
    mae_test = float(mean_absolute_error(test.objetivo, modelo.predict(test[FEATURES])))
    persistencia = float(mean_absolute_error(test.objetivo, test.temperatura_actual))

    with mlflow.start_run(run_id=ganador["run_id"]):
        mlflow.log_metrics({"mae_test": mae_test, "mae_persistencia_test": persistencia})
        
    resumen = {"mejor_run_id": ganador["run_id"], "runs": resultados,
               "mae_test": mae_test, "mae_persistencia_test": persistencia,
               "test_inicio": str(test.index.min()), "test_fin": str(test.target_at.max())}
    if registrar_inicial:
        # Bootstrap solo si no hay champion: entrenar de nuevo no lo reemplaza.
        versiones = cliente.search_model_versions(f"name='{MODELO}'")
        hay_campeon = bool(versiones and cliente.get_registered_model(MODELO).aliases.get("champion"))
        resumen["version_alternativa"] = registrar(resultados[orden[1]]["run_id"], "alternativa")
        alias = "candidate" if hay_campeon else "champion"
        resumen["version"] = registrar(ganador["run_id"], alias)
        resumen["alias"] = alias
    guardar_json(RAIZ / "artifacts/entrenamiento.json", resumen)
    return resumen, modelo, test


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datos", type=Path, default=DATOS)
    parser.add_argument("--hasta", help="Última hora disponible para este entrenamiento, con zona horaria.")
    args = parser.parse_args()
    resumen, _, _ = entrenar(args.datos, args.hasta)
    print(resumen)

"""Demostraciones reproducibles y aisladas; los datos de laboratorio son sintéticos."""

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mlflow
import numpy as np
import pandas as pd

from src.config import RAIZ, FEATURES, guardar_json
from src.entrenar import entrenar
from src.features import cargar, crear_features
from src.modelos import Persistencia
from src.monitorear import evaluar
from src.registrar_modelo import cargar_modelo
from src.reentrenar import reentrenar


def main():
    salida = RAIZ / "evidencias/ciclo"
    salida.mkdir(parents=True, exist_ok=True)
    # Una carpeta nueva evita reutilizar el test de una demostración anterior.
    ejecucion = RAIZ / "artifacts/demos" / pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%S%f")
    ejecucion.mkdir(parents=True)
    fechas = pd.date_range("2020-01-01", periods=6000, freq="h", tz="UTC")
    control = pd.DataFrame({"temperatura": 25 + np.sin(np.arange(1200) / 24)}, index=fechas[:1200])
    tabla = crear_features(control)
    informes = {}
    for escenario in ("normal", "datos", "concepto"):
        informe = evaluar(tabla, tabla[FEATURES], Persistencia(), 0.1, tabla.index[0], tabla.index[-1], escenario)
        alerta = informe["reentrenar"] or any(l["data_drift"] for l in informe["lotes"])
        informe.update({"procedencia": "synthetic; semilla 42", "codigo_detector": int(alerta)})
        guardar_json(salida / f"drift_{escenario}.json", informe)
        informes[escenario] = informe
        assert alerta == (escenario != "normal")
    assert informes["normal"]["lotes"][0]["ks"] == informes["concepto"]["lotes"][0]["ks"]
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4))
    for escenario, informe in informes.items():
        ax.plot([l["mae"] for l in informe["lotes"]], "o-", label=escenario)
    ax.axhline(informes["normal"]["umbral_mae"], color="red", linestyle="--", label="umbral")
    ax.set(xlabel="Semana (última pendiente)", ylabel="MAE (°C)", title="Laboratorio sintético: drift")
    ax.legend()
    fig.tight_layout()
    fig.savefig(salida / "drift.png")
    plt.close(fig)

    decisiones = {}
    for caso in ("periodico", "impredecible"):
        carpeta = ejecucion / caso
        carpeta.mkdir()
        os.environ["MLFLOW_TRACKING_URI"] = f"sqlite:///{(carpeta / 'mlflow.db').as_posix()}"
        os.environ.pop("MODEL_VERSION_EXPECTED", None)
        valores = 25 + np.sin(np.arange(6000) / 24)
        if caso == "periodico":
            valores[1200:] = 25 + 8 * np.sin(np.arange(4800) / 2)
        else:
            rng = np.random.default_rng(42)
            for i in range(1200, 6000):
                valores[i] = 25 + 0.99 * (valores[i - 1] - 25) + rng.normal(0, 1)
        ruta = carpeta / "temperatura.csv"
        pd.DataFrame({"timestamp": fechas, "temperatura": valores}).to_csv(ruta, index=False)
        entrenar(ruta, hasta=str(fechas[1199]), salida=carpeta)
        modelo, identidad, meta = cargar_modelo()
        tabla = crear_features(cargar(ruta).loc[:fechas[2208]])
        # Referencia sintética de entrenamiento, sin modificar X/y del lote observado.
        referencia = crear_features(cargar(ruta).iloc[:720])[FEATURES]
        alarma = {**identidad, **evaluar(tabla, referencia, modelo, meta["mae_validacion"], fechas[1200], fechas[2208])}
        assert alarma["reentrenar"], "El escenario debe activar la alarma antes de CT."
        guardar_json(salida / f"alarma_{caso}.json", {**alarma, "procedencia": "synthetic"})
        decision = reentrenar(ruta, alarma, promover=True, salida=carpeta)
        decision["procedencia"] = "synthetic; Registry aislado, no cambia el despliegue"
        decisiones[caso] = decision
        guardar_json(salida / f"ct_{caso}.json", decision)
        if not decision["promovido"]:
            try:
                reentrenar(ruta, alarma)
            except ValueError as error:
                decisiones[caso]["reutilizacion_test_bloqueada"] = str(error)
            else:
                raise AssertionError("No debe reutilizarse el test de un candidato rechazado.")
    guardar_json(salida / "resumen.json", decisiones)
    print(json.dumps(decisiones, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

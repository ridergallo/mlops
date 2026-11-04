"""Exporta evidencia real de MLflow, API, dataset y código, sin incluir los datos."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mlflow
import pandas as pd

from src.config import DATOS, MODELO, RAIZ, conectar_mlflow, guardar_json
from src.registrar_modelo import cargar_modelo


def main(api):
    conectar_mlflow()
    cliente = mlflow.MlflowClient()
    modelo, identidad, meta = cargar_modelo()
    experimento = cliente.get_experiment_by_name("Temperatura-1h")
    runs = cliente.search_runs([experimento.experiment_id], max_results=1000)
    versiones = cliente.search_model_versions(f"name='{MODELO}'")
    def get(ruta):
        with urllib.request.urlopen(api + ruta, timeout=15) as respuesta:
            return json.load(respuesta)
    payload = {"hora": "2018-01-01T06:00:00Z", "temperaturas": [20.1, 20.3, 20.5, 20.8, 21, 21.2]}
    req = urllib.request.Request(api + "/predecir", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as respuesta:
        prediccion = json.load(respuesta)
    assert prediccion["run_id"] == identidad["run_id"]
    try:
        urllib.request.urlopen(urllib.request.Request(api + "/predecir", data=b"{}", headers={"Content-Type": "application/json"}), timeout=15)
    except urllib.error.HTTPError as error:
        invalida = error.code
    else:
        raise AssertionError("La API aceptó una entrada inválida.")
    assert invalida == 422
    datos = pd.read_csv(DATOS)
    guardar_json(RAIZ / "evidencias/dataset.json", {
        "archivo": "data/temperatura.csv", "sha256": hashlib.sha256(DATOS.read_bytes()).hexdigest(),
        "filas": len(datos), "inicio": str(datos.timestamp.min()), "fin": str(datos.timestamp.max()),
        "horas_sin_dato": int(datos.temperatura.isna().sum()), "zona": "UTC",
        "procedencia": "CSV real Schwartau proporcionado localmente; ver docs/ENTREGA.md",
        "licencia": "Pendiente de confirmar con la fuente; dataset excluido del paquete de entrega"})
    informe = {"fecha_utc": str(pd.Timestamp.now(tz="UTC")), "tracking_uri": mlflow.get_tracking_uri(),
               "modelo": identidad, "metadatos": meta, "health": get("/health/ready"),
               "prediccion": prediccion, "entrada_invalida_status": invalida,
               "alias": cliente.get_registered_model(MODELO).aliases,
               "versiones": [{"version": v.version, "run_id": v.run_id} for v in versiones],
               "runs": [{"run_id": r.info.run_id, "nombre": r.data.tags.get("mlflow.runName"),
                         "parametros": r.data.params, "metricas": r.data.metrics} for r in runs],
               "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=RAIZ, text=True).strip(),
               "cambios_sin_commit": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=RAIZ, text=True))}
    # El HEAD no representa los cambios sin commit: guardar un hash del código real.
    huella = hashlib.sha256()
    for archivo in sorted((RAIZ / "src").glob("*")):
        if archivo.is_file():
            huella.update(archivo.name.encode())
            huella.update(archivo.read_bytes())
    informe["src_sha256"] = huella.hexdigest()
    guardar_json(RAIZ / "evidencias/entrega.json", informe)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    recientes = [r for r in runs if "mae_validacion" in r.data.metrics][:6]
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar([r.data.tags.get("mlflow.runName", r.info.run_id[:6]) for r in recientes],
           [r.data.metrics["mae_validacion"] for r in recientes])
    ax.set(ylabel="MAE validación (°C)", title="Seis ejecuciones reales de MLflow")
    fig.tight_layout()
    fig.savefig(RAIZ / "evidencias/experimentos.png")
    plt.close(fig)
    print(json.dumps({"modelo": identidad, "tipo": meta.get("tipo"), "runs": len(runs)}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:18000")
    main(parser.parse_args().api.rstrip("/"))

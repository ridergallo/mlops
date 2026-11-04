"""Replay semanal: deriva de entradas y degradación sostenida del pronóstico."""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

import mlflow
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

from src.config import DATOS, FEATURES, RAIZ, guardar_json
from src.features import cargar, crear_features
from src.registrar_modelo import cargar_modelo


def evaluar(tabla, referencia, modelo, mae_base, desde, hasta, escenario="normal"):
    """Alerta si KS D>0.20; desempeño si MAE supera umbral durante tres semanas.

    Escenarios datos/concepto son inyecciones controladas para probar detectores.
    Los p-valores KS son descriptivos: las muestras tienen dependencia temporal.
    """
    if escenario not in ("normal", "datos", "concepto"):
        raise ValueError("Escenario desconocido.")
    desde, hasta = pd.Timestamp(desde), pd.Timestamp(hasta)
    if desde.tzinfo is None or hasta.tzinfo is None or desde >= hasta:
        raise ValueError("Se requieren fechas con zona horaria y desde < hasta.")
    tabla = tabla.loc[(tabla.index >= desde) & (tabla.index <= hasta)].copy()
    if tabla.empty:
        raise ValueError("No existen muestras en el periodo solicitado.")
    if escenario == "datos":
        tabla[FEATURES] += 8
    if escenario == "concepto":
        tabla["objetivo"] += 5  # Cambia y, preserva exactamente X.
    tabla["prediccion"] = modelo.predict(tabla[FEATURES])
    tabla.loc[tabla.target_at > hasta, "objetivo"] = np.nan
    umbral = max(mae_base * 1.30, mae_base + 0.5)
    reportes, racha = [], 0
    for inicio in pd.date_range(desde, hasta, freq="7D"):
        fin = inicio + pd.Timedelta(days=7)
        lote = tabla.loc[(tabla.index >= inicio) & (tabla.index < fin)]
        maduro = fin <= hasta  # La etiqueta de la última hora llega al cierre del lote.
        suficiente = len(lote) >= 0.8 * 168
        etiquetas = lote.dropna(subset=["objetivo"])
        mae = float((etiquetas.objetivo - etiquetas.prediccion).abs().mean()) if maduro and len(etiquetas) >= 0.8 * 168 else None
        pruebas = {}
        if maduro and suficiente:
            for c in FEATURES:
                ks = ks_2samp(referencia[c], lote[c], method="asymp")
                pruebas[c] = {"D": float(ks.statistic), "p_valor_descriptivo": float(ks.pvalue)}
        racha = racha + 1 if mae is not None and mae > umbral else 0
        reportes.append({"inicio": str(inicio), "fin": str(fin), "maduro": maduro,
                         "cobertura": len(lote) / 168, "mae": mae, "ks": pruebas,
                         "data_drift": any(p["D"] > 0.20 for p in pruebas.values()),
                         "racha": racha, "alarma_desempeno": racha >= 3})
    maduros = [r for r in reportes if r["maduro"]]
    return {"desde": str(desde), "hasta": str(hasta), "escenario": escenario,
            "umbral_mae": umbral, "umbral_ks": 0.20,
            "reentrenar": bool(maduros and maduros[-1]["alarma_desempeno"]), "lotes": reportes}


def monitorear(ruta=DATOS, desde=None, hasta=None, escenario="normal"):
    modelo, identidad, meta = cargar_modelo()
    desde = pd.Timestamp(desde or meta["test_inicio"])
    hasta = pd.Timestamp(hasta or meta["test_fin"])
    if desde < pd.Timestamp(meta["test_inicio"]):
        raise ValueError("Usar un periodo posterior a la selección del modelo.")
    # Recortar ANTES de crear etiquetas: no permite consultar mediciones futuras.
    tabla = crear_features(cargar(ruta).loc[:hasta])
    with TemporaryDirectory() as temporal:
        archivo = mlflow.artifacts.download_artifacts(run_id=identidad["run_id"],
                                                       artifact_path="referencia.csv", dst_path=temporal)
        referencia = pd.read_csv(archivo)
    informe = {**identidad, **evaluar(tabla, referencia, modelo, meta["mae_validacion"], desde, hasta, escenario)}
    salida = RAIZ / f"artifacts/monitoreo_{escenario}.json"
    guardar_json(salida, informe)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot([r["mae"] if r["mae"] is not None else np.nan for r in informe["lotes"]], "o-")
    ax.axhline(informe["umbral_mae"], color="red", linestyle="--")
    ax.set(xlabel="Semana", ylabel="MAE (°C)", title=f"Desempeño: {escenario}")
    fig.tight_layout()
    fig.savefig(salida.with_suffix(".png"))
    plt.close(fig)
    return informe


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datos", type=Path, default=DATOS)
    parser.add_argument("--desde")
    parser.add_argument("--hasta")
    parser.add_argument("--escenario", choices=["normal", "datos", "concepto"], default="normal")
    args = parser.parse_args()
    informe = monitorear(args.datos, args.desde, args.hasta, args.escenario)
    alerta = informe["reentrenar"] or any(r["data_drift"] for r in informe["lotes"])
    print(f"Alerta: {alerta}; reentrenar: {informe['reentrenar']}")
    raise SystemExit(1 if alerta else 0)

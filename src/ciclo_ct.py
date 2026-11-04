"""Orquesta monitoreo y CT de un snapshot real identificado por SHA-256."""

import argparse
import hashlib
from pathlib import Path

from src.config import RAIZ, guardar_json
from src.monitorear import monitorear
from src.reentrenar import reentrenar


def ejecutar(datos, sha256, desde, hasta, promover=False):
    digest = hashlib.sha256(datos.read_bytes()).hexdigest()
    if digest != sha256.lower():
        raise ValueError("El SHA-256 no coincide con el snapshot autorizado.")
    informe = monitorear(datos, desde, hasta)
    try:
        decision = reentrenar(datos, informe, promover)
    except ValueError as error:
        if not str(error).startswith("Faltan datos posteriores"):
            raise
        decision = {"estado": "datos_pendientes", "promovido": False, "motivo": str(error)}
    decision.update({"dataset_sha256": digest, "desde": desde, "hasta": hasta})
    guardar_json(RAIZ / "artifacts/decision_ct.json", decision)
    return decision


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datos", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--desde", required=True)
    parser.add_argument("--hasta", required=True)
    parser.add_argument("--promover", action="store_true")
    args = parser.parse_args()
    print(ejecutar(args.datos, args.sha256, args.desde, args.hasta, args.promover))

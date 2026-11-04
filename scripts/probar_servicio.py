"""Peticiones independientes para medir balanceo y continuidad del Service."""

import argparse
from collections import Counter
import json
import time
from urllib.request import Request, urlopen


def probar(url, peticiones, pausa):
    cuerpo = json.dumps({"hora": "2018-01-01T06:00:00Z", "temperaturas": [20.1, 20.3, 20.5, 20.8, 21, 21.2]}).encode()
    pods, versiones, errores, latencias = Counter(), set(), [], []
    for i in range(peticiones):
        inicio = time.monotonic()
        try:
            req = Request(url.rstrip("/") + "/predecir", data=cuerpo,
                          headers={"Content-Type": "application/json", "Connection": "close"})
            with urlopen(req, timeout=5) as respuesta:
                salida = json.load(respuesta)
            pods[salida["pod"]] += 1
            versiones.add((salida["version"], salida["run_id"]))
        except Exception as error:
            errores.append({"peticion": i, "error": str(error)})
        latencias.append(round((time.monotonic() - inicio) * 1000, 2))
        time.sleep(pausa)
    return {"peticiones": peticiones, "respuestas_por_pod": dict(pods),
            "versiones_y_runs": sorted(versiones), "errores": errores,
            "latencia_max_ms": max(latencias)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://temperatura-api:8000")
    parser.add_argument("--peticiones", type=int, default=100)
    parser.add_argument("--pausa", type=float, default=0.1)
    parser.add_argument("--min-pods", type=int, default=1)
    args = parser.parse_args()
    if args.peticiones < 1 or args.pausa < 0:
        parser.error("Peticiones positivas y pausa no negativa.")
    resultado = probar(args.url, args.peticiones, args.pausa)
    print(json.dumps(resultado))
    raise SystemExit(bool(resultado["errores"]) or len(resultado["respuestas_por_pod"]) < args.min_pods)

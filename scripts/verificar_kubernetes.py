"""Guarda evidencias reales: réplicas, balanceo, autorreparación y escalado.

Solo actúa en el namespace apiario-v1 del contexto indicado. No elimina volúmenes.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time


def verificar(contexto):
    base = ["kubectl", "--context", contexto, "-n", "apiario-v1"]

    def kube(*args):
        return subprocess.check_output(base + list(args), text=True, encoding="utf-8")

    def pods():
        datos = json.loads(kube("get", "pods", "-l", "app=temperatura-api", "-o", "json"))
        return [{"nombre": p["metadata"]["name"], "uid": p["metadata"]["uid"],
                 "ready": all(c["ready"] for c in p["status"].get("containerStatuses", []))
                          and bool(p["status"].get("containerStatuses")),
                 "fase": p["status"]["phase"],
                 "imagen_id": [c.get("imageID") for c in p["status"].get("containerStatuses", [])]}
                for p in datos["items"] if not p["metadata"].get("deletionTimestamp")]

    def esperar():
        kube("rollout", "status", "deployment/temperatura-api", "--timeout=180s")

    informe = {"fecha_utc": datetime.now(timezone.utc).isoformat(), "contexto": contexto}
    salida = Path(__file__).resolve().parents[1] / "evidencias/kubernetes.json"
    salida.parent.mkdir(exist_ok=True)
    trafico = None
    try:
        esperar()
        iniciales = pods()
        assert len(iniciales) >= 3 and all(p["ready"] and p["fase"] == "Running" for p in iniciales)
        informe["replicas_iniciales"] = iniciales
        imagen = kube("get", "deployment", "temperatura-api", "-o", "jsonpath={.spec.template.spec.containers[0].image}")
        # El cliente atraviesa el Service; port-forward no se usa para medir balanceo.
        kube("delete", "pod", "cliente-pruebas", "--ignore-not-found=true")
        kube("run", "cliente-pruebas", f"--image={imagen}", "--image-pull-policy=IfNotPresent",
             "--restart=Never", "--command", "--", "python", "-c", "import time; time.sleep(900)")
        kube("wait", "--for=condition=Ready", "pod/cliente-pruebas", "--timeout=120s")
        comando = ["exec", "cliente-pruebas", "--", "python", "scripts/probar_servicio.py"]
        informe["balanceo"] = json.loads(kube(*comando, "--min-pods", "3"))

        trafico = subprocess.Popen(base + comando + ["--peticiones", "150", "--pausa", "0.1"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        time.sleep(2)
        eliminado = iniciales[0]
        kube("delete", "pod", eliminado["nombre"], "--wait=false")
        stdout, stderr = trafico.communicate(timeout=90)
        informe["trafico_durante_eliminacion"] = json.loads(stdout)
        informe["codigo_trafico"] = trafico.returncode
        # rollout puede terminar mientras un reemplazo aún no está listo: esperar explícitamente.
        limite = time.monotonic() + 120
        while time.monotonic() < limite:
            nuevos = pods()
            if len(nuevos) == len(iniciales) and all(p["ready"] for p in nuevos):
                break
            time.sleep(1)
        informe["pod_eliminado"] = eliminado
        informe["replicas_recuperadas"] = nuevos
        assert eliminado["uid"] not in {p["uid"] for p in nuevos}
        assert len(nuevos) == len(iniciales) and all(p["ready"] for p in nuevos)
        assert trafico.returncode == 0, stderr or "Se detectaron peticiones fallidas durante la eliminación."

        kube("scale", "deployment/temperatura-api", "--replicas=5")
        esperar()
        informe["escalado_cinco"] = pods()
        assert len(informe["escalado_cinco"]) == 5 and all(p["ready"] for p in informe["escalado_cinco"])
        kube("scale", "deployment/temperatura-api", "--replicas=3")
        esperar()
        informe["escalado_tres"] = pods()
        assert len(informe["escalado_tres"]) == 3 and all(p["ready"] for p in informe["escalado_tres"])

        # Una revisión de configuración demuestra rollout y retorno a la revisión previa.
        kube("set", "env", "deployment/temperatura-api", "DEMO_REVISION=2")
        esperar()
        time.sleep(5)  # Dar tiempo a la actualizacion de endpoints del Service.
        informe["rollout"] = json.loads(kube(*comando, "--peticiones", "30", "--min-pods", "2"))
        kube("rollout", "undo", "deployment/temperatura-api")
        esperar()
        time.sleep(5)
        informe["rollback"] = json.loads(kube(*comando, "--peticiones", "30", "--min-pods", "2"))
        informe["estado"] = "correcto"
    except Exception as error:
        informe["estado"] = "fallo"
        informe["error"] = str(error)
        if isinstance(error, subprocess.CalledProcessError):
            informe["salida_error"] = error.output
        raise
    finally:
        if trafico is not None and trafico.poll() is None:
            trafico.terminate()
        salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
        kube("delete", "pod", "cliente-pruebas", "--ignore-not-found=true", "--wait=false")
    print(f"Evidencia guardada en {salida}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contexto", default="docker-desktop")
    verificar(parser.parse_args().contexto)

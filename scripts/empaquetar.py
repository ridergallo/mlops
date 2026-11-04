"""Empaqueta código, documentación y evidencias; excluye datos, modelos y secretos."""

from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

raiz = Path(__file__).resolve().parents[1]
destino = raiz / "artifacts/entrega_proyecto.zip"
destino.parent.mkdir(exist_ok=True)
carpetas = ["src", "tests", "scripts", "k8s", "docs", "evidencias", ".github/workflows"]
archivos = [raiz / n for n in ["README.md", "Dockerfile", "compose.yaml", "requirements.txt", ".dockerignore", ".gitignore"]]
for carpeta in carpetas:
    archivos.extend(p for p in (raiz / carpeta).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
with ZipFile(destino, "w", ZIP_DEFLATED) as salida:
    for archivo in sorted(archivos):
        salida.write(archivo, archivo.relative_to(raiz))
print(destino)

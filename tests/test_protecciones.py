"""Protecciones de datos y versión antes de ejecutar acciones costosas."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.ciclo_ct import ejecutar
from src.registrar_modelo import cargar_modelo


class ProteccionesTest(unittest.TestCase):
    def test_snapshot_distinto_no_llega_al_monitoreo(self):
        with TemporaryDirectory() as carpeta, patch("src.ciclo_ct.monitorear") as monitor:
            ruta = Path(carpeta) / "datos.csv"
            ruta.write_text("timestamp,temperatura\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                ejecutar(ruta, "0" * 64, "2020-01-01T00:00:00Z", "2020-02-01T00:00:00Z")
            monitor.assert_not_called()

    def test_version_incorrecta_no_descarga_modelo(self):
        with patch.dict("os.environ", {"MODEL_VERSION_EXPECTED": "2"}), \
             patch("src.registrar_modelo.conectar_mlflow"), \
             patch("src.registrar_modelo.mlflow.MlflowClient") as cliente, \
             patch("src.registrar_modelo.mlflow.sklearn.load_model") as descargar:
            cliente.return_value.get_model_version_by_alias.return_value.version = "3"
            with self.assertRaisesRegex(ValueError, "exige v2"):
                cargar_modelo()
            descargar.assert_not_called()

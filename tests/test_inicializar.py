"""Verifica el uso directo del CSV preparado y la reutilizacion del Registry."""

import unittest
from pathlib import Path
from unittest.mock import patch

from src.inicializar import inicializar


class InicializarTest(unittest.TestCase):
    def test_csv_preparado_y_reutilizacion(self):
        entrada = Path("data/temperatura.csv")
        identidad = {"version": "2"}
        with patch("src.inicializar.conectar_mlflow"), \
             patch("src.inicializar.mlflow.MlflowClient") as cliente, \
             patch("src.inicializar.entrenar") as entrenar, \
             patch("src.inicializar.cargar_modelo", return_value=(None, identidad, {})):
            cliente.return_value.search_model_versions.return_value = []
            self.assertEqual(inicializar(entrada, "2017-12-31T23:00:00Z"), identidad)
            entrenar.assert_called_once_with(entrada, hasta="2017-12-31T23:00:00Z")
            entrenar.reset_mock()
            cliente.return_value.search_model_versions.return_value = ["2"]
            cliente.return_value.get_registered_model.return_value.aliases = {"champion": "2"}
            self.assertEqual(inicializar(entrada, "2017-12-31T23:00:00Z"), identidad)
            entrenar.assert_not_called()

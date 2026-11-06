"""La información expuesta debe corresponder al modelo cargado y su réplica."""

import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from sklearn.ensemble import RandomForestRegressor

from src.api import crear_app
from src.config import FEATURES
from src.modelos import Persistencia


class InformacionModeloTest(unittest.TestCase):
    def test_modelo_cargado_y_pod_sin_recargar_registry(self):
        identidad = {"modelo": "colmena-temperatura-1h", "version": "8", "run_id": "run-cargado"}
        meta = {"features": FEATURES, "tipo": "RF-100-5", "mae_validacion": 0.3}
        cargador = Mock(return_value=(RandomForestRegressor(n_estimators=100, max_depth=5), identidad, meta))
        with patch.dict("os.environ", {"POD_NAME": "temperatura-api-abc"}), TestClient(crear_app(cargador)) as api:
            for _ in range(2):
                respuesta = api.get("/modelo")
                self.assertEqual(respuesta.status_code, 200)
                datos = respuesta.json()
                self.assertEqual(datos["run_id"], "run-cargado")
                self.assertEqual(datos["pod"], "temperatura-api-abc")
                self.assertEqual(datos["caracteristicas"], FEATURES)
                self.assertEqual(datos["parametros"]["n_estimators"], 100)
            cargador.assert_called_once()

    def test_persistencia_y_hostname_fuera_de_kubernetes(self):
        with patch.dict("os.environ", {"POD_NAME": ""}), \
             patch("src.api.socket.gethostname", return_value="contenedor-api"), \
             TestClient(crear_app(lambda: (Persistencia(), {"version": "2"}, {}))) as api:
            datos = api.get("/modelo").json()
            self.assertEqual(datos["pod"], "contenedor-api")
            self.assertEqual(datos["clase"], "Persistencia")
            self.assertEqual(datos["parametros"], {})
            self.assertIsNone(datos["mae_validacion"])

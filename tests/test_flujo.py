"""Pruebas pequeñas de las decisiones que pueden afectar el pronóstico."""

import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from src.api import crear_app
from src.config import FEATURES
from src.features import crear_features, dividir, entradas_api
from src.monitorear import evaluar
from src.preparar_datos import preparar
from src.reentrenar import reentrenar


class Persistencia:
    def predict(self, x):
        return x.temperatura_actual.to_numpy()


class FlujoTest(unittest.TestCase):
    def datos(self, n=1000):
        return pd.DataFrame({"temperatura": 20 + np.sin(np.arange(n) / 24)},
                            index=pd.date_range("2020-01-01", periods=n, freq="h", tz="UTC"))

    def test_features_causales_y_paridad_api(self):
        datos = self.datos()
        antes = crear_features(datos)
        datos.iloc[500:, 0] += 10
        despues = crear_features(datos)
        pd.testing.assert_frame_equal(antes.iloc[:490][FEATURES], despues.iloc[:490][FEATURES])
        np.testing.assert_allclose(entradas_api(datos.temperatura.iloc[20:26]),
                                   despues.loc[[datos.index[25]], FEATURES])

    def test_huecos_y_purga(self):
        datos = self.datos()
        datos.iloc[20, 0] = np.nan
        tabla = crear_features(datos)
        self.assertNotIn(datos.index[25], tabla.index)
        train, valid, test = dividir(tabla)
        self.assertLess(train.target_at.max(), valid.index.min())
        self.assertLess(valid.target_at.max(), test.index.min())

    def test_agregacion_cerrada_y_hora_ambigua(self):
        with TemporaryDirectory() as tmp:
            entrada, salida = Path(tmp) / "raw.csv", Path(tmp) / "horas.csv"
            fechas = pd.date_range("2017-10-29 01:00", "2017-10-29 03:55", freq="5min")
            pd.DataFrame({"timestamp": fechas, "temperature": 20}).to_csv(entrada, index=False)
            informe = preparar(entrada, salida)
            self.assertEqual(informe["filas_descartadas"], 12)
            resultado = pd.read_csv(salida)
            self.assertEqual(pd.Timestamp(resultado.timestamp.iloc[0]), pd.Timestamp("2017-10-29T00:00:00Z"))
            self.assertGreater(resultado.temperatura.isna().sum(), 0)

    def test_api_valida_entrada_y_devuelve_version(self):
        with TestClient(crear_app(lambda: (Persistencia(), {"version": "1"}, {}))) as cliente:
            self.assertEqual(cliente.get("/").status_code, 200)
            solicitud = {"hora": "2020-01-01T06:00:00Z", "temperaturas": [20, 21, 22, 23, 24, 25]}
            respuesta = cliente.post("/predecir", json=solicitud)
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(respuesta.json()["temperatura_predicha_c"], 25)
            solicitud["temperaturas"] = [20]
            self.assertEqual(cliente.post("/predecir", json=solicitud).status_code, 422)

    def test_drift_normal_concepto_y_etiquetas_pendientes(self):
        tabla = crear_features(self.datos())
        parametros = dict(tabla=tabla, referencia=tabla, modelo=Persistencia(), mae_base=0.1,
                          desde=tabla.index[0], hasta=tabla.index[-1])
        normal = evaluar(**parametros)
        concepto = evaluar(**parametros, escenario="concepto")
        self.assertFalse(normal["reentrenar"])
        self.assertTrue(concepto["reentrenar"])
        self.assertEqual(normal["lotes"][0]["ks"], concepto["lotes"][0]["ks"])
        self.assertIsNone(concepto["lotes"][-1]["mae"])
        alterado = evaluar(**parametros, escenario="datos")
        self.assertTrue(alterado["lotes"][0]["data_drift"])

    def test_ct_no_entrena_sin_alarma_ni_con_etiquetas_simuladas(self):
        self.assertEqual(reentrenar(None, {"reentrenar": False})["estado"], "sin_alarma")
        with self.assertRaises(ValueError):
            reentrenar(None, {"reentrenar": True, "escenario": "concepto"})

    def test_ct_compara_y_promueve_solo_si_mejora(self):
        tabla = crear_features(self.datos()).dropna()
        identidad = {"modelo": "colmena-temperatura-1h", "version": "2", "run_id": "anterior"}
        informe = {**identidad, "reentrenar": True, "escenario": "normal", "hasta": "2019-01-01T00:00:00Z"}
        with patch("src.reentrenar.cargar_modelo", return_value=(Persistencia(), identidad, {"test_fin": "2018-01-01T00:00:00Z"})), \
             patch("src.reentrenar.cargar", return_value=self.datos()), \
             patch("src.reentrenar.entrenar") as entrenamiento, \
             patch("src.reentrenar.registrar", return_value="3"), \
             patch("src.reentrenar.mlflow.start_run"), \
             patch("src.reentrenar.mlflow.log_dict"), \
             patch("src.reentrenar.mlflow.MlflowClient") as cliente:
            resumen = {"mejor_run_id": "nuevo", "mae_test": 0.001, "mae_persistencia_test": 0.03}
            entrenamiento.return_value = (resumen, None, tabla)
            decision = reentrenar(None, informe)
            self.assertEqual(decision["estado"], "aprobado")
            self.assertFalse(decision["promovido"])
            cliente.return_value.set_registered_model_alias.assert_not_called()
            cliente.return_value.get_model_version_by_alias.return_value.version = "2"
            self.assertTrue(reentrenar(None, informe, promover=True)["promovido"])
            cliente.return_value.reset_mock()
            resumen["mae_test"] = 1.0
            self.assertEqual(reentrenar(None, informe, promover=True)["estado"], "rechazado")
            cliente.return_value.set_registered_model_alias.assert_not_called()


if __name__ == "__main__":
    unittest.main()

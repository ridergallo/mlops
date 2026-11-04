"""Cuatro entradas y una etiqueta futura; misma lógica en entrenamiento y API."""

import numpy as np
import pandas as pd

from src.config import FEATURES


def cargar(ruta):
    datos = pd.read_csv(ruta)
    fechas = pd.to_datetime(datos.timestamp, errors="raise")
    if fechas.dt.tz is None:
        raise ValueError("Los datos preparados deben incluir zona horaria.")
    datos["timestamp"] = fechas.dt.tz_convert("UTC")
    if datos.timestamp.duplicated().any() or not datos.timestamp.eq(datos.timestamp.dt.floor("h")).all():
        raise ValueError("Se requieren horas exactas, sin timestamps duplicados.")
    valores = pd.to_numeric(datos.temperatura, errors="raise")
    if not valores.dropna().between(-40, 80).all():
        raise ValueError("Temperatura inválida; se admiten huecos, no valores fuera de rango.")
    return datos.assign(temperatura=valores).sort_values("timestamp").set_index("timestamp").asfreq("h")


def crear_features(datos):
    """Cada fila representa un origen t. La etiqueta es la hora cerrada en t+1h."""
    temperatura = datos.temperatura
    tabla = pd.DataFrame({
        "temperatura_actual": temperatura,
        "temperatura_hace_1h": temperatura.shift(1),
        "temperatura_hace_2h": temperatura.shift(2),
        "media_6h": temperatura.rolling(6, min_periods=6).mean(),
        "objetivo": temperatura.shift(-1),
    })
    tabla["target_at"] = tabla.index + pd.Timedelta(hours=1)
    return tabla.dropna(subset=FEATURES)


def dividir(tabla):
    """Cortes cronológicos 60/20/20; purga de etiquetas en las fronteras."""
    tabla = tabla.dropna(subset=["objetivo"]).sort_index()
    if len(tabla) < 200:
        raise ValueError("Se necesitan al menos 200 muestras completas.")
    valid_inicio = tabla.index[int(len(tabla) * 0.6)]
    test_inicio = tabla.index[int(len(tabla) * 0.8)]
    train = tabla.loc[tabla.target_at < valid_inicio]
    valid = tabla.loc[(tabla.index >= valid_inicio) & (tabla.target_at < test_inicio)]
    test = tabla.loc[tabla.index >= test_inicio]
    return train, valid, test


def entradas_api(temperaturas):
    """Recibe exactamente seis medias horarias consecutivas, de antigua a reciente."""
    valores = np.asarray(temperaturas, dtype=float)
    if valores.shape != (6,) or not np.isfinite(valores).all():
        raise ValueError("Se necesitan seis temperaturas finitas.")
    return pd.DataFrame([[valores[-1], valores[-2], valores[-3], valores.mean()]], columns=FEATURES)

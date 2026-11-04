"""Limpia el CSV de Schwartau y genera medias de horas ya cerradas."""

import argparse

import pandas as pd

from src.config import DATOS, RAIZ, guardar_json


def preparar(entrada, salida=DATOS, zona="Europe/Berlin"):
    """La zona es un supuesto explícito: el CSV no incluye offset.

    Se descartan horas ambiguas del cambio estacional y fechas inexistentes.
    No se interpolan huecos. Una hora requiere al menos seis mediciones válidas.
    """
    datos = pd.read_csv(entrada, usecols=["timestamp", "temperature"])
    fechas = pd.to_datetime(datos.timestamp, errors="coerce")
    if fechas.dt.tz is None:
        fechas = fechas.dt.tz_localize(zona, ambiguous="NaT", nonexistent="NaT")
    fechas = fechas.dt.tz_convert("UTC")
    temperatura = pd.to_numeric(datos.temperature, errors="coerce")
    validas = fechas.notna() & temperatura.between(-40, 80)
    serie = pd.Series(temperatura[validas].to_numpy(), index=fechas[validas])
    # Una fecha repetida no cuenta como dos mediciones independientes.
    serie = serie.groupby(level=0).mean().sort_index()
    horas = serie.resample("h", closed="left", label="right")
    media = horas.mean().where(horas.count() >= 6)
    resultado = media.rename("temperatura").rename_axis("timestamp").reset_index()
    salida.parent.mkdir(parents=True, exist_ok=True)
    resultado.to_csv(salida, index=False)
    informe = {"archivo_origen": str(entrada), "zona_asumida": zona,
               "filas_originales": len(datos), "filas_descartadas": int((~validas).sum()),
               "horas": len(resultado), "horas_sin_dato": int(media.isna().sum()),
               "criterio": "Media horaria con >=6 mediciones; etiqueta al cierre; sin interpolación"}
    guardar_json(salida.with_suffix(".json"), informe)
    return informe


if __name__ == "__main__":
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=RAIZ.parent / "dataset/temperature_schwartau.csv")
    parser.add_argument("--salida", type=Path, default=DATOS)
    parser.add_argument("--zona", default="Europe/Berlin")
    args = parser.parse_args()
    print(preparar(args.entrada, args.salida, args.zona))

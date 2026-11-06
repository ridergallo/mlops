"""API sencilla: seis temperaturas horarias y pronóstico a una hora."""

import os
import socket
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import timedelta

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from typing import Annotated

from src.features import entradas_api
from src.registrar_modelo import cargar_modelo

Temperatura = Annotated[float, Field(ge=-40, le=80, allow_inf_nan=False)]


class Solicitud(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hora: AwareDatetime
    temperaturas: list[Temperatura] = Field(min_length=6, max_length=6,
                                           description="Seis medias horarias consecutivas, de antigua a reciente.")


def crear_app(cargador=cargar_modelo):
    @asynccontextmanager
    async def lifespan(app):
        app.state.modelo, app.state.identidad, app.state.metadatos = cargador()
        yield

    app = FastAPI(title="Temperatura de colmena a una hora", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    def interfaz():
        return Path(__file__).with_name("interfaz.html").read_text(encoding="utf-8")

    @app.get("/health")
    @app.get("/health/ready")
    def health():
        return {"estado": "ok", **app.state.identidad}

    @app.get("/health/live")
    def live():
        return {"estado": "ok"}

    @app.get("/modelo", summary="Características del modelo y pod que responde")
    def informacion_modelo():
        """Describe el modelo cargado en esta réplica, sin consultar de nuevo MLflow.

        En Kubernetes devuelve POD_NAME; fuera del clúster, el hostname.
        Cada solicitud identifica la réplica que la atendió, no todos los pods.
        """
        modelo = app.state.modelo
        meta = app.state.metadatos
        return {
            **app.state.identidad,
            "pod": os.getenv("POD_NAME") or socket.gethostname(),
            "tipo": meta.get("tipo", type(modelo).__name__),
            "clase": type(modelo).__name__,
            "parametros": modelo.get_params(deep=False),
            "objetivo": "Temperatura media de la próxima hora",
            "horizonte_horas": 1,
            "unidad": "°C",
            "observaciones_requeridas": 6,
            "caracteristicas": meta.get("features", []),
            "mae_validacion": meta.get("mae_validacion"),
            "entrenamiento": {k: meta.get(k) for k in (
                "train_fin", "test_inicio", "test_fin", "filas",
                "dataset_sha256", "politica_seleccion")},
        }

    @app.post("/predecir")
    def predecir(solicitud: Solicitud):
        if solicitud.hora.minute or solicitud.hora.second or solicitud.hora.microsecond:
            raise HTTPException(422, "hora debe corresponder al cierre de una hora exacta.")
        prediccion = float(app.state.modelo.predict(entradas_api(solicitud.temperaturas))[0])
        if not np.isfinite(prediccion):
            raise HTTPException(503, "El modelo devolvió un valor inválido.")
        return {"temperatura_predicha_c": prediccion, "hora_objetivo": solicitud.hora + timedelta(hours=1),
                **app.state.identidad, "pod": os.getenv("POD_NAME", socket.gethostname())}

    return app


app = crear_app()

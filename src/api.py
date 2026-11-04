"""API sencilla: seis temperaturas horarias y pronóstico a una hora."""

import os
import socket
from contextlib import asynccontextmanager
from datetime import timedelta

import numpy as np
from fastapi import FastAPI, HTTPException
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
        app.state.modelo, app.state.identidad, _ = cargador()
        yield

    app = FastAPI(title="Temperatura de colmena a una hora", lifespan=lifespan)

    @app.get("/health")
    @app.get("/health/ready")
    def health():
        return {"estado": "ok", **app.state.identidad}

    @app.get("/health/live")
    def live():
        return {"estado": "ok"}

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

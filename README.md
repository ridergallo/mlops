# Pronosticador de temperatura de colmenas

Proyecto final individual de MLOps. Predice la temperatura media de la próxima
hora con seis observaciones horarias consecutivas. Esta versión trabaja solo
con temperatura; humedad, presión, peso e integración IoT quedan como ampliación.

## Empezar con Docker

Desde esta carpeta, con Docker Desktop en modo Linux y `data/temperatura.csv`:

```powershell
docker compose up -d --build
```

- Interfaz: http://localhost:18000/
- API: http://localhost:18000/docs
- MLflow: http://localhost:15050

El CSV ya está preparado. El contenedor no vuelve a agregar el original.
MLflow guarda base y artefactos en un volumen persistente. La inicialización
compara cinco Random Forest y persistencia si no hay modelo registrado.

**Selección resuelta:** gana el menor MAE de validación. En el dataset real,
persistencia obtiene 0,2711 °C frente a 0,3280 °C del mejor RF, por lo que se
sirve persistencia. Los RF permanecen registrados para comparación. No se
atribuye una mejora a IA cuando la referencia sencilla funciona mejor.

## Documentación

- [Informe final en PDF](docs/informe_final/INFORME_PROYECTO_FINAL.pdf)
- [Informe editable en Word](docs/informe_final/INFORME_PROYECTO_FINAL.docx)
- [Paquete del informe y evidencias](docs/informe_final/INFORME_ENTREGA.zip)

- [Entrega, alcance, modelo, datos y defensa](docs/ENTREGA.md)
- [Docker, MLflow y Kubernetes](docs/DESPLIEGUE.md)
- [Workflows CI/CD/CT y configuración pendiente en GitHub](docs/AUTOMATIZACION.md)
- [Evidencias reales del despliegue](evidencias/entrega.json)
- [Evidencias de Kubernetes](evidencias/kubernetes.json)
- [Decisiones del laboratorio CT](evidencias/ciclo/resumen.json)

## Kubernetes

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/desplegar_kubernetes.ps1 -Imagen temperatura-mlops:1.1.1
python scripts/verificar_kubernetes.py
kubectl --context docker-desktop -n apiario-v1 port-forward service/temperatura-api 18001:8000
```

Abrir http://localhost:18001/. El despliegue utiliza tres réplicas. El script
verifica balanceo, autorreparación, escalado y actualización/rollback.
Compose y Kubernetes mantienen registros MLflow independientes.

## Ejecución Python

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

No es necesario activar el entorno: usar su ejecutable evita el bloqueo de
`Activate.ps1` en PowerShell. En los comandos siguientes, `python` representa
ese ejecutable o el entorno ya activado.

Si falta el CSV preparado, generarlo a partir del original disponible:

```powershell
python -m src.preparar_datos
python -m src.inicializar --entrada data/temperatura.csv --actualizar-politica
python -m uvicorn src.api:app --host 127.0.0.1 --port 8000
```

Sin `MLFLOW_TRACKING_URI` se utiliza MLflow local. Para consultar el servidor
Docker desde Python: `$env:MLFLOW_TRACKING_URI = 'http://127.0.0.1:15050'`.

## API

La interfaz `/` incluye un chat guiado que solicita la hora UTC y seis
temperaturas, una por mensaje, y espera confirmación antes de llamar a
`POST /predecir`. También permite editar las entradas, cargar un ejemplo,
visualizar una gráfica y consultar el historial de la sesión. No utiliza un
LLM ni servicios externos: la predicción procede del modelo MLflow de la API.
El historial se borra al recargar la página. La información de modelo disponible
puede proceder de otro pod; cada predicción muestra su propia versión, run y pod.

`GET /modelo` devuelve nombre, versión, run, tipo de modelo, parámetros,
características de entrada, MAE de validación y metadatos de entrenamiento.
Incluye `pod`, la réplica que atendió esa solicitud (hostname en Docker).
Describe el modelo cargado en memoria, aunque el alias del Registry cambie.
No enumera todos los pods del clúster. Docker: http://localhost:18000/modelo.

`POST /predecir`:

```json
{"hora":"2018-01-01T06:00:00Z","temperaturas":[20.1,20.3,20.5,20.8,21.0,21.2]}
```

La hora es el cierre de la última observación. Las seis temperaturas están
ordenadas de antigua a reciente y deben representar horas consecutivas. La
respuesta contiene °C, hora objetivo, versión, run y pod. `/health/ready`
confirma la carga del modelo; una solicitud inválida devuelve 422.

## Drift, CT y pruebas

```powershell
python -m unittest discover -s tests -v
python scripts/demostrar_ciclo.py
python -m src.monitorear --desde 2018-01-01T00:00:00Z --hasta 2018-02-01T00:00:00Z
```

El detector devuelve código 1 cuando hay alerta, no necesariamente un fallo
del programa. La demostración guarda un control verde, escenarios rojos,
un candidato aprobado y otro rechazado. Usa datos sintéticos y registros
separados; no modifica el modelo desplegado. Las etiquetas pendientes se
excluyen del MAE. CT exige periodos nuevos y bloquea reutilizar un test consumido.

## Preparar la entrega

```powershell
$env:MLFLOW_TRACKING_URI = 'http://127.0.0.1:15050'
python scripts/recopilar_entrega.py
python scripts/empaquetar.py
```

El paquete queda en `artifacts/entrega_proyecto.zip`, sin dataset ni secretos.
CI/CD/CT están implementados como workflows; su ejecución remota requiere
publicar los cambios y configurar el runner local descrito en la documentación.

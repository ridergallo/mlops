# Pronosticador de temperatura de colmenas

Proyecto final individual de MLOps. Predice la temperatura media de la próxima
hora con seis observaciones horarias consecutivas. Esta versión trabaja solo
con temperatura. Humedad, peso y flujo son ampliaciones propuestas; la presión
atmosférica y la integración directa con sensores IoT tampoco están implementadas.

## Componentes y alcance

| Componente | Función en el proyecto |
| --- | --- |
| Dataset | `data/temperatura.csv`: histórico preparado para el entrenamiento y monitoreo. |
| Modelo | Cinco configuraciones de Random Forest comparadas con persistencia. |
| MLflow | Experimentos, parámetros, métricas, artefactos, versiones y alias del modelo. |
| Docker Compose | MLflow persistente, inicialización del modelo y API con interfaz integrada. |
| Kubernetes | Tres réplicas de la API, Service, Job de inicialización y MLflow con volumen persistente. |
| Interfaz | Formulario, chat guiado, gráfica e historial de la sesión. |
| Monitoreo y CT | Detección de drift, evaluación temporal y reentrenamiento con criterios de promoción. |
| CI/CD/CT | Workflows preparados; la ejecución remota requiere configurar GitHub y el runner. |

Los datos se dividen cronológicamente en entrenamiento, validación y prueba.
Las entradas derivadas son temperatura actual, dos rezagos y media de seis
horas. Persistencia pronostica que la siguiente temperatura será igual a la
última observada.

Todos los comandos siguientes se ejecutan desde `proyecto_mlops_v1` en PowerShell.

## Empezar con Docker

Desde esta carpeta, con Docker Desktop en modo Linux y `data/temperatura.csv`:

```powershell
docker compose up -d --build
docker compose ps -a
docker compose logs inicializar
```

- Interfaz: http://localhost:18000/
- API: http://localhost:18000/docs
- MLflow: http://localhost:15050

El CSV ya está preparado. El contenedor no vuelve a agregar el original.
MLflow guarda base y artefactos en un volumen persistente. La inicialización
compara cinco Random Forest y persistencia si no hay modelo registrado.
El servicio `inicializar` termina con código 0 cuando completa su trabajo;
no necesita permanecer en ejecución. Si ya existe un modelo con la política
actual, se reutiliza. La opción de inicialización también permite migrar la
política antigua de selección.

Para detener los servicios conservando los experimentos y modelos:

```powershell
docker compose down
```

**Selección resuelta:** gana el menor MAE de validación. En el dataset real,
persistencia obtiene 0,2711 °C frente a 0,3280 °C del mejor RF, por lo que se
sirve persistencia. Los RF permanecen registrados para comparación. No se
atribuye una mejora a IA cuando la referencia sencilla funciona mejor.

## Documentación

- [Entrega, alcance, modelo, datos y defensa](docs/ENTREGA.md)
- [Docker, MLflow y Kubernetes](docs/DESPLIEGUE.md)
- [Workflows CI/CD/CT y configuración pendiente en GitHub](docs/AUTOMATIZACION.md)
- [Recomendaciones para humedad, peso y flujo](docs/RECOMENDACIONES_MULTIVARIABLE.md)
- [Evidencias reales del despliegue](evidencias/entrega.json)
- [Evidencias de Kubernetes](evidencias/kubernetes.json)
- [Decisiones del laboratorio CT](evidencias/ciclo/resumen.json)

## Kubernetes

Activar Kubernetes en Docker Desktop y comprobar que el contexto
`docker-desktop` está disponible. El script construye la imagen, despliega
MLflow, copia el CSV preparado, ejecuta la inicialización y despliega la API.
Usar una etiqueta nueva al cambiar el código para evitar reutilizar una imagen
anterior almacenada en el nodo.

```powershell
kubectl --context docker-desktop get nodes
Test-Path .\data\temperatura.csv
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/desplegar_kubernetes.ps1 -Imagen temperatura-mlops:1.1.2
kubectl --context docker-desktop -n apiario-v1 get deployments,pods,services,pvc
kubectl --context docker-desktop -n apiario-v1 port-forward service/temperatura-api 18001:8000
```

Mantener esa terminal abierta. Interfaz: http://localhost:18001/; documentación
de la API: http://localhost:18001/docs. En otra terminal, exponer MLflow:

```powershell
kubectl --context docker-desktop -n apiario-v1 port-forward service/mlflow 15051:5000
```

MLflow de Kubernetes: http://localhost:15051. Compose y Kubernetes mantienen
registros MLflow independientes; entrenar en uno no actualiza el otro.

Con las dependencias Python instaladas, generar las evidencias de la práctica:

```powershell
.\.venv\Scripts\python.exe scripts/verificar_kubernetes.py
```

Esta prueba realiza solicitudes a través del Service, elimina un pod para
comprobar autorreparación, escala a cinco réplicas y vuelve a tres; también
verifica actualización y rollback. Guarda resultados en
`evidencias/kubernetes.json`. El túnel `port-forward` permite acceder a la
interfaz, pero no demuestra por sí mismo el balanceo entre réplicas.

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

El monitoreo compara las características actuales con `referencia.csv`,
almacenado como artefacto del modelo en MLflow. Usa KS para cambios de las
entradas y MAE por ventanas temporales para deterioro de las predicciones,
cuando ya existen observaciones reales para compararlas.

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
Los reportes de monitoreo se guardan en `artifacts/`; las evidencias de la
demostración están en `evidencias/ciclo/`. Para operar CT con un nuevo snapshot,
seguir [AUTOMATIZACION.md](docs/AUTOMATIZACION.md).

## Estructura del proyecto

```text
src/                 Preparación, features, entrenamiento, API, interfaz y CT
data/                Dataset preparado
tests/               Pruebas automatizadas
scripts/             Despliegue, verificación, demostraciones y empaquetado
k8s/                 Manifiestos de Kubernetes
.github/workflows/   CI, CD y CT
docs/                Alcance, despliegue, automatización y recomendaciones
evidencias/          Resultados guardados de las verificaciones
artifacts/           Salidas locales generadas
compose.yaml         Servicios Docker Compose
Dockerfile           Imagen compartida de la solución
```

## Ampliación a otras variables

La propuesta es evolucionar hacia un único modelo multisalida que pronostique
temperatura, humedad, peso y flujo. Primero deben alinearse los datos de la
misma colmena y periodo, comprobar las unidades del peso y confirmar el
significado del flujo antes de agregarlo por hora. Cada salida tendrá métricas
y comparación con persistencia propias. Esta ampliación está documentada,
pero todavía no forma parte de la API ni del modelo actual.

## Preparar la entrega

```powershell
$env:MLFLOW_TRACKING_URI = 'http://127.0.0.1:15050'
python scripts/recopilar_entrega.py
python scripts/empaquetar.py
```

El paquete queda en `artifacts/entrega_proyecto.zip`, sin dataset ni secretos.
CI/CD/CT están implementados como workflows; su ejecución remota requiere
publicar los cambios y configurar el runner local descrito en la documentación.
Las evidencias guardadas corresponden a la fecha en que se ejecutaron las
pruebas; deben regenerarse después de un nuevo despliegue para documentar
su estado actual.

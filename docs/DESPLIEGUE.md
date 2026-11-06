# Docker, MLflow y Kubernetes

Ejecutar desde `proyecto_mlops_v1`. Requisitos: Docker Desktop con contenedores
Linux; para Kubernetes, activar el clúster local y disponer de `kubectl`.

## Dataset

El archivo de entrada es **`data/temperatura.csv`**, con columnas `timestamp`
y `temperatura`: medias horarias con zona UTC. Se monta en modo lectura.
No se incluye en la imagen ni se vuelve a procesar con `preparar_datos`.
Si falta en una copia nueva del repositorio, generarlo una vez:

```powershell
.\.venv\Scripts\python.exe -m src.preparar_datos
```

Ese paso requiere el CSV original `../dataset/temperature_schwartau.csv`.
La inicialización usa datos hasta el cierre de 2017, registra modelos si no existe
`champion` y verifica la descarga del modelo. Si ya existe, lo reutiliza.

## Docker Compose

```powershell
docker compose up -d --build
docker compose ps -a
docker compose logs inicializar
```

- MLflow: http://localhost:15050
- API y Swagger: http://localhost:18000/docs
- Disponibilidad: http://localhost:18000/health/ready

Una imagen Python se utiliza para los tres servicios. MLflow inicia primero;
después se ejecuta la inicialización y finalmente la API. El proceso utiliza
un usuario sin privilegios. Los modelos, artefactos y SQLite persisten en el
volumen `mlflow-data`. Los artefactos se descargan por HTTP desde MLflow.

```powershell
docker compose stop
docker compose start
```

`docker compose down` elimina contenedores, conservando el volumen. Agregar `-v`
eliminaría los modelos y el historial: no usarlo para un reinicio normal.

## Kubernetes local

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/desplegar_kubernetes.ps1 -Imagen temperatura-mlops:1.1.1
```

El script utiliza explícitamente el contexto `docker-desktop` y namespace
`apiario-v1`. Construye la imagen, despliega MLflow con un PVC de 5 GiB, copia
el CSV preparado, ejecuta el Job inicializador y despliega tres réplicas de API.
Configura recursos, probes y actualización gradual. Cambiar la etiqueta con
cada modificación para evitar que `IfNotPresent` reutilice imágenes anteriores.
En otros clústeres se necesita publicar la imagen en un registro accesible y
adaptar almacenamiento y exposición del servicio.

El Service publica el NodePort 30080. Si Docker Desktop no lo expone en
localhost, abrir una terminal con:

```powershell
kubectl --context docker-desktop -n apiario-v1 port-forward service/temperatura-api 18001:8000
```

API mediante el túnel: http://localhost:18001/docs. Para consultar MLflow:

```powershell
kubectl --context docker-desktop -n apiario-v1 port-forward service/mlflow 15051:5000
```

Abrir http://localhost:15051. Mantener esa terminal abierta.
Compose y Kubernetes tienen almacenes independientes: las versiones y los
identificadores de ejecución pertenecen a su servidor respectivo. No se copia
la base SQLite de Windows, que puede contener rutas locales incompatibles.

## Verificación

```powershell
python scripts/verificar_kubernetes.py
```

Guarda `evidencias/kubernetes.json`: peticiones atravesando el Service, pods que
respondieron, eliminación y sustitución de un pod durante tráfico, escalado
3 → 5 → 3, actualización de configuración y rollback. Esta última prueba no
cambia el modelo: comprueba las revisiones del Deployment.

La API carga el modelo al iniciar. `MODEL_VERSION_EXPECTED` comprueba que el
alias corresponde a la versión prevista en `modelo-desplegado`. Después de
promover un modelo, volver a ejecutar el despliegue para actualizar la ConfigMap
y reiniciar las réplicas. Para retroceder el modelo también hay que restaurar
el alias y actualizar la ConfigMap; `rollout undo` por sí solo no lo hace.

## Alcance

Se siguen los ejemplos del módulo: imagen Python, API, Deployment y Service
NodePort, añadiendo almacenamiento para MLflow y arranque ordenado.
SQLite con un único servidor MLflow y PVC local es suficiente para el laboratorio.
El servidor utiliza un proceso con cuatro hilos para que una conexión lenta
no bloquee todas las peticiones ni las comprobaciones de salud.
Las tres réplicas de API en un solo nodo no cubren la caída del nodo completo.
La selección compara cinco RF con persistencia y conserva la referencia cuando
es mejor. Ver ENTREGA.md y AUTOMATIZACION.md para resultados y CI/CD/CT.

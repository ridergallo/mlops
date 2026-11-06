# CI/CD/CT sencillo

`proyecto_mlops_v1` es la raíz de su propio repositorio Git. Los workflows están
en su `.github/workflows`, siguiendo la práctica del módulo. No copian el CSV
nuevo sobre el histórico, ni guardan modelos binarios en Git.

## CI y entrega de imagen

`ci-cd.yml` se ejecuta en pull requests, push a `main` y manualmente. Instala
dependencias, ejecuta `pip check` y tests, construye la imagen y ejecuta dentro
de ella un entrenamiento sintético aislado con Registry y llamadas a FastAPI.
El smoke verifica el artefacto real, una respuesta válida y una entrada 422.

Solo desde `main`, después de las pruebas, publica en GHCR con etiqueta SHA
del commit y guarda el digest. La CI no necesita el CSV real ni el MLflow local.
Una publicación no equivale a desplegar Kubernetes.

## CD local

GitHub no puede acceder directamente al Docker Desktop de la computadora.
`cd.yml` es un despliegue automatizado de activación manual. Requiere un runner
Windows con etiquetas `self-hosted`, `Windows`, `apiario`, Docker y kubectl con
contexto `docker-desktop`, registrado por el propietario del repositorio.

Configurar el environment `laboratorio` y variable `DATASET_PATH` como ruta
absoluta del CSV preparado, fuera de la carpeta que limpia checkout. El runner
debe tener acceso a la imagen GHCR; si es privada, iniciar sesión previamente
con permiso de lectura. No escribir tokens en los archivos del proyecto.

Ejecutar el workflow con `ghcr.io/usuario/repositorio@sha256:...`, obtenido de
la CI. Descarga esa imagen, despliega y obtiene evidencias de Kubernetes.
La activación manual mantiene la solución simple: entrega automatizada y
despliegue manualmente iniciado, no despliegue continuo desatendido.

Alternativa sin runner:

```powershell
docker pull ghcr.io/usuario/repositorio@sha256:DIGEST_REAL
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/desplegar_kubernetes.ps1 -Imagen ghcr.io/usuario/repositorio@sha256:DIGEST_REAL -OmitirConstruccion
```

## CT por snapshot

`ct.yml` se activa manualmente al disponer de un snapshot completo y nuevo.
No se configura un cron que reevalúe indefinidamente el mismo histórico. Usa
el mismo runner y `DATASET_PATH`; configurar además `MLFLOW_TRACKING_URI`.
Para Compose es `http://127.0.0.1:15050`. Para Kubernetes mantener un túnel a
MLflow y utilizar `http://127.0.0.1:15051`. Elegir el Registry que se desea operar.

Inputs: SHA-256 del CSV, fechas UTC del monitoreo y opción de promoción
(desactivada por defecto). El hash se comprueba antes de evaluar. `hasta`
debe ser anterior a la nueva validación y test del snapshot. Si aún no hay
datos suficientes, se informa `datos_pendientes` y no se entrena.

```powershell
$env:MLFLOW_TRACKING_URI = 'http://127.0.0.1:15050'
$HashDatos = (Get-FileHash data/temperatura.csv -Algorithm SHA256).Hash
python -m src.ciclo_ct --datos data/temperatura.csv --sha256 $HashDatos --desde 2018-01-01T00:00:00Z --hasta 2018-02-01T00:00:00Z
```

CT guarda la decisión y los reportes como artefactos de Actions. Una alarma
esperada no provoca un fallo permanente de CI: el script distingue alerta,
decisión y error de ejecución. La promoción se permite solo si pasan las
puertas. Después de una promoción, ejecutar CD contra el mismo Registry para
actualizar la versión esperada y reiniciar los pods; para Compose reiniciar
la API. La activación de CD posterior a CT es manual en esta versión.

## Estado de validación

Se ejecutaron localmente tests, construcción Docker, smoke integrado y
demostraciones de CT. Los archivos YAML se verifican localmente; esto no
equivale a una ejecución alojada en GitHub. No se realizó push ni se configuró
un runner en la cuenta del usuario. Quedan por ejecutar los workflows remotos
una vez versionados los cambios y configurado el entorno.

Referencias oficiales: [sintaxis de workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
y [selección de runners propios](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/use-in-a-workflow).

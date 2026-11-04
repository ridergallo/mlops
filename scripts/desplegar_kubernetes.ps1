param(
    [string]$Contexto = "docker-desktop",
    [string]$Imagen = "temperatura-mlops:1.0.0",
    [string]$Dataset = "../data/temperatura.csv",
    [switch]$OmitirConstruccion
)

# Por defecto Dataset se resuelve desde scripts/, no desde la terminal del usuario.
$ErrorActionPreference = "Stop"
$RaizProyecto = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RutaDataset = if ([System.IO.Path]::IsPathRooted($Dataset)) {
    (Resolve-Path -LiteralPath $Dataset).Path
} else { (Resolve-Path (Join-Path $PSScriptRoot $Dataset)).Path }
Set-Location $RaizProyecto

function Kube {
    if ($MyInvocation.ExpectingInput) {
        $input | & kubectl --context $Contexto @args
    } else {
        & kubectl --context $Contexto @args
    }
    if ($LASTEXITCODE -ne 0) { throw "kubectl falló: $args" }
}

function Aplicar([string]$Archivo) {
    (Get-Content $Archivo -Raw).Replace("temperatura-mlops:1.0.0", $Imagen) | Kube apply -f -
}

Kube get nodes
if (-not $OmitirConstruccion) {
    & docker build -t $Imagen .
    if ($LASTEXITCODE -ne 0) { throw "No se pudo construir la imagen." }
}

Aplicar "k8s/namespace.yaml"
Aplicar "k8s/mlflow.yaml"
Kube -n apiario-v1 rollout status deployment/mlflow --timeout=300s

# Copiar el CSV horario preparado; no migrar bases de datos con rutas Windows.
Kube -n apiario-v1 exec deployment/mlflow '--' mkdir -p /mlflow/input
$PodMlflow = Kube -n apiario-v1 get pods -l app=mlflow -o "jsonpath={.items[0].metadata.name}"
Push-Location (Split-Path $RutaDataset -Parent)
try {
    $NombreDataset = Split-Path $RutaDataset -Leaf
    Kube -n apiario-v1 cp "./$NombreDataset" "${PodMlflow}:/mlflow/input/temperatura.csv"
} finally { Pop-Location }

Kube -n apiario-v1 delete job inicializar-modelo --ignore-not-found=true
Aplicar "k8s/inicializar.yaml"
try {
    Kube -n apiario-v1 wait --for=condition=complete job/inicializar-modelo --timeout=1800s
} finally {
    Kube -n apiario-v1 logs job/inicializar-modelo
}

$SalidaModelo = Kube -n apiario-v1 exec deployment/mlflow '--' env MLFLOW_TRACKING_URI=http://mlflow:5000 python -m src.inicializar --informar
$Modelo = $SalidaModelo | ConvertFrom-Json
@{
    apiVersion = "v1"; kind = "ConfigMap"
    metadata = @{ name = "modelo-desplegado"; namespace = "apiario-v1" }
    data = @{ version = [string]$Modelo.version; run_id = [string]$Modelo.run_id }
} | ConvertTo-Json -Depth 5 | Kube apply -f -
Aplicar "k8s/deployment.yaml"
# Recargar también cuando cambió solamente el valor de la ConfigMap.
Kube -n apiario-v1 rollout restart deployment/temperatura-api
Kube -n apiario-v1 rollout status deployment/temperatura-api --timeout=300s
Kube -n apiario-v1 get 'pods,services,pvc'
Write-Host "API NodePort: 30080. Si localhost no lo expone, usar:"
Write-Host "kubectl --context $Contexto -n apiario-v1 port-forward service/temperatura-api 18001:8000"
Write-Host "API con port-forward: http://localhost:18001/docs"
Write-Host "MLflow: kubectl --context $Contexto -n apiario-v1 port-forward service/mlflow 15051:5000"

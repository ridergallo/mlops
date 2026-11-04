# Pronóstico sencillo de temperatura de colmenas

Predice la temperatura media de la próxima hora usando datos reales de
`../dataset/temperature_schwartau.csv`. Usa un Random Forest y cuatro entradas:
temperatura actual, temperatura de hace una y dos horas y promedio de seis horas.
Es un pronóstico de temperatura, no un diagnóstico de salud de la colmena.

## Archivos

| Archivo | Función |
|---|---|
| `src/preparar_datos.py` | Limpiar y convertir mediciones a medias horarias |
| `src/features.py` | Construir las cuatro entradas y la etiqueta futura |
| `src/entrenar.py` | Comparar cinco configuraciones y registrar dos versiones |
| `src/registrar_modelo.py` | Registrar candidatos y cargar el alias de MLflow |
| `src/api.py` | Recibir seis temperaturas y devolver el pronóstico |
| `src/monitorear.py` | Medir drift y error por semanas |
| `src/reentrenar.py` | Evaluar un candidato antes de sustituir al modelo |
| `src/config.py` | Rutas, nombre del modelo y cuatro columnas |

## Ejecutar

Desde `proyecto_mlops_v1`, con Python 3.12:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

.\.venv\Scripts\Activate.ps1
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1

python -m src.preparar_datos
python -m src.entrenar --hasta 2017-12-31T23:00:00Z
```

Si no activas el entorno, reemplaza `python` por `.\.venv\Scripts\python.exe`.
También puedes usar el entorno ya instalado del proyecto anterior, reemplazando
`python` por `..\proyecto_mlops\.venv\Scripts\python.exe`; el código y los artefactos
de esta versión siguen siendo independientes. Esta fue la opción usada para verificarla.

El entrenamiento usa 2017 en este ejemplo; los datos posteriores quedan disponibles
para monitoreo y CT. Sin `--hasta`, usa todo el archivo. Divide cronológicamente
60/20/20 y elimina las etiquetas que cruzan las fronteras. Selecciona por MAE de
validación y evalúa una sola vez el ganador en test, comparándolo con persistencia
(la siguiente temperatura será igual a la actual).

La primera ejecución registra `alternativa` y `champion`. Ejecuciones siguientes
registran `candidate` sin sustituir a `champion`. El campeón inicial representa la
mejor configuración de validación; revisar su comparación con persistencia antes
de atribuirle utilidad práctica. Los modelos y las referencias se guardan en MLflow.

### Ver MLflow

```powershell
python -m mlflow ui --backend-store-uri sqlite:///artifacts/mlflow.db --host 127.0.0.1 --port 5050
```

Abrir `http://127.0.0.1:5050`. La base y los artefactos son locales. Si se configura
`MLFLOW_TRACKING_URI`, usar la misma dirección en entrenamiento, API y monitoreo.

### API

```powershell
python -m uvicorn src.api:app --host 127.0.0.1 --port 8000
```

Abrir `http://127.0.0.1:8000/docs`. Ejemplo de `POST /predecir`:

```json
{
  "hora": "2018-01-01T06:00:00Z",
  "temperaturas": [20.1, 20.3, 20.5, 20.8, 21.0, 21.2]
}
```

Son seis medias horarias consecutivas, ordenadas de antigua a reciente. `hora`
corresponde al cierre de la última observación. El cliente debe respetar esa
continuidad: el contrato simple no incluye un timestamp por cada valor.
La respuesta incluye pronóstico en °C, hora objetivo, versión, run y nombre del pod.
`GET /health` devuelve el estado y la identidad del modelo cargado. Una entrada
inválida devuelve 422. Sin modelo registrado, la API no arranca.

### Monitoreo

```powershell
python -m src.monitorear
python -m src.monitorear --escenario datos
python -m src.monitorear --escenario concepto
```

Por defecto reproduce el test reservado. Para fechas nuevas, usar `--desde` y
`--hasta` con zona horaria. Los datos posteriores a `--hasta` quedan excluidos.
Guarda JSON y PNG en `artifacts/monitoreo_<escenario>.*`.

- **Data drift:** estadístico KS por cada una de las cuatro entradas; alerta si
  D supera 0,20. Es un umbral inicial de tamaño de cambio para el laboratorio,
  pendiente de calibración. El p-valor se muestra como descriptivo porque hay
  dependencia temporal. Estacionalidad normal también puede activar alertas.
- **Desempeño:** MAE mayor que `max(1,30 × MAE_validación, MAE_validación + 0,5 °C)`
  durante tres semanas consecutivas con al menos 80 % de cobertura. Espera una
  hora para la última etiqueta del lote. Un lote insuficiente interrumpe la racha.
- **Demostraciones:** `datos` desplaza X en +8 °C; `concepto` suma 5 °C a y sin
  modificar X. Son perturbaciones de prueba, no nuevas observaciones reales.

Código de salida 1 indica alerta; 0 indica ausencia de alerta. Los tests comprueban
que un escenario alterado sea detectado y por eso deben pasar aunque el detector
devuelva una alerta. `normal` significa datos sin perturbación: no garantiza
ausencia de cambios naturales. El error alto indica degradación, no demuestra por
sí solo una causa biológica.

### Reentrenar

```powershell
python -m src.reentrenar --informe artifacts/monitoreo_normal.json
```

Sin alarma no entrena. Con alarma exige validación y test nuevos posteriores al
periodo de alarma y al test previo. Registra candidato y exige mejorar al campeón
al menos 5 % y superar persistencia en el mismo test nuevo. `--promover` permite
cambiar el alias solo si aprueba; conserva `previous`. Reiniciar la API después
de promover. Ejecutar un solo CT a la vez y reservar periodos nuevos para ciclos
sucesivos. Las alarmas artificiales `datos`/`concepto` no disparan CT sobre etiquetas
reales: la perturbación no está presente en el CSV original.

## Decisiones y límites

- El CSV no indica zona horaria. Se asume `Europe/Berlin`, configurable con
  `preparar_datos --zona`. Se descartan fechas ambiguas/inexistentes del cambio
  estacional; confirmar la zona con la fuente antes de uso productivo.
- Se aceptan temperaturas entre −40 y 80 °C como control amplio de datos, no como
  rango saludable. Se requieren seis mediciones por hora y no se interpolan huecos.
- La media de 14:00–14:59 se etiqueta a las 15:00, cuando ya está disponible.
  El objetivo es la media de la hora siguiente, disponible a las 16:00.
- El monitoreo es replay del modelo actual; no es una bitácora de predicciones
  históricamente emitidas. Reconstruye las rachas sobre todo el periodo pedido.
- Este alcance implementa el flujo Python. Docker, las tres réplicas Kubernetes
  y workflows CI/CD son la siguiente fase del proyecto final. Las rutas locales
  de MLflow necesitarán un servidor de artefactos accesible desde los contenedores.
- `data/`, `artifacts/` y entornos virtuales quedan fuera de Git. No se modifican
  el dataset original, SoundHive-AI ni la implementación anterior.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

Cubren causalidad, huecos, separación temporal, horario estacional, paridad de
features entre API y entrenamiento, validación de solicitudes, drift, etiquetas
pendientes y protección frente a reentrenamiento por perturbaciones artificiales.

## Resultado verificado el 3 de noviembre de 2026

- Preparación: 253.430 registros originales; 21.120 horas, de las cuales 175
  quedaron sin dato utilizable. Se descartaron 2.080 registros inválidos o ambiguos.
- Cinco experimentos con el periodo de 2017; versiones 1 (`alternativa`) y 2
  (`champion`) registradas. Ganador: `85a048636606456d9860e0d0757b9bac`.
- MAE del modelo en test: **0,2947 °C**; persistencia: **0,1065 °C**.
  El modelo no supera esta referencia en el test. El alias champion identifica
  al candidato elegido para la demostración MLOps, no una superioridad validada.
- API verificada con TestClient y el modelo real del Registry; respuesta guardada
  en `artifacts/prediccion_ejemplo.json`.
- Replay normal: alerta de entradas, sin alarma sostenida de desempeño. Hay
  cambios naturales respecto al entrenamiento; no se forzó un resultado verde.
- Escenarios datos y concepto: alarmas detectadas. El concepto mantiene las mismas
  X del replay normal, por lo que conserva también su drift de entradas previo.
- CT real: `sin_alarma`, conservando la versión 2. Aprobación, rechazo y promoción
  se verifican con dependencias simuladas en las pruebas de decisión.
- Siete pruebas automatizadas; modelos, reportes y gráficas en `artifacts/`.

Los resultados del test ya fueron observados. Si se modifica el modelo después
de este análisis, reservar un periodo posterior como nueva evaluación final.

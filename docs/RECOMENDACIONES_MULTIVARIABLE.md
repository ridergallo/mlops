# Resumen ejecutivo: incorporación de humedad, peso y flujo

La ampliación es viable reutilizando la infraestructura actual. Se recomienda
un único modelo multisalida que pronostique temperatura, humedad, peso y flujo
para la próxima hora. El trabajo principal será preparar datos compatibles y
evaluar cada salida, sin añadir más contenedores ni proyectos independientes.

## Recomendaciones por variable

| Variable | Recomendación principal |
|---|---|
| Humedad | Validar el rango 0–100 %, tratar faltantes y construir una serie horaria. No fabricar observaciones mediante interpolación extensa. |
| Peso | Confirmar unidades y escala antes de convertir a kg; revisar valores negativos, calibraciones y cambios de manejo. El peso total no equivale a producción de miel. |
| Flujo | Confirmar qué representa cada registro y su signo. La documentación local lo describe como tránsito de abejas, pero el CSV solo tiene una columna flow y contiene valores negativos. No tratarlos automáticamente como errores. |

En flujo, sumar por hora solo sería correcto si los registros representan
conteos de intervalos no superpuestos. Si son contadores acumulados, tasas o
balances entre entradas y salidas, se necesita otra transformación. Primero
deben aclararse los timestamps repetidos y la definición del sensor.

## Ruta de implementación sencilla

1. **Unificar la procedencia.** Evaluar los archivos de Würzburg como primera
   opción, verificando que correspondan a la misma colmena y sensores compatibles.
   No unir la temperatura actual de Schwartau con variables de otra localidad.
2. **Crear un dataset conjunto.** Una fila por hora, con fecha, temperatura,
   humedad, peso y flujo. Normalizar zona horaria y unidades; conservar únicamente
   períodos con cobertura suficiente, sin inventar etiquetas faltantes.
3. **Adaptar el modelo existente.** Usar Random Forest multisalida con históricos
   de las cuatro variables. Escalar las salidas con parámetros aprendidos solo
   del entrenamiento para evitar que una magnitud domine por su escala.
4. **Evaluar por variable.** Comparar cada salida contra persistencia, usando
   cortes temporales. Informar errores por separado en °C, puntos porcentuales,
   kg y la unidad de flujo confirmada. Una mejora global no debe ocultar una
   degradación importante en una variable.
5. **Actualizar API, interfaz y monitoreo.** Recibir los cuatro históricos,
   devolver cuatro predicciones y aplicar alertas de desempeño específicas.
   Mantener una imagen Docker, un Registry MLflow y tres réplicas de la API.

## Decisión recomendada

Incorporar primero humedad y peso al desarrollo y añadir flujo cuando su
significado esté confirmado. El objetivo final sigue siendo un único modelo
multisalida. Conservar la versión de temperatura operativa mientras se valida
la ampliación con un nombre de modelo nuevo en MLflow, evitando sustituir
accidentalmente el contrato actual de la API.

La dificultad es media: la infraestructura se reutiliza, pero el dataset conjunto
y los criterios de selección requieren adaptación. Estas son recomendaciones;
el modelo multisalida todavía no está implementado.

# Análisis de fuentes incorporadas a ARNOLD

Fecha del perfil: 24 de septiembre de 2026.

Este documento registra únicamente estructura, cantidades y reglas. No se copiaron nombres, identificaciones, teléfonos, correos ni filas completas al proyecto.

## Resultado principal

Las cuatro fuentes ya pueden reconocerse por esquema. La cartera mensual debe ingresar como fuente original; las hojas unificadas y las órdenes son productos derivados que deben conservar referencia a su lote de origen.

| Fuente | Filas útiles | Resultado derivado | Hallazgo de control |
|---|---:|---:|---|
| Cartera julio 2026 | 37.330 | 26.927 unificadas | El consolidado usa el segundo bloque monetario; excluye 10.403 claves. |
| Cartera agosto 2026 | 38.042 | 32.560 unificadas | 18.234 errores de fórmula almacenados; 42 grupos no reconcilian automáticamente. |
| Exportación XLS heredada | 38.042 | 38.042 | 38.038 filas son idénticas a agosto; no debe contarse como otro lote. |
| Órdenes 030–034 | 2.619 | 50 inconsistencias registradas | 2.618 filas con clave provienen del consolidado de julio. |

## Claves de trabajo

- En la cartera mensual, `CLAVE` es única y debe conservarse como identidad de fila.
- Para consolidar y comparar se usa `CEDULA_RUC + CIU`.
- La combinación `CEDULA_RUC + CIU + CLAVE` sirve como evidencia de procedencia.
- En las órdenes, la referencia estable comprobada es `CEDULA + CIU`; `TP`, `EXP` e `ID PLAN` no están suficientemente completos para ser claves primarias.

## Transformaciones comprobadas

1. Julio contiene encabezados monetarios duplicados. El consolidado coincide exactamente con el segundo bloque de `TOTAL_EMISION`, `TOTAL_INTERES`, `TOTAL_COACTIVA` y `TOTAL_RECARGO` para las 26.927 claves incluidas.
2. La hoja de julio “sin coactiva” conserva sin cambios 26.427 filas y únicamente excluye 500 registros.
3. Agosto consolida a una fila por `CEDULA_RUC + CIU`. En 32.518 de 32.560 grupos los importes coinciden con una fila normalizada de la fuente. Los otros 42 requieren revisión; dentro de los grupos repetidos, 3.443 de 3.447 coinciden y cuatro no.
4. La copia de `SHEET-UNIFICADO` de agosto es totalmente redundante y no debe importarse dos veces.
5. Las órdenes 030–034 coinciden por clave con julio. Solo seis claves dejan de aparecer al compararlas con agosto, por lo que no se debe atribuir su origen a agosto.

## Reglas de seguridad de datos

- Las fórmulas de Excel no se ejecutan ni se toman como autoridad. Se registran sus errores y el servidor recalcula las salidas autorizadas.
- La ausencia de una clave en el mes siguiente no demuestra pago o cancelación.
- Ningún monto, identidad, título o estado de pago se corrige sin conservar valor anterior, evidencia, usuario y aprobación cuando corresponda.
- El `.xls` heredado se convierte en un proceso aislado, con macros desactivadas, y se compara mediante huella y claves antes de aceptarlo.
- Los archivos originales permanecen fuera del frontend y deben almacenarse cifrados cuando exista el backend.

## Integración realizada

`backend/static/js/validator-config.js` contiene el catálogo usado por la presentación, los esquemas requeridos, los alias de encabezados y las reglas iniciales. La pantalla “Fuentes” presenta únicamente métricas agregadas y hallazgos seguros.

La lectura real de XLSX/XLS debe implementarse en el backend aislado; el navegador no debe procesar archivos sensibles como mecanismo definitivo.

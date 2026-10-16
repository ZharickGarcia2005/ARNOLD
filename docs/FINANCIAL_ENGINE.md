# Motor financiero desacoplado

## Alcance

Esta primera versión implementa el núcleo de validación sin modificar ni
importar código de ARDUR-BETA. El núcleo puro trabaja con objetos inmutables en
memoria y no accede directamente a modelos Django, usuarios, archivos privados,
auditoría o Celery; esas responsabilidades se conectan desde servicios externos
al núcleo.

Su objetivo es fijar un contrato estable para que ambos proyectos puedan
integrarse después mediante un adaptador pequeño y revisable.

## Componentes

- `contracts.py`: entradas, resultados, severidades y huellas idempotentes.
- `comparators.py`: agrupación, duplicados, comparación mensual, consolidación
  y trazabilidad de órdenes.
- `rules.py`: las once reglas financieras versionadas.
- `exporters.py`: creación de un XLSX en memoria con `Resumen` e `Incidencias`.
- `tests/`: pruebas puras con datos ficticios, sin base de datos.

Estos cuatro módulos forman el núcleo puro. La app `validation` ya conecta el
adaptador XLSX, `ValidationRun`, la tarea Celery, los registros cifrados y las
incidencias persistidas mediante `services.py`, sin introducir dependencias de
Django dentro de las reglas.

## Límites de seguridad

- El motor no modifica RAW, staging, expedientes ni órdenes.
- Una ausencia mensual nunca se interpreta como pago.
- Un contribuyente con varias claves no se considera duplicado por ese solo
  hecho.
- Los perfiles con encabezados duplicados deben seleccionarse expresamente.
- El adaptador debe declarar también las apariciones de columnas que aplicó;
  indicar solamente el nombre de un perfil no elimina la ambigüedad.
- Las solicitudes de pago o cancelación requieren evidencia autorizada y un
  aprobador diferente del solicitante. Los identificadores se comparan sin
  depender de mayúsculas o espacios.
- Ese control opera únicamente sobre los `PaymentClaim` entregados al motor.
  La carga ya autentica usuarios y comprueba permisos, pero la futura capa de
  revisión deberá comprobar la existencia real de la evidencia y crear un
  claim por cada cambio sensible; los valores declarados en memoria no
  constituyen autorización por sí solos.
- Los importes vacíos, no numéricos, infinitos o `NaN` generan incidencia; el
  valor cero sí se considera válido. En la cartera actual bloquean, mientras
  que en una fuente auxiliar `SCHEMA-001` los reporta como alerta.
- El exportador neutraliza texto que podría convertirse en fórmula de Excel.
- Si cualquier texto supera los 32.767 caracteres admitidos por una celda, la
  exportación completa se detiene con un error explícito en vez de dividirlo o
  truncarlo. La evidencia JSON se conserva en una sola celda.
- El XLSX no contiene fórmulas, macros ni vínculos externos.
- El XLSX sí contiene datos personales en claro. Antes de almacenarlo o
  ofrecerlo para descarga se requieren cifrado, permisos, caducidad y auditoría.
- Se admiten como máximo 100.000 incidencias por libro; volúmenes mayores deben
  dividirse o procesarse mediante una exportación en segundo plano.

## Contrato de entrada

Cada `DatasetInput` identifica un lote y contiene `RecordInput`. Los valores se
representan mediante `FieldCell`, que conserva el valor, la representación
original opcional y el tipo de celda (`value`, `blank`, `formula` o `error`).
Cuando se usa un perfil de encabezados duplicados, `selected_occurrences`
registra las apariciones que realmente utilizó el adaptador.

La cartera actual es obligatoria. Las fuentes de referencia, consolidado,
catálogo y órdenes son opcionales. Cuando falta una fuente, las reglas que la
necesitan quedan registradas en `skipped_rules`; no se presentan como una
validación satisfactoria.

Si ambos periodos están informados, la referencia debe ser estrictamente
anterior a la cartera actual. El consolidado admite una sola fila por grupo de
cédula/RUC y CIU; varias filas consolidadas se reportan como ambigüedad.

El contrato exige además roles correctos y `dataset_id` distintos; `record_id`
y `source_row` son únicos dentro de cada dataset. `reference` debe usar el mismo
esquema que `current`; `consolidated` debe declarar a `current` como padre y
`orders` debe declarar como padre al consolidado o, si no existe, al actual.
Los `PaymentClaim` solo pueden referirse al mismo registro presente en la
cartera actual.

## Contrato de salida

`validate()` devuelve `ValidationReport`. Cada `RuleResult` incluye:

- código y severidad;
- condición bloqueante;
- registro principal y relacionados;
- campo afectado;
- mensaje;
- evidencia estructurada;
- versión del motor;
- huella SHA-256 estable.

La huella permite reintentar la evaluación sin duplicar una incidencia cuando
la regla, decisión, sujeto, evidencia y versión no cambiaron. No es una firma
del XLSX ni sustituye el hash externo y la auditoría del archivo final.
La evidencia se copia y congela de forma profunda para impedir que una lista o
diccionario externo cambie una huella ya calculada. Los grupos anormalmente
grandes conservan cantidad y huella completa, pero limitan a 50 las referencias
incluidas por cada grupo para evitar crecimiento cuadrático de memoria.

## Reglas iniciales

| Código | Propósito |
|---|---|
| `SCHEMA-001` | Columnas obligatorias, reconocimiento de esquema e importes válidos |
| `SCHEMA-002` | Encabezados duplicados y perfiles explícitos |
| `KEY-001` | CLAVE vacía o repetida dentro del periodo |
| `KEY-002` | Cambio de identidad o CIU para la misma CLAVE |
| `DUP-001` | Reconciliación del consolidado sin sumar títulos |
| `CAT-001` | Filas exactas repetidas o catálogo contradictorio |
| `FORMULA-001` | Fórmulas y errores: bloquea la cartera actual y alerta en fuentes auxiliares |
| `MONTH-001` | Altas, ausencias y cambios monetarios entre periodos |
| `PAYMENT-001` | Evidencia y doble control de pago/cancelación |
| `ORDER-001` | Trazabilidad de la orden a su fuente |
| `ORDER-002` | Campos obligatorios e importes válidos de la orden |

### Fuentes necesarias y omisiones

| Regla | Requisito |
|---|---|
| `KEY-002`, `MONTH-001` | Se omiten sin cartera histórica `reference` |
| `DUP-001` | Se omite sin `consolidated` |
| `ORDER-001`, `ORDER-002` | Se omiten sin `orders` |
| `CAT-001` | Siempre revisa duplicados exactos actuales; amplía el análisis si existe `catalog` |

`MONTH-001` compara únicamente claves unívocas uno a uno. Revisa por defecto
los campos monetarios conocidos, tolera una diferencia de hasta 0,01 y reporta
diferencias mayores como informativas, no bloqueantes y pendientes de revisión.
Una alta, ausencia o diferencia monetaria nunca implica por sí sola un pago.

`SCHEMA-001` y `FORMULA-001` son bloqueantes en la cartera actual y se degradan
a alerta en fuentes auxiliares. `SCHEMA-002` sigue siendo bloqueante ante una
selección ambigua de columnas, y `ORDER-002` emite incidencias bloqueantes para
órdenes incompletas o con importes inválidos. Estos indicadores todavía no
detienen una aprobación real porque el motor no está conectado al workflow.

`ORDER-001` traza directamente contra la cartera actual mediante CLAVE,
cédula/RUC y CIU. Cuando existe consolidado, usa los campos obligatorios comunes
PREDIO_MUN, cédula/RUC y CIU para enlazar la orden con su padre inmediato.

La igualdad aritmética entre `TOTAL` y sus componentes todavía no se impone:
primero debe confirmarse con el negocio si incluye coactiva, recargos, redondeos
u otros conceptos. Por ahora solo se exige que los importes sean finitos.

## Perfil de julio de 2026

El perfil `julio_2026_confirmado` admite expresamente la segunda aparición de
los cuatro encabezados monetarios duplicados comprobados durante el análisis.
El motor nunca activa este perfil utilizando el nombre del archivo: el proceso
que prepare el dataset debe seleccionarlo de forma explícita y auditada, y debe
declarar en `selected_occurrences` que aplicó la aparición 2 de
`TOTAL_EMISION`, `TOTAL_INTERES`, `TOTAL_COACTIVA` y `TOTAL_RECARGO`. Una tercera
aparición inesperada vuelve a bloquear el archivo.

## Uso básico

```python
from apps.validation.contracts import ValidationInput
from apps.validation.rules import validate
from datetime import datetime

from apps.validation.exporters import ExportMetadata, render_issues_xlsx

report = validate(ValidationInput(current=current, reference=reference))
metadata = ExportMetadata(
    report_id="reporte-001",
    generated_at=datetime.now(),
    generated_by="usuario-autenticado",
)
payload = render_issues_xlsx(report, metadata)
```

`render_issues_xlsx()` verifica el libro antes de devolver sus bytes.

La integración se divide deliberadamente en dos piezas:

1. **Adaptador Excel de ARNOLD**: ya implementado para el primer corte;
   lee libros en cuarentena y construye `DatasetInput`, preservando `raw`,
   `kind`, encabezados, `profile_id` y `selected_occurrences`.
2. **Puente ARDUR**: aún pendiente; exportará el contrato de 13 columnas para
   que ARDUR lo reciba mediante su propio flujo RAW/Staging/modelos. Solo debe
   implementarse con aprobación del responsable de ARDUR-BETA y sin copiar sus
   modelos ni escribir directamente en su base.

`RULE_CATALOG` en Python es la fuente normativa. La configuración JavaScript
actual es solo presentación heredada y deberá consumir ese catálogo para no
divergir.

## Verificación

Desde `backend/`:

```powershell
python manage.py test apps.validation.tests -v 2
python manage.py test -v 2
python manage.py check
python manage.py makemigrations --check --dry-run
```

## Integración futura con ARDUR-BETA

El mapeo acordado es conceptual, no una copia de modelos:

| Motor ARNOLD | ARDUR-BETA |
|---|---|
| Dataset actual | `ImportacionCartera` |
| Registro original | `RegistroCarteraRaw` |
| Registro normalizado | `RegistroCarteraStaging` |
| Referencia aprobada | `CarteraDetalle` |
| Resultado de regla | futura incidencia financiera |

La conexión automática, persistencia, permisos, auditoría, rutas y bloqueo de
aprobación requieren un cambio compartido aprobado por el responsable de
ARDUR-BETA. Esta versión no altera ninguno de esos puntos.

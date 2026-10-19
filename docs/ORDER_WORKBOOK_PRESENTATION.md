# Hoja preliminar organizada como el libro de órdenes

## Causa y corrección

La implementación anterior seguía siendo genérica: un contrato universal ordenaba
los campos canónicos y anteponía FILA_ORIGEN/ESTADO_REVISION. Cambiar etiquetas no
creaba pestañas ni reproducía las columnas ocultas del libro. Además, ambas
descargas eran de una sola hoja. Eso no cumplía la organización solicitada.

Ahora el runtime consume `backend/apps/workflow/order_manifest.json`, versión
`order-book-2026.10.19.1`. Se generó desde cero con el XML del único archivo
autorizado con `(1)`, SHA-256
`c1527fbbca77b4d92f38f420f284de65851b9f3bac68a58d33e9c25109dda29f`.
No se ejecutaron fórmulas, macros ni vínculos; el manifiesto no contiene datos
personales ni filas de deudores. No utiliza la configuración del archivo descartado.

## Pestañas del manifiesto

| ID | Nombre exacto | Columnas del libro |
| --- | --- | ---: |
| 030 | 030-SAN CARLOS (LISTA) | 37 |
| 031 | 031-(24 DE MAYO) LISTA | 37 |
| 032 | 032-SAN CRISTOBAL(LISTA) | 37 |
| 033 | 033-GUAYACAN(LISTA) | 37 |
| 034 | 034-GUAYACAN(LISTA) | 37 |
| 035 | 035-NICOLAS ALTA(LISTA) | 38 |
| 036 | 036-RUTA DEL RIO(LISTA) | 38 |
| 037 | 037-VIVA ALFARO(LISTA) | 38 |
| 038 | 038- VENUS | 41 |
| 039 | 039-VENUS | 38 |
| 040 | 040-VENUS | 38 |
| issues | INCONSISTENCIAS | 37 |

No se presentan como pestañas de edición Hoja 8, PG RECARGO, COACTIVA ni Copia de
BARRIOS DE QGUIS. No se eliminaron esas hojas del archivo personal original.

Cada columna registra posición, encabezado literal (incluidos espacios finales),
ancho relativo, ocultación expandida desde rangos min/max, nivel de agrupación y
formato observado. La columna B de 030 realmente tiene el encabezado vacío: no se
inventó TP allí. Se conserva ese espacio y las letras originales de Excel.
EMISION está en V para 030–035, en W para 036–040. La cantidad de títulos no se
ha movido a una posición universal. Se conservan UNIDAD, FE y REGISTRADO de 038.

Los encabezados de algunas hojas de origen tienen otros colores. Por petición
expresa se aplica en todas el gris azulado de 030 (#A2C4C9); el color de origen se
conserva en `source_header_fill`. Las filas alternan blanco/celeste, con bordes
finos y cabecera fija. Los importes y fechas conservan los formatos monetarios y
dd/mm/yyyy donde los indica el manifiesto. Los identificadores se fuerzan a texto
para no perder ceros, aunque la celda original tuviera formato numérico.

## Mapeo y asignación de filas

`columns.py` construye el contrato de cada pestaña desde ese manifiesto. Alias de
presentación: NOMBRES → CONTRIBUYENTE, CEDULA_RUC → CEDULA, TELEF → TELEFONO,
TOTAL_EMISION → EMISION, TOTAL_INTERES → INTERES, TOTAL_RECARGO → RECARGO.
No se renombra el RAW. El TOTAL del libro es un valor de origen independiente
(`SOURCE_TOTAL`): no se sustituye por una nueva suma de componentes financieros.

CLAVE, CATASTRO, PREDIO MUNICIPAL, TITULO, TITULOS, TITULOS VENCIDOS y
TITULOS VENC. no se rellenan entre sí. CATASTRO sólo queda disponible como
columna auxiliar si existe en el archivo cargado. No se impone una columna TITULO
vacía a las órdenes que no la contienen. Los originales adicionales y ocurrencias
duplicadas se conservan ocultos, con IDs propios y procedencia; no se borran.
Un alias visual puede tener una copia RAW auxiliar con su encabezado original:
el valor de trabajo editado y la evidencia original son distintos deliberadamente.

La asignación NO utiliza parroquia, nombre, cédula, OP, OC ni predio como atajos.
Sólo reconoce una hoja de origen con nombre exacto confirmado, o un valor explícito
030–040/nombre exacto en ORDEN u ORDEN_PRELIMINAR. Un número desconocido, un dato
ausente o un conflicto entre fuentes va a INCONSISTENCIAS. GUAYACÁN y VENUS no
determinan una orden porque tienen varias. Las auxiliares nunca son destinos.

Los errores financieros, de identidad y CLAVE repetida siguen usando las reglas
existentes. No se deduplica por persona ni por cantidad de títulos. Todas las
apariciones de una CLAVE repetida siguen separadas.

`order_projection.py` calcula una partición de presentación sin escribir sobre la
calidad, cifrado, importes o versiones de los lotes históricos. `validation_summary`
expone sus conteos originales; `summary` incluye además las filas sin asignación
segura. Por eso una orden puede estar vacía y esas filas aparecer en INCONSISTENCIAS,
sin que se hayan eliminado o revalidado registros. Hay un aviso explícito en pantalla.
El índice en memoria sólo conserva UUID, orden y motivo técnico, no datos personales.

## Interfaz, edición y sincronización

La primera pestaña siempre es 030; cada pestaña consulta sólo su orden, con páginas
de 100 filas y búsqueda exacta. La banda inferior permite desplazamiento horizontal
entre las doce pestañas. Mostrar ocultas revela los campos sin destruirlos. Cambiar
de pestaña respeta la protección de borradores y formatos pendientes.

FILA_ORIGEN/ESTADO_REVISION no encabezan las órdenes. El indicador ⋮ de una fila
y el panel Revisión de la fila muestran origen, versión, orden, incidencias y
observaciones sobre valores ausentes. En INCONSISTENCIAS los controles se añaden
al final, sin sustituir las columnas del libro. Una orden confirmada se puede
proponer en ese panel, con el mismo motivo, versiones y aprobación protegida.

Se conservan doble clic/F2, teclado, copiar/pegar validado, selección, minibarra,
redimensionamiento, formatos personales, Ctrl+S, Ctrl+Z de borradores, historial y
doble control. Los campos adicionales financieros, FECHA y HORA tienen controles
de formato. Las fechas dd/mm/yyyy de pantalla se normalizan al guardar sin
alterar su RAW. Las descargas nunca contienen cambios pendientes como aprobados.
Guardar y descargar espera confirmación, consulta la revisión y descarga; un
fallo de descarga no repite un guardado ya confirmado.

## Dos descargas, no tres

- Principal: todas las filas válidas asignadas, distribuidas en las once hojas
  de órdenes, en el orden confirmado. Las órdenes sin registros conservan su
  cabecera vacía para mantener la estructura del libro.
- Errores/duplicados: todas las incidencias y filas sin orden segura, en
  INCONSISTENCIAS, con su estructura y controles adicionales de revisión.

Ambas incluyen Trazabilidad, original/SHA, revisiones, motor/adaptador, reglas
omitidas y ejecutadas, contrato por hoja y ocurrencia, Record/WorksheetRow/fila,
destino, campos vacíos, incidencias, historial y decisiones. Conservan formatos
personales compatibles, anchos/ocultaciones y valores guardados/aprobados.
Se ignoran pestaña, página, búsqueda y filtro activos al descargar el conjunto
completo. Se neutralizan fórmulas y errores Excel como texto. El usuario necesita
permiso de descarga. No hay otra sección ni descarga llamada Final preliminar.

## Verificación y límites

Resultado final: 155 pruebas Django y 16 JavaScript correctas; comprobación de
Django sin incidencias, sin migraciones pendientes y revisión de espacios de Git
sin errores. Las pruebas incluyen un caso de más de 100 registros, formatos
personales, aprobaciones, conflictos y errores de descarga sin doble guardado.

La instancia visual de `tools/worksheet_ui_fixture.py` ahora ejecuta Django real,
sus endpoints, login y exportadores, con SQLite/archivos privados temporales y
datos totalmente ficticios; no un servidor que simula respuestas de la API.
Las cookies de esta instancia tienen nombres propios, separados del servidor 8000.

Se probó carga → cuarentena íntegra → motor/incidencias → Worksheet → doce
pestañas → edición con motivo → aprobación → dos descargas completas. Un caso
de 111 registros produce 107 principales y 4 inconsistencias sin pérdidas ni
solapamiento: dos CLAVEs repetidas, una identificación de orden ausente y un
correo inválido. La clasificación financiera original mantiene 108/3: la fila
sin orden se separa por presentación, no mediante una revalidación destructiva.

Las sumas se reconciliaron: principal 1081.77 emisión + 237.54 interés + 356.31
coactiva + 475.08 recargo = 2150.70; inconsistencias 40.44 + 8.88 + 13.32 + 17.76
= 80.40. Se verificaron ZIP/CRC, apertura XLSX, identificadores de texto,
encabezados/ocultaciones/tipos por hoja, fechas, personalización y trazabilidad.
El navegador comparó las secuencias visibles de las doce pestañas con el manifiesto;
se verificaron ocultas, la orden 038 y guardar/descargar. Capturas y JSON están en
`outputs/order-presentation`, ignorados por Git. Ambos XLSX se importaron y
renderizaron de forma independiente; los previews no ejecutan contenido del original.
No se automatizó Microsoft Excel de escritorio ni se certifica su interfaz nativa.

Campos que NO se completan sin origen/regla confirmada: EXP, OP/OC, predio,
ubicación, cantidad exacta de títulos, SUBTOTAL, importes/textos financieros,
digitador, fechas y auxiliares que falten en la cartera. FE se conserva como texto
sin asumir que sea una fecha. No se calculan importes en letras ni se interpreta
TITULOS como MESES_DEUDA. La observación explica el vacío; no se inventan valores.

El formulario mensual continúa leyendo una hoja explícita de una cartera por
lote. Para el libro operativo se añadió el comando administrativo
`import_order_workbook`, descrito abajo. No se sustituyen lotes anteriores.
No se cambió ARDUR-BETA ni se hizo push.
La configuración local de cifrado/desarrollo sigue requiriendo endurecimiento
antes de producción; no se cambió la clave que protege datos existentes.

## Carga real del libro operativo (19 de octubre de 2026)

Por solicitud expresa del usuario se importaron los datos del archivo `(1)` como
un lote nuevo, sin periodo mensual inventado: `90f1331f-642a-4356-87f9-e235fed2a983`.
El SHA del original coincide con el manifiesto. La copia privada conserva todos
sus bytes, incluidas las auxiliares; sólo las doce hojas autorizadas generan filas.

Se conservaron 5.801 filas: 339 de 030, 407 de 031, 246 de 032, 701 de 033,
309 de 034, 462 de 035, 44 de 036, 1.167 de 037, 502 de 038, 203 de 039,
1.360 de 040 y 61 de INCONSISTENCIAS. Se omiten como fuentes Hoja 8, PG RECARGO,
COACTIVA y Copia de BARRIOS DE QGUIS. No se descartaron filas incompletas ni
subtotales no reconocidos: permanecen observados para revisión humana.

El libro tiene 39.146 celdas con fórmulas y 1.524 con errores Excel en las hojas
operativas. No se ejecutaron ni se asumieron correctos sus resultados cacheados.
El motor guardó 57.409 incidencias (no personas distintas), hay dos filas con
CLAVE repetida y las 5.801 filas permanecen en INCONSISTENCIAS. La carga terminó
correctamente en estado `review`; no significa aprobación ni fallo de importación.

`source_row` es un ordinal interno único del libro. El RAW cifrado de cada fila
incluye `origin.sheet`, `origin.excel_row` y `origin.headers`, sin perder la fila
real porque dos pestañas tengan una fila 2. El panel de revisión y la trazabilidad
de descarga exponen esa procedencia. Las órdenes se toman del nombre exacto de
origen, jamás de la parroquia. La hoja de origen INCONSISTENCIAS conserva una
observación obligatoria. No se inventan MESES_DEUDA ni TOTAL_COACTIVA ausentes:
las revisiones del esquema ordenPreliminar no exigen columnas propias de mensual.

La comprobación SHA de registros cifrados, estados, revisiones e incidencias de
trabajo de los lotes anteriores coincidió antes y después de importar. Repetir
el mismo archivo y área reutiliza el lote. La importación usa cuarentena, controles
de archivo, permiso import_batch, cifrado, motor y auditoría existentes. No habilita
este tipo de carga en el formulario mensual ni cambia permisos o claves.

```powershell
# Ejecutar desde backend con una cuenta que tenga permiso de importación.
.\.venv\Scripts\python.exe manage.py import_order_workbook "C:\ruta\libro.xlsx" --username cuenta --dry-run
.\.venv\Scripts\python.exe manage.py import_order_workbook "C:\ruta\libro.xlsx" --username cuenta
```

La interfaz acepta `?batch=UUID` para abrir un lote visible del área del usuario.
Al abrir/cambiar de cartera elige una pestaña con datos si la actual está vacía.
No redirige los clics posteriores sobre órdenes vacías ni pierde borradores.
Las operaciones largas pueden bloquear SQLite local temporalmente; no se anunció
éxito hasta confirmar la transacción. La solución de desarrollo sigue sin ser
una configuración apta para producción o trabajo concurrente de toda la empresa.

## Archivos principales

Manifiesto/generador: `order_manifest.json`, `tools/build_order_manifest.py`.
Backend: `columns.py`, `order_projection.py`, `worksheet.py`, `views.py`,
`sheet_exports.py`, `presentation.py`, `dashboard/views.py`.
Pantalla: `worksheet.html`, `worksheet-app.js`, `worksheet-grid.js`,
`worksheet-orders.css`. Pruebas: workflow/contrato/presentación y descargas JS.
Utilidades: `worksheet_ui_fixture.py`, verificadores y renderizado sintético.
No se añadieron modelos ni migraciones de base de datos.

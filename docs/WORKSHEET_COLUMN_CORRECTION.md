# Corrección de la hoja preliminar — 19 de octubre de 2026

Este documento describe el contrato genérico anterior, sustituido por la
[presentación por órdenes](ORDER_WORKBOOK_PRESENTATION.md). Sus conteos y
afirmaciones sobre CATASTRO obligatorio no son la especificación vigente.

## Qué se corrigió y qué se conservó

El prompt anterior interpretaba una tercera descarga «Final preliminar». Era
incorrecto. Se retiraron su botón, selector, rama del exportador, contrato,
exportador, pruebas y documentación nuevos, así como sus artefactos sintéticos
en `outputs/final-preliminar-synthetic`. El archivo personal anterior NO se borró.
No se utilizó un restablecimiento general de Git.

Se conservan PRELIMINAR, la Worksheet, las DOS descargas, el motivo obligatorio,
los borradores, el control de versiones, las aprobaciones y los formatos personales.
También se conserva la mejora válida de comprobación de respuestas de descarga:
tipo XLSX, firma ZIP, lote, revisión, filas y nombre devuelto por el servidor.
Si falla sólo la descarga, un guardado confirmado no vuelve a ejecutarse.

No se modificó ARDUR-BETA, no se hizo push, no se ejecutaron migraciones ni se
importó el Excel de referencia a la base operativa.

## Referencia vigente analizada desde cero

Únicamente `ORDEN PRELIMINAR-030-031-032-033-034-035-036-037-038 (1).xlsx`.
SHA-256: `c1527fbbca77b4d92f38f420f284de65851b9f3bac68a58d33e9c25109dda29f`.
Se inspeccionó como XML dentro del ZIP, en modo de lectura, sin ejecutar fórmulas,
macros ni vínculos. `current_reference_manifest.json` guarda sólo estructura y
estadísticas; nunca filas de personas. Los textos de fila 1 no reconocidos como
encabezados se redactan, porque una hoja auxiliar comienza directamente con datos.

Inventario observado NUEVAMENTE en el archivo vigente:

| Hoja | Visibilidad | Filas con contenido, incluyendo cabeceras y auxiliares |
| --- | --- | ---: |
| 030-SAN CARLOS (LISTA) | Visible | 340 |
| 031-(24 DE MAYO) LISTA | Visible | 408 |
| 032-SAN CRISTOBAL(LISTA) | Visible | 247 |
| 033-GUAYACAN(LISTA) | Visible | 702 |
| 034-GUAYACAN(LISTA) | Visible | 310 |
| 035-NICOLAS ALTA(LISTA) | Visible | 463 |
| Hoja 8 | Visible | 0 |
| 036-RUTA DEL RIO(LISTA) | Visible | 45 |
| 037-VIVA ALFARO(LISTA) | Visible | 1168 |
| 038- VENUS | Visible | 503 |
| 039-VENUS | Visible | 204 |
| 040-VENUS | Visible | 1361 |
| INCONSISTENCIAS | Oculta | 62 |
| PG RECARGO | Oculta | 26 |
| COACTIVA | Visible | 18669 |
| Copia de BARRIOS DE QGUIS | Visible | 31335 |

Estos NO son conteos de deudores ni órdenes aprobadas. El libro contiene 1524
celdas `#N/A`: 1098 en 037, 416 en 040 y 10 en INCONSISTENCIAS. No se certifica
como base depurada. Sus hojas 039/040 también existen aunque no figuren en el nombre.

Organización útil observada: control/expediente/predio, contribuyente y cédula,
OP/OC, CLAVE/CIU, ubicación/contacto, importes y textos auxiliares de importes,
cantidades de títulos, digitador/fecha/hora/novedad. Las cantidades aparecen en
posiciones diferentes entre hojas; hay encabezados vacíos y auxiliares.
No se copian fórmulas, agrupaciones, subtotales históricos ni columnas vacías
accidentales a una cartera mensual. Anchos, colores y alineaciones originales
quedan registrados; la presentación operativa mantiene el estilo de ARNOLD,
anchos por tipo y preferencias personales, no un clon de todas las órdenes.

## Aclaraciones posteriores del usuario

- CLAVE y CATASTRO son identificadores distintos, aunque puedan coincidir. Ambos
  se conservan como texto, con ceros iniciales; nunca se rellenan entre sí.
- TITULO, TITULOS y sus variantes conservan sus cantidades/textos originales
  separados. El usuario entiende que podrían representar meses de deuda, pero
  esa equivalencia no se aplica sin confirmación del municipio. TITULO sigue como
  columna independiente cuando existe; no se copia de CLAVE, TITULOS o MESES_DEUDA.
- Repetir una cantidad de títulos o un CATASTRO no provoca deduplicación. Se
  mantiene la regla vigente de CLAVE: TODAS sus repeticiones van a revisión.
- No se descartan filas por compartir cédula o nombre, ni se agrupan personas.
- La comprobación de presencia de CATASTRO se aplica al preparar las próximas
  cargas; su ausencia conserva la fila y la separa para revisión. TITULO no se
  exige como supuesto identificador individual después de la aclaración.
- Los lotes existentes se conservan: no se revalidan, reclasifican ni rellenan.
  Si su copia de trabajo no tenía CATASTRO, la consulta y la descarga muestran
  un aviso de validación no ejecutada, sin cambiar el cifrado, conteos o revisión.
  Tampoco se recuperan automáticamente alias históricos ambiguos; una revisión
  de esos datos necesitaría autorización expresa, no una migración silenciosa.

## Contrato compartido

`apps/workflow/columns.py`, versión `worksheet-columns-2026.10.19.1`, es la
definición que consumen query, ambas tablas y ambos exportadores. Cada columna
incluye ID, etiqueta, posición, origen/encabezado/ocurrencia, tipo, formato, ancho,
capacidad de edición, protección, cálculo/control y reglas de exportación/traza.

| Grupo | Organización y tratamiento |
| --- | --- |
| Control de ARNOLD | FILA_ORIGEN, ESTADO_REVISION |
| Origen documental, si existe | NO, TP, EXP, PREDIO MUNICIPAL, OP, OC, DIGIT y demás originales |
| Identidad y contacto | NOMBRES, CEDULA_RUC, CLAVE, CATASTRO, TITULO, CIU, dirección, ubicación, teléfono, correo |
| Importes | Emisión, interés, coactiva y recargo numéricos; auxiliares originales separados |
| Cantidades y fechas | TITULOS/variantes originales, MESES_DEUDA y vencimiento sin inferir equivalencias |
| Otras columnas del origen | Se conservan, incluso desconocidas o encabezados repetidos |
| Control calculado | MONTO_PENDIENTE, MOTIVOS |

Se intercalan los originales en el orden de negocio observado y los campos de
trabajo explícitos; no se inventan datos para columnas ausentes. Los encabezados
originales se conservan. CLAVE/TITULO se muestran independientes con sus nombres.
Las ocurrencias seleccionadas por perfil alimentan el campo editable; las otras
apariciones y columnas extra se muestran como evidencia de sólo lectura con IDs
propios. Una columna original llamada TOTAL no sustituye MONTO_PENDIENTE.

La tabla sigue paginada a 100 filas, con búsqueda exacta en todo el lote, edición
con doble clic/F2, selección, pegado validado, minibarra y formatos personales.
Abrir o descargar no aplica cambios. Los valores protegidos (incluidos CLAVE,
CATASTRO y TITULO) siguen el mismo circuito de permisos y doble control existente.

## Descargas y trazabilidad

Sólo Principal y Errores/duplicados. Exportan todo su conjunto, ignorando búsqueda
y página, y exigen la revisión actual. Los identificadores son texto y los importes
válidos números con dos decimales. Fórmulas y errores Excel se neutralizan como
texto. Se respetan formatos personales soportados. No se exportan propuestas
pendientes como valores aplicados.

Trazabilidad incluye lote, archivo/SHA, hoja, Record/WorksheetRow/fila de origen,
versión, revisión, contrato por encabezado/ocurrencia, adaptador, motor, reglas
ejecutadas y omitidas, errores de hoja, incidencias con huella de evidencia,
historial por campo (antes/después, usuario/motivo/fecha) y solicitud/decisión.
Se crean partes adicionales de trazabilidad antes de superar el límite de filas
de Excel; nunca se mezclan registros de principal y revisión.

## Verificaciones ejecutadas

Archivos principales añadidos o ajustados:

- `backend/apps/workflow/columns.py`: contrato común versionado.
- `backend/apps/workflow/worksheet.py`: campos independientes y compatibilidad.
- `backend/apps/workflow/views.py`: filas y metadatos para ambas tablas.
- `backend/apps/workflow/sheet_exports.py`: dos descargas completas y traza.
- `backend/apps/workflow/presentation.py`: formatos por IDs del contrato.
- `backend/apps/validation/excel_adapter.py`, `rules.py`: normalización separada
  y conservación del texto de identificadores.
- `backend/templates/dashboard/worksheet.html`, `backend/static/js/worksheet-app.js`:
  columnas compartidas, aviso histórico y sólo dos botones.
- `backend/static/js/worksheet-download.js`, `backend/apps/dashboard/views.py`:
  verificación de la descarga y versión de recursos.
- Pruebas de workflow, presentación, adaptador y descargas JavaScript; fixture
  visual, analizador de referencia, verificador genérico y del flujo completo.
- README, esta explicación y manifiesto estructural saneado.

- Django: 149 pruebas, todas correctas. JavaScript: 16 pruebas, todas correctas.
- `manage.py check`: sin problemas. `makemigrations --check --dry-run`: sin cambios.
- Carga real mediante cliente HTTP de pruebas, cuarentena original intacta,
  motor, incidencias y Worksheet: 111 filas sintéticas → 107 principal + 4 revisión,
  incluyendo las dos apariciones de CLAVE duplicada. Sin solapamiento ni pérdidas.
- Edición con motivo, conflicto 409, propuesta protegida, exportación del valor
  anterior pendiente, aprobación por otro usuario y descarga en revisión 3.
- Dos XLSX realmente descargados de la API, abiertos con openpyxl, ZIP íntegro,
  encabezados iguales a la API, identificadores de texto con ceros y sin fórmulas
  ejecutables. Sumas de principal: 1081.77 emisión, 237.54 interés, 356.31 coactiva,
  475.08 recargo = 2150.70. Revisión: 40.44 + 8.88 + 13.32 + 17.76 = 80.40.
- Prueba visual en navegador con fixture sin datos reales: columnas independientes,
  doble clic, motivo y Guardar y descargar funcionando. Captura en outputs ignorados.
- Importación/renderizado visual independiente del bloque financiero de ambos
  archivos sintéticos. El visor infiere números para ciertos textos numéricos:
  los identificadores se verifican en el archivo con openpyxl, no con esa inferencia
  del visor. Nunca se recalcula ni reescribe el XLSX descargado.
- No se automatizó Microsoft Excel de escritorio: su apertura sin aviso de reparación
  debe confirmarse allí; las verificaciones de estructura y ZIP sí se completaron.

Artefactos ignorados por Git: `outputs/corrected-worksheet/principal-sintetico.xlsx`,
`revision-sintetica.xlsx`, previews, captura y `verification.json`. Son ficticios.
Para reproducir: `tools/verify_corrected_workflow.py` crea exclusivamente una base
de pruebas SQLite en memoria; `tools/verify_worksheet_downloads.py` recibe conteos
y revisión explícitos, sin fijar datos de carteras reales.

## Comprobación desde la interfaz y límites

Abrir ARNOLD, pulsar Actualizar, elegir un lote y comprobar las columnas separadas.
Los lotes históricos muestran el aviso y mantienen sus clasificaciones anteriores.
Probar una próxima carga controlada; revisar MOTIVOS y las reglas omitidas.
Corregir una celda con motivo, aprobar si procede, y descargar cada conjunto.
El archivo de referencia se usa para organización, no como cartera mensual nueva.

Pendientes de negocio: confirmar significado/unidad y variantes de títulos con
el municipio y el mapa real de CATASTRO. No se añadieron cálculos de recargos,
reglas de agrupación ni certificación de pago/cancelación. «Principal» significa
sin incidencias que obligan a revisión de las reglas ejecutadas, no validación
histórica satisfactoria si faltan fuentes. Producción conserva los requisitos
de seguridad y despliegue ya documentados.

El servidor local sigue avisando que la clave de cifrado se deriva de la clave
de desarrollo cuando no hay una clave persistente configurada. No se cambió esa
clave porque podría volver ilegible la evidencia existente. Antes de producción
se necesita un plan de gestión/migración de claves y los demás controles de seguridad.

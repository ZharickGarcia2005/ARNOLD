# Hoja preliminar de ARNOLD

La organización vigente de columnas y su compatibilidad con lotes históricos
se especifican en [ORDER_WORKBOOK_PRESENTATION.md](ORDER_WORKBOOK_PRESENTATION.md).
Las nuevas validaciones sólo se aplican a próximas cargas. No ejecutar comandos
de revalidación sobre los lotes existentes sin autorización del usuario.

La pantalla operativa usa `dashboard/worksheet.html` y un único controlador de
estado en `static/js/worksheet-app.js`. No carga los registros demo ni depende
de la inicialización del dashboard anterior. Los recursos llevan una versión
en su URL y la página/API responden `Cache-Control: no-store`.

## Flujo de datos

`Excel original → Batch/Record RAW cifrados → motor original → Worksheet/WorksheetRow`

El motor conserva sus resultados originales. La hoja añade controles de
calidad para revisión y mantiene una copia de trabajo cifrada. No sobrescribe
`Record.data_ciphertext`. Cada lote validado prepara su hoja en la misma
transacción que confirma el reporte; `prepare_worksheets` adapta lotes
preexistentes sin borrar ni reimportar los originales.

## Separación

- Una fila representa un título identificado por CLAVE. Una persona con varias
  claves no se descarta por ese motivo.
- Todas las apariciones de una CLAVE repetida se separan para revisión. No se
  elige una ganadora silenciosamente.
- Se validan campos obligatorios, cédula de 10 dígitos con verificador,
  estructura RUC de 13 dígitos, importes finitos no negativos con hasta dos
  decimales, meses enteros, correo y fecha opcional ISO.
- Un valor de Excel como `52.0` es válido como cantidad entera de meses.
- El RUC no se consulta al SRI; el control no acredita existencia, vigencia ni
  estado de pago. Identificaciones no reconocidas se conservan para revisión.
- FECHA_VENCIMIENTO permanece vacía si no existe en el origen. No se utiliza la
  fecha de elaboración de una orden como vencimiento.
- Los controles pendientes por falta de histórico, órdenes o consolidado se
  muestran explícitamente. No se interpreta su ausencia como pago ni éxito de
  comparación.
- Las alertas originales que requieren revisión se conservan en `source_errors`.
  Una edición no elimina automáticamente una discrepancia histórica del motor.
  Los errores locales de formato se recalculan al guardar.

## Edición y concurrencia

La grilla usa páginas de 100 filas para no colocar decenas de miles de inputs
en el navegador. La búsqueda exacta por CLAVE, cédula/RUC o CIU consulta todo el
lote mediante índices HMAC; no se limita a la página actual. Los identificadores
de búsqueda viajan en POST para no incluirlos en la URL de los logs.

Cada celda cambia inmediatamente el borrador local. Se guarda con el botón o
Ctrl+S: abre «Confirmar cambios», sin guardar automáticamente. El motivo
obligatorio se pide solo en esa ventana. Cancelar conserva el borrador; un
error de guardado conserva ventana, motivo y borradores. «Guardar y descargar
Excel» primero espera la confirmación, consulta la revisión actual y solo
después descarga el conjunto activo completo. Si el guardado fue confirmado
pero falla la descarga, se informa de ambos resultados y no se repite el
guardado. Si falla la consulta posterior, se bloquea la exportación hasta
actualizar. Se admite pegar un rango TSV de Excel dentro de
las filas/columnas visibles. El servidor verifica el área, el permiso
`batches.change_record`, los campos editables y la versión de cada fila. Un
conflicto devuelve 409 y no aplica parcialmente el rango.

Los validadores envían cambios de identidad e importes a `ChangeRequest`.
Jefes con `workflow.decide_change_request` y administradores pueden decidir
solicitudes de otra persona; el solicitante nunca aprueba su propia solicitud.
Una solicitud obsoleta no se aplica si cambió la fila. Las repeticiones idénticas
no crean solicitudes adicionales. Los cambios protegidos pendientes todavía no
forman parte del lote exportado.

`WorksheetEdit` conserva valores anteriores/nuevos y motivo cifrados junto al
usuario, fecha y versión. `AuditEvent` registra guardados, solicitudes,
decisiones y descargas sin copiar valores personales a sus metadatos.

La actualización periódica no reemplaza borradores pendientes ni interrumpe una
celda activa. Al guardar, el servidor recalcula errores y CLAVEs repetidas de
todas las filas afectadas y la interfaz vuelve a consultar el conjunto.

## Espacio de trabajo

El botón compacto ☰ del encabezado oculta o muestra la navegación; el nombre
se muestra como tooltip, no como texto permanente. El área
principal ocupa la columna liberada; la preferencia se guarda únicamente en
el navegador (`arnold.sidebarCollapsed`). Sin preferencia previa, el menú
empieza cerrado en pantallas de hasta 760 px. Ocultarlo no cierra la sesión ni
cambia los permisos.

La primera sección (`sheetWorkspace`) ocupa la altura útil del área de trabajo:
encabezado compacto, selector de cartera, estado y hoja con sus herramientas.
La tabla utiliza el espacio restante, con desplazamiento interno en ambos
ejes y encabezados fijos. Se conserva la letra de 12 px de las celdas. En
pantallas bajas se mantiene una altura mínima del espacio de trabajo y se
permite bajar por la zona principal, evitando recortar los controles.

Después del contenedor completo de la hoja está `sheetSecondary`: las cuatro
tarjetas y las validaciones adicionales. Las tarjetas conservan su diseño
compacto, fuentes de datos y colores; no son fijas ni flotantes. Quedan fuera
de la vista inicial y se consultan bajando por el área principal o con el
enlace «Resumen y validaciones» del pie de la hoja. Ese desplazamiento es
independiente del desplazamiento interno de filas/columnas de la tabla.

El estado de guardado también se refleja junto a las herramientas mediante
`toolbarSaveStatus`, utilizando el mismo estado local que la tarjeta inferior;
no introduce otro mecanismo de guardado ni requiere bajar para ver pendientes.

`Pantalla completa` es un modo de enfoque dentro de la aplicación: oculta
temporalmente menú, encabezado y sección secundaria. El mismo botón o Esc restaura
la vista normal sin cambiar la preferencia guardada del menú. No utiliza ni
requiere el modo de pantalla completa del navegador.

Los repintados de filas y el guardado conservan el desplazamiento de la tabla;
Ctrl+S también conserva la celda activa y su selección, si la fila sigue en
el conjunto. Una búsqueda, cambio de página, conjunto o cartera vuelve al
inicio vertical. La edición sigue usando borradores locales y guardado
explícito con motivo: no se añadió guardado automático.

## Herramientas de hoja interactiva

La tabla HTML existente se amplía con `worksheet-grid-model.js`,
`worksheet-grid.js` y `worksheet-grid.css`; no se incorporó una dependencia
externa ni se sustituyeron las reglas financieras. Continúan las páginas de
100 filas y la búsqueda en todo el lote.

- Clic: selecciona sin activar el editor. Arrastre o Shift+clic: rango. Ctrl/Cmd+clic: rangos
  separados. La numeración selecciona filas; los encabezados, columnas.
- Flechas, Tab y Enter navegan. F2 o doble clic permiten mover el cursor dentro
  del texto; Esc vuelve a navegación. Ctrl+B/I/U aplica formato únicamente con
  foco en la tabla. Ctrl+S sigue guardando datos con motivo.
- Ctrl+C copia TSV con comillas y saltos de línea compatibles con Excel.
  Ctrl+V pega como borrador: se verifica el tamaño completo antes de aplicarlo
  y se rechazan bloques que incluyan columnas calculadas o excedan la página.
  Los controles y aprobaciones del servidor siguen siendo obligatorios.
- Colores de relleno/texto, negrita, cursiva, subrayado, alineación, texto de
  10–24 px y ajuste de texto se aplican a la selección. Las alertas de
  validación conservan su prioridad visual. «Sin formato» no borra valores.
- Los bordes de encabezado/numeración permiten arrastrar tamaños con guía.
  Doble clic ajusta al contenido de la página visible. Los separadores también
  funcionan con flechas. «Texto completo» muestra el valor sin truncarlo.
- «Columna» aplica formato a esa columna en todas las páginas, sin enumerar
  miles de filas. Los rangos de celdas y filas afectan la página seleccionada.
  El zoom de 70–150 % solo cambia la tabla, no el navegador.
- El clic derecho ofrece operaciones según permisos. Si el navegador deniega
  el portapapeles del menú, se indican los atajos Ctrl+C/Ctrl+V.

### Minibarra flotante (sin barra permanente)

La minibarra `formatToolbar` está fuera del flujo de la hoja y oculta inicialmente.
Al terminar una selección izquierda aparece junto al rango, con iconos B/I/U,
relleno, texto, alineación, tamaños, copiar y más opciones. Cada icono tiene
nombre accesible y tooltip. Las paletas compactas incluyen colores predefinidos
y color personalizado. Tamaño, zoom, ajuste y restauración siguen disponibles;
en «⋯» están rango, fila/columna, deseleccionar, quitar formato y recuperación
del guardado visual. Ninguna herramienta anterior fue eliminada.

Los botones conservan el foco y la selección de la tabla. Escape, clic exterior,
desplazamiento de la tabla/zona principal, redimensionamiento o inicio de edición
ocultan el menú. Durante un arrastre de rango aparece solo al soltar, nunca
durante un cambio de tamaño. Posición y paneles se limitan al tamaño de pantalla.
Escape cierra primero la minibarra; un segundo Escape puede salir del modo de
enfoque. F2 o doble clic activan la edición del texto; las flechas navegan cuando
no se está editando. Los controles de formato siguen usando el permiso existente
`capabilities.format` y el servidor mantiene sus comprobaciones originales.

Ctrl/Cmd+Z y «Deshacer borrador» revierten únicamente cambios de datos pendientes
en la página actual, incluida una pegada múltiple como bloque. La escritura en
una misma celda se agrupa durante intervalos de 1,2 segundos. El historial está
solo en memoria, limitado a 50 acciones y aproximadamente 1 MiB de caracteres
serializados; se limpia al guardar, descartar o repintar/cambiar la página.
No revierte operaciones financieras guardadas, aprobaciones, importaciones ni
formatos autoguardados. El deshacer vuelve a pasar por los mismos controles
locales y conserva la obligación de motivo y validación del servidor al guardar.
No se añadieron migraciones ni cambios a los datos o al almacenamiento visual.

Verificación de la minibarra: 25 pruebas Django (plantilla, hoja, permisos,
concurrencia, exportaciones y presentación) y 10 pruebas Node (selección,
TSV, formatos y deshacer) superadas. Comprobación visual con datos sintéticos:
clic/Shift/arrastre, colores y subrayado sin perder rango, alineación, doble
clic, copiar/pegar, error local de importe y deshacer, guardado y recarga,
redimensionamiento, cierre exterior/scroll/Escape y pantalla de 390 px sin
desbordamiento horizontal de página. Captura: `worksheet-floating-preview.png`.
La cartera real se comprobó solo en lectura: 38.042 filas, 35.106 principales,
2.936 en revisión, revisión financiera 2 sin cambios.

### Persistencia visual separada

Los formatos son personales por usuario/cartera y se asocian a UUID de fila y
nombre estable de columna. No se guardan por posición de página. La nueva
API POST `presentation/` valida área, permisos, UUID, propiedades admitidas,
colores hexadecimales, tamaños, cantidad de operaciones y versión.

Se guardan automáticamente en archivos cifrados dentro de
`ARNOLD_FILE_ROOT/presentation/`, fuera de los estáticos y de las rutas públicas.
Se reutiliza el cifrado del sistema. No hay migraciones ni nuevos modelos;
no se escriben valores de deudores en estos archivos. Se añade únicamente un
evento de auditoría visual con cantidad de operaciones y versión.

El guardado agrupa operaciones, usa bloqueo entre procesos y reemplazo atómico.
Un conflicto de otra pestaña conserva lo pendiente: «Actualizar formato» lee
la versión nueva y vuelve a aplicar las operaciones propias. Las descargas y
cambios de página se bloquean mientras quede formato por guardar. «Restaurar
tamaños» no elimina colores ni datos; solo anchos, alturas y zoom personales.

Límites: 100 operaciones por petición, hasta 100 filas y 10.000 celdas objetivo
por lote de operaciones; documento de presentación máximo 4 MiB. Una columna
completa se guarda como una única regla. El almacenamiento privado debe estar
incluido en copias de seguridad y ser compartido por los procesos que atienden
la aplicación. Despliegues con varios servidores requieren un volumen con
bloqueos de archivos compatibles; no basta un disco local diferente por nodo.

El exportador existente conserva, cuando corresponde, colores, fuentes,
alineaciones, ajuste de texto y tamaños personales del usuario que descarga,
usando todas las filas del conjunto, no solo la página. Conserva los tipos
numéricos, fechas, identificadores y protección frente a fórmulas inyectadas.
La hoja de trazabilidad identifica también la versión del formato personal.

Pruebas específicas: `python manage.py test apps.workflow.test_presentation`
y `node --test tools/worksheet_grid.test.cjs`. La prueba visual aislada usa
datos ficticios; sus preferencias se conservan durante la ejecución del
servidor de prueba, no sustituyen la persistencia cifrada de la aplicación real.

## Archivos exportados

Los botones descargan dos XLSX separados: `Principal` y `Problemas`. Cada uno
incluye una hoja `Trazabilidad`, periodo, SHA-256 del original, revisión,
usuario, cantidad de filas y clasificación confidencial. Se exportan todas las
filas del conjunto completo, sin limitar por la búsqueda o por la página
visibles. La API mantiene su filtro opcional para consumidores explícitos;
estos botones no lo envían. Una descarga sin filas se rechaza, no crea un
archivo vacío. Los borradores impiden descargar con una advertencia visible;
el botón no queda desactivado silenciosamente por ese motivo.

El exportador conserva nombres, orden y columnas adicionales de los encabezados
originales cifrados. En encabezados repetidos, solo la ocurrencia seleccionada
por el perfil recibe las ediciones aprobadas; las otras conservan su valor de
origen. Los campos de trabajo que no estaban en el origen y las columnas de
control se añaden al final. Las fórmulas de origen se conservan como texto
neutralizado, no se ejecutan. Esto no recupera estilos arbitrarios que el
adaptador no almacenó; conserva los formatos financieros y personales soportados.

La respuesta HTTP incluye MIME XLSX, Content-Disposition, número de filas y
revisión en `X-ARNOLD-Export-Rows` / `X-ARNOLD-Export-Revision`. El navegador
verifica tipo de respuesta, conteo y firma ZIP antes de iniciar la descarga.
La firma es un control de transporte, no sustituye la validación de contenido.

La descarga exige `batches.export_batch`, un área autorizada, ausencia de
borradores locales y la revisión actual. Los números se exportan como números,
los identificadores como texto y las fechas ingresadas como fechas. El texto
con prefijos de fórmulas se neutraliza. Los originales no se modifican.

Esta salida es preliminar. No aprueba el lote ni certifica cancelaciones. El
puente de importación en ARDUR-BETA continúa siendo una integración posterior.

## Ejecución y pruebas

En Windows, desde `backend/`, `./start-local.ps1` arranca web y trabajador. Para
preparar lotes antiguos: `python manage.py prepare_worksheets`.

El arranque local usa `--noreload`: después de cambiar plantillas hay que
reiniciar ese servidor. Recargar solo el navegador puede mezclar una plantilla
anterior en memoria con un JavaScript nuevo. No requiere migraciones ni volver
a cargar las carteras.

Pruebas de persistencia/seguridad/descarga:
`python manage.py test apps.workflow.test_worksheet`.

`tools/worksheet_ui_fixture.py` sirve únicamente datos sintéticos en
`127.0.0.1:8011` para comprobar el controlador visual. No concede sesiones ni
accede a las carteras de la aplicación. Producción continúa usando PostgreSQL
y Celery/Redis; SQLite es exclusivamente desarrollo.

Verificación del diseño de hoja principal: 17 pruebas de dashboard/hoja superadas,
sintaxis JavaScript comprobada y pruebas visuales con 100 filas sintéticas en
1440×900, 768×900 y 390×844. Se comprobó persistencia del menú al recargar,
modo de enfoque/Esc, ubicación de las tarjetas bajo la primera pantalla,
búsqueda y edición con Ctrl+S conservando celda y desplazamiento en ambos ejes.
La aplicación real se comprueba en lectura, sin editar su cartera.

## Verificación de confirmación y descargas (16 de octubre de 2026)

- 30 pruebas Django y 10 pruebas Node superadas. Incluyen HTTP, MIME,
  Content-Disposition, XLSX legible, paginación completa, columnas originales,
  encabezados repetidos, separación de conjuntos, motivo, permisos y cambios
  monetarios pendientes que no se exportan antes de aprobarse.
- Prueba de navegador con datos ficticios: sin cambios, cancelar, motivo vacío,
  Ctrl+S, guardar y descargar, error de guardado que conserva borradores y
  error de descarga que no repite el guardado. El XLSX sintético descargado
  tiene 100 filas e incluye el nombre corregido tras confirmar.
- Descargas reales desde los botones: 35.106 filas principales y 2.936 de
  revisión, revisión 2. Apertura con lector XLSX, CRC de todo el ZIP,
  encabezados, identificadores como texto, formatos monetarios y totales por
  fila verificados. Ninguna fila de origen aparece en ambos conjuntos; la
  unión contiene 38.042 filas. Sin modificaciones a los registros reales.
- No se reprodujo una caída del endpoint inicial: la descarga anterior ya
  contenía 35.106 filas. Se corrigieron comportamientos comprobados del código:
  botón silenciosamente inhabilitado por borradores, filtro de búsqueda que
  restringía el lote y lista fija que omitía columnas originales adicionales.

`tools/verify_worksheet_downloads.py` vuelve a comprobar, en lectura y sin
imprimir datos personales, los dos archivos de esta cartera. Los XLSX de
prueba no se incorporan al repositorio; `outputs/` está excluido de Git.

Archivos de esta mejora:
`backend/templates/dashboard/worksheet.html`, `backend/static/css/worksheet.css`,
`backend/static/js/worksheet-app.js`, `backend/apps/workflow/sheet_exports.py`,
`backend/apps/workflow/views.py`, `backend/apps/dashboard/tests.py`,
`backend/apps/workflow/test_worksheet.py`, `tools/worksheet_ui_fixture.py`,
`tools/verify_worksheet_downloads.py` y este documento.

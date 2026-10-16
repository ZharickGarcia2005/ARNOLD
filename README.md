# ARNOLD · Módulo Preliminar

Prototipo funcional de la interfaz para validar bases mensuales de cobranza coactiva.

## Qué incluye

- Tablero de resultados y calidad.
- Tabla tipo Excel con búsqueda y filtros.
- Alertas por duplicados, conflictos y pagos/cancelaciones.
- Edición condicionada por rol.
- Solicitudes de aprobación para cambios sensibles.
- Bitácora visible de acciones.
- Matriz de permisos y controles de seguridad.
- Datos de la tabla operativa completamente ficticios.
- Catálogo seguro de las cuatro fuentes analizadas, sin copiar datos personales.
- Esquemas, alias de columnas y once reglas iniciales del motor de validación.

## Cómo abrirlo

La interfaz ahora forma parte de Django. Desde **backend/** ejecute:

```powershell
python manage.py migrate
python manage.py runserver
```

Luego abra `http://127.0.0.1:8000/`.

## Alcance de esta versión

La hoja preliminar consulta las filas reales del lote seleccionado, en páginas
de 100 filas, y permite edición con guardado explícito, control de versiones,
revisión de cambios protegidos y dos descargas XLSX (principal/problemas).
Sin lotes muestra un estado vacío, sin datos de demostración. La carga mensual
está conectada al backend: recibe un XLSX autenticado, lo pone en cuarentena,
crea `Batch`/`Record`/`ValidationRun`, ejecuta el motor y persiste incidencias
idempotentes. El despliegue productivo continúa bloqueado hasta disponer de MFA,
antivirus operativo, volumen cifrado, copias y monitoreo.

El análisis agregado de los libros de julio, agosto, la exportación XLS heredada
y las órdenes 030–034 se conserva en **docs/SOURCE_ANALYSIS.md**. La nueva hoja
operativa utiliza la base real; el dashboard anterior y su catálogo JavaScript
quedan como presentación heredada fuera de la ruta principal.

## Siguiente etapa técnica

1. Probar el adaptador con una copia anonimizada y confirmar el mapa de columnas.
2. Inicio de sesión individual con segundo factor para cargos sensibles.
3. Ampliar la consulta de lotes e incidencias con búsqueda y filtros en servidor.
4. Construir el exportador ARDUR separado y aprobado.
5. Completar el cierre/aprobación global del lote y la evidencia de pagos.
6. Ampliar la comparación histórica sobre las correcciones de la hoja.
7. Despliegue privado con HTTPS, copias de seguridad y monitoreo.

## Motor financiero

La primera versión del motor de reglas, comparación mensual y exportación XLSX
está implementada como código Python puro bajo `backend/apps/validation/`. No
modifica ni importa código de ARDUR-BETA y se prueba únicamente con datos
ficticios. Puede conservar los identificadores con ceros iniciales cuando el
adaptador entrega texto o el valor `raw`; emite incidencias cuando un
`PaymentClaim` no declara doble control, obliga a registrar qué apariciones de
columnas duplicadas se utilizaron y evita truncar evidencia en Excel. Consulte
**docs/FINANCIAL_ENGINE.md** para el contrato y sus límites.

## Backend iniciado

La base del backend utiliza Django 5.2 LTS. El desarrollo local usa SQLite; el
despliegue está preparado para PostgreSQL, Celery y Redis como varios servicios
con una sola base de negocio para mantener consistencia. La API de carga y el
worker ya están conectados. Consulte **backend/BACKEND_ARCHITECTURE.md**,
**backend/compose.yaml** y **docs/REAL_DATA_INTEGRATION.md**.

La interfaz de revisión y sus permisos se describen en
**docs/PRELIMINAR_WORKSHEET.md**.

## Organización Django

- **backend/core/**: configuración, URLs, ASGI, WSGI y Celery.
- **backend/core/settings/**: configuración base, desarrollo y producción.
- **backend/apps/**: dominios de negocio separados.
- **backend/templates/**: plantillas HTML y estructura común.
- **backend/static/css/**: estilos propios.
- **backend/static/js/**: JavaScript propio y módulos.
- **backend/static/vendor/**: dependencias frontend externas versionadas.
- **docs/**: análisis, seguridad y material de referencia.
- **tools/**: herramientas de análisis de Excel, fuera del runtime web.

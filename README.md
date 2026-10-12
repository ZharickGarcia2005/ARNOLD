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

Esta versión permite revisar el flujo y la interfaz. El cambio de rol, las cargas y los datos son demostrativos. Antes de utilizar información real se debe conectar un servidor con autenticación, permisos, almacenamiento cifrado, auditoría inalterable y copias de seguridad.

La pantalla **Fuentes** sí refleja estadísticas agregadas obtenidas de los libros de julio, agosto, la exportación XLS heredada y las órdenes 030–034. Los archivos originales no forman parte del frontend. Véase **docs/SOURCE_ANALYSIS.md** para la reconciliación. El catálogo Python de `backend/apps/validation/rules.py` es la autoridad de reglas; `backend/static/js/validator-config.js` es todavía una presentación heredada que deberá consumir ese catálogo en una fase posterior.

## Siguiente etapa técnica

1. Adaptador Excel seguro dentro de ARNOLD para construir los contratos del motor.
2. Inicio de sesión individual con segundo factor para cargos sensibles.
3. Importación y lectura de Excel en segundo plano.
4. Conectar el motor mediante un adaptador ARDUR separado y aprobado.
5. Persistir incidencias sin modificar la evidencia RAW.
6. Conectar el flujo de aprobación de doble control.
7. Despliegue privado con HTTPS, copias de seguridad y monitoreo.

## Motor financiero

La primera versión del motor de reglas, comparación mensual y exportación XLSX
está implementada como código Python puro bajo `backend/apps/validation/`. No
modifica ni importa código de ARDUR-BETA y se prueba únicamente con datos
ficticios. Puede conservar los identificadores con ceros iniciales cuando el
futuro adaptador entrega texto o el valor `raw`; emite incidencias cuando un
`PaymentClaim` no declara doble control, obliga a registrar qué apariciones de
columnas duplicadas se utilizaron y evita truncar evidencia en Excel. Consulte
**docs/FINANCIAL_ENGINE.md** para el contrato y sus límites.

## Backend iniciado

La base del backend utiliza Django 5.2 LTS. El desarrollo local usa SQLite; el
despliegue está preparado para PostgreSQL, Celery y Redis como varios servicios
con una sola base de negocio para mantener consistencia. La API segura, la
autenticación operativa y la conexión del worker todavía están pendientes. Consulte
**backend/BACKEND_ARCHITECTURE.md** y **backend/compose.yaml**.

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

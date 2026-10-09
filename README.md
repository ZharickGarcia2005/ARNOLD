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

La pantalla **Fuentes** sí refleja estadísticas agregadas obtenidas de los libros de julio, agosto, la exportación XLS heredada y las órdenes 030–034. Los archivos originales no forman parte del frontend. Véase **docs/SOURCE_ANALYSIS.md** para la reconciliación y **backend/static/js/validator-config.js** para la presentación de esquemas y reglas.

## Siguiente etapa técnica

1. API segura y base PostgreSQL. El esqueleto inicial está en **backend/**.
2. Inicio de sesión individual con segundo factor para cargos sensibles.
3. Importación y lectura de Excel en segundo plano.
4. Motor de reglas con versiones y evidencia de cada alerta.
5. Flujo de aprobación de doble control.
6. Exportación final a Excel.
7. Despliegue privado con HTTPS, copias de seguridad y monitoreo.

## Backend iniciado

La base del backend utiliza Django 5.2 LTS, PostgreSQL, Celery y Redis. Se
despliega como varios servicios, pero mantiene por ahora una sola base de datos
para garantizar consistencia entre validación, revisión y aprobación. Consulte
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

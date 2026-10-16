# Backend ARNOLD

Base inicial del módulo Preliminar construida con Django 5.2 LTS.

## Servicios

- **web**: autenticación, permisos, lotes, revisión y aprobaciones.
- **worker**: procesamiento asíncrono de Excel mediante Celery.
- **db**: PostgreSQL como única fuente de verdad.
- **redis**: cola de trabajos; no guarda información definitiva.

## Prueba local sin contenedores

Desde esta carpeta:

```powershell
python manage.py migrate
python manage.py test
python manage.py runserver
```

La prueba local utiliza SQLite solamente para desarrollo. La configuración de
despliegue utiliza PostgreSQL.

Para ejecutar la web y el trabajador local juntos en Windows:

```powershell
.\start-local.ps1
```

También pueden ejecutarse en dos terminales: `manage.py runserver` y
`manage.py process_pending --watch`, usando el Python de `.venv`. En desarrollo
`ARNOLD_LOCAL_QUEUE=1` es el valor predeterminado y las tareas se recogen desde
la base local. `ARNOLD_LOCAL_QUEUE=0` conserva Celery/Redis para desarrollo con
contenedores. Producción sigue usando Celery/Redis. La lista de carteras y las
filas paginadas ya consultan la base real. La hoja nueva permite editar celdas,
guardar con motivo, solicitar/aprobar cambios protegidos y descargar los
conjuntos principal/problemas. La búsqueda exacta por identificador consulta
todo el lote; se muestran 100 filas por página. Consulte
`../docs/PRELIMINAR_WORKSHEET.md`.

## Inicio con contenedores

1. Para desarrollo, copiar `.env.development.example` como `.env`.
2. Para producción, copiar `.env.example` como `.env` y reemplazar todas las claves y contraseñas.
3. Ejecutar `docker compose up --build`.
4. Comprobar `http://127.0.0.1:8000/healthz`.

El archivo `compose.yaml` todavía es una base de despliegue, no una receta de
producción cerrada: antes de aceptar cargas debe añadirse un servicio ClamAV o
un escáner equivalente y su cliente dentro de la imagen. El comando de ejemplo
`clamdscan` no está instalado por el `Dockerfile` actual; producción rechazará
la carga de forma segura hasta completar esa infraestructura.

## Carpetas principales

- `core/`: configuración Django y puntos de entrada.
- `core/settings/`: ajustes por entorno.
- `apps/`: módulos de negocio.
- `templates/`: plantillas Django.
- `static/css/`: estilos fuente.
- `static/js/`: scripts propios.
- `static/vendor/`: librerías externas controladas.
- `staticfiles/`: salida generada por `collectstatic`; no se edita.

## Estado de seguridad

La carga inicial aplica permiso de servidor, CSRF, límite durante streaming,
cuarentena, inspección XLSX, SHA-256, cifrado autenticado de filas/evidencia e
idempotencia. Producción exige claves y un comando antivirus. Todavía no debe
recibir información real hasta completar MFA, proxy HTTPS, volumen cifrado,
copias, monitoreo y la prueba controlada con datos anonimizados.

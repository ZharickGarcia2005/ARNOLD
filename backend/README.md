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

## Inicio con contenedores

1. Para desarrollo, copiar `.env.development.example` como `.env`.
2. Para producción, copiar `.env.example` como `.env` y reemplazar todas las claves y contraseñas.
3. Ejecutar `docker compose up --build`.
4. Comprobar `http://127.0.0.1:8000/healthz`.

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

El esqueleto ya aplica cookies seguras en producción, HSTS, límite de carga,
doble control, campos preparados para cifrado y auditoría inmutable a nivel de
modelo. Todavía no debe recibir información real hasta implementar gestión de
claves, MFA, antivirus, proxy HTTPS y almacenamiento cifrado.

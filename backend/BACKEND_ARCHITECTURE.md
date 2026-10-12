# Arquitectura inicial del backend ARNOLD

## Decisión

ARNOLD comienza como una arquitectura multiservicio de despliegue con un núcleo
de negocio modular. SQLite se usa en desarrollo local y PostgreSQL es el destino
de despliegue. Se mantiene una sola base de negocio porque los lotes, registros,
incidencias, aprobaciones y auditoría requieren consistencia transaccional fuerte.

Los servicios iniciales son:

1. **web**: hoy ofrece dashboard, administración y health check; la API,
   autenticación operativa, permisos y flujo de aprobación son el objetivo.
2. **worker**: existe el esqueleto Celery; la lectura aislada de Excel y la
   conexión con el motor siguen pendientes.
3. **db**: PostgreSQL; único propietario persistente de los datos de negocio.
4. **redis**: cola de trabajos, nunca fuente de verdad.

Esta división evita que una carga de Excel bloquee la aplicación y permite
escalar los trabajadores sin multiplicar prematuramente bases y transacciones.

## Opinión sobre una sola base

Una sola base es adecuada en esta etapa porque:

- el equipo todavía está descubriendo las reglas definitivas;
- las operaciones de validación y aprobación necesitan transacciones ACID;
- simplifica copias de seguridad, recuperación, cifrado y monitoreo;
- evita inconsistencias entre servicios durante el arranque del producto.

La condición es que el acceso se realice a través del dominio propietario. No se
deben crear varios servicios independientes que escriban libremente sobre las
mismas tablas.

## Límites internos

- **accounts**: usuarios, roles y áreas.
- **batches**: lotes y registros cifrados.
- **validation**: incidencias producidas por reglas.
- **workflow**: solicitudes y doble aprobación.
- **audit**: eventos inmutables.

Los módulos se comunican mediante interfaces internas y eventos de aplicación.
No se permiten dependencias circulares.

## Cuándo separar bases

Un módulo pasa a microservicio y base independiente únicamente cuando exista al
menos una de estas razones:

- necesita escalar de forma muy diferente;
- tiene un ciclo de despliegue independiente;
- lo mantiene otro equipo;
- necesita un nivel de aislamiento normativo diferente;
- una falla del módulo no debe afectar las operaciones restantes.

Al separarlo, su información será privada y los demás módulos accederán por API
o mensajes. Nunca mediante consultas directas a sus tablas.

## Próximos pasos

1. Implementar el adaptador Excel de ARNOLD y su carga en cuarentena con SHA-256.
2. Conectar el núcleo puro de once reglas al worker sin duplicar la lógica.
3. Completar usuarios, grupos de permisos y doble control operativo.
4. Completar cifrado de campos y gestión de claves.
5. Implementar eventos de auditoría con cadena hash.
6. Publicar endpoints versionados para el frontend.
7. Añadir proxy HTTPS, MFA, antivirus y respaldos.


# Seguridad propuesta para ARNOLD

## Condición de uso

El prototipo actual contiene únicamente información ficticia. No debe recibir datos reales hasta que exista un servidor autenticado, una base de datos protegida y los controles descritos aquí.

## Jerarquía de acceso

| Rol | Alcance |
|---|---|
| Validador | Consulta lotes asignados, corrige campos comunes y solicita cambios sensibles. |
| Jefe de área | Todo lo anterior, aprueba cambios sensibles, reasigna trabajo y cierra lotes. |
| Auditor | Consulta registros, decisiones y bitácora; no modifica datos. |
| Administrador | Administra usuarios, roles y configuración. Las operaciones de negocio deben quedar igualmente auditadas. |

Los permisos se validarán siempre en el servidor. Ocultar un botón en la pantalla no constituye una medida de seguridad.

## Doble control

Requieren aprobación de un jefe:

- Cambio de título o expediente.
- Cambio de identificación del contribuyente.
- Cambio de monto, estado de pago o cancelación.
- Eliminación lógica o exclusión de un registro.
- Cierre y exportación definitiva del lote.

La solicitud debe conservar el valor anterior, valor solicitado, motivo, usuario solicitante, aprobador y fecha. El solicitante no puede aprobar su propio cambio.

## Trabajo simultáneo

Cada registro tendrá un número de versión. Al guardar, el servidor verificará que nadie lo haya modificado después de que el usuario lo abrió. Si cambió, ARNOLD mostrará ambas versiones y pedirá conciliar el conflicto; nunca sobrescribirá silenciosamente.

Los lotes pueden dividirse por usuario, pero los jefes tendrán una vista consolidada del avance.

## Bitácora

La bitácora será de solo anexado y registrará:

- Inicio y cierre de sesión.
- Carga y descarga de archivos.
- Consulta masiva o exportación.
- Valor anterior y nuevo de cada cambio.
- Regla que produjo una alerta.
- Solicitudes, aprobaciones, rechazos y cierres.
- Cambios de roles y usuarios.

Los usuarios de negocio no podrán editar ni eliminar la bitácora. Se conservará una copia separada de la base operativa.

## Protección de archivos Excel

- Aceptar inicialmente XLSX y CSV; rechazar libros con macros.
- Mantener cada archivo en cuarentena hasta validar tipo real, tamaño y estructura.
- Escanear malware antes del procesamiento.
- Limitar tamaño, número de filas y columnas para evitar cargas abusivas.
- No ejecutar fórmulas del archivo recibido.
- Neutralizar celdas que comiencen con `=`, `+`, `-` o `@` al exportar texto, evitando inyección de fórmulas.
- Conservar el archivo original con huella digital para demostrar que no fue alterado.
- No copiar libros reales, filas ni información personal al código del frontend. El navegador solo recibe registros autorizados por la API y nunca rutas locales de archivos.
- Detectar copias del mismo lote mediante huella y reconciliación de claves para impedir una doble importación.
- Tratar errores almacenados de fórmula (`#N/A`, `#NAME?`, entre otros) como incidencias; el servidor recalcula las transformaciones aprobadas.

## Controles de cuenta

- Usuario individual; quedan prohibidas las cuentas compartidas.
- Contraseñas con hash Argon2id y política de bloqueo progresivo.
- Segundo factor obligatorio para jefes y administradores.
- Sesiones cortas, cookies seguras y cierre remoto de sesión.
- Alta, cambio de cargo y baja de usuarios con aprobación administrativa.
- Desactivar inmediatamente las cuentas de personal que deja la empresa.

## Infraestructura recomendada

- Aplicación web servida exclusivamente por HTTPS.
- API privada que aplica permisos y reglas.
- PostgreSQL cifrado para registros, versiones y aprobaciones.
- Almacenamiento cifrado separado para archivos originales y exportaciones.
- Procesador aislado para importar Excel.
- Copias de seguridad cifradas y pruebas periódicas de restauración.
- Monitoreo de accesos anómalos, exportaciones grandes y fallos repetidos.

### Decisión inicial del backend

ARNOLD comienza con servicios separados para la aplicación web, procesamiento
de Excel, PostgreSQL y Redis. Solo PostgreSQL es fuente de verdad. Los módulos de
usuarios, lotes, validación, aprobaciones y auditoría permanecen dentro de un
núcleo modular para conservar transacciones consistentes. Cuando un módulo se
convierta en microservicio independiente tendrá datos privados y los demás
servicios accederán exclusivamente por API o mensajería.

## Datos mínimos del módulo Preliminar

- Lote e identidad del archivo original.
- Orden, título de crédito, título preliminar y expediente.
- Código de cliente, identificación, CIU, cuenta de agua, predio e ID de plan.
- Valores de emisión, intereses, coactiva y total.
- Estado de validación, regla de alerta y nivel de riesgo.
- Usuario asignado, versión, fechas y evidencia.
- Solicitud y decisión para cambios protegidos.

## Reglas de salida

La exportación final debe incluir un identificador de lote, fecha, versión del motor de reglas y usuario que aprobó. Los archivos descargados deben tener caducidad y marca de clasificación. Las exportaciones con datos completos solo estarán disponibles para roles autorizados.

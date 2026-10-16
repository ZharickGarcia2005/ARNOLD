# Integración inicial de datos reales

## Flujo implementado

```text
XLSX mensual
→ recepción autenticada y permiso batches.import_batch
→ cuarentena privada, SHA-256, inspección ZIP y antivirus configurable
→ adaptador Excel (una hoja explícita)
→ Record cifrado + índices HMAC
→ ValidationRun reproducible
→ once reglas del motor financiero
→ ValidationIssue idempotente y evidencia cifrada
→ estado ready, review o failed
```

La API de entrada es `POST /api/v1/batches/uploads/`. El navegador envía
`file`, `period`, `sheet_name`, `header_row`, `schema_name` y, opcionalmente,
`profile_id` y `reference_batch_id`. La respuesta `202` contiene los UUID del
lote y de la ejecución, además de una URL de estado.

## Trazabilidad conservada

- Nombre visible, SHA-256, tamaño, periodo, usuario, área, hoja y fila de
  encabezados.
- Encabezados originales y todas sus apariciones.
- Fila original, valor interpretado, texto original, fórmulas y errores.
- Versión del adaptador, versión del motor, reglas ejecutadas y omitidas.
- Huella estable de cada incidencia para que un reintento no la duplique.

Los identificadores no se guardan en columnas de búsqueda en texto claro:
`CLAVE`, `CIU` y `CEDULA_RUC` utilizan HMAC. La fila y la evidencia completa se
cifran con AES-256-GCM. Los mensajes de las incidencias no deben contener PII.

## Límites intencionales del primer corte

- Solo `.xlsx`; el `.xls` histórico tendrá un adaptador aislado posterior.
- Solo `carteraMensual` y una hoja indicada expresamente por carga.
- La misma combinación de archivo, área, periodo, hoja y perfil no se duplica;
  el mismo libro puede registrarse con otra hoja o perfil explícito.
- Un libro multihoja no se combina: hacerlo exigiría agregar `source_sheet` al
  contrato y separar archivo físico de dataset lógico.
- Una cartera con encabezados monetarios repetidos queda bloqueada si no existe
  un perfil explícito y probado.
- Las hojas consolidadas con cientos de miles de fórmulas quedan fuera de este
  corte; requieren una política de valor calculado y agregación de incidencias.
- Producción falla al iniciar si faltan claves, PostgreSQL o antivirus. El
  volumen que almacena originales también debe estar cifrado por infraestructura.

## Coexistencia con ARDUR-BETA

ARDUR-BETA se mantiene como repositorio y base separados. Su cadena
`ImportacionCartera → RegistroCarteraRaw → RegistroCarteraStaging →
CarteraDetalle` depende de catastro, clientes y expedientes; no se copian esos
modelos dentro de ARNOLD.

El puente previsto es un contrato versionado del lado de ARNOLD. Todavía no
está implementado; la hoja actual ya permite correcciones, doble control de
cambios y descargas preliminares. El cierre global del lote y el archivo
específico de intercambio ARDUR todavía están pendientes. El objetivo es:

1. ARNOLD valida y conserva la revisión con aprobación de cambios protegidos.
2. ARNOLD deberá exportar la plantilla aceptada por ARDUR con estos 13
   encabezados en la primera fila y sin duplicados: `CIU`, `CEDULA_RUC`,
   `NOMBRES`, `CLAVE`, `DIRECCION`, `PARROQUIA`, `TELEF`, `CORREO`,
   `TOTAL_EMISION`, `TOTAL_INTERES`, `TOTAL_COACTIVA`, `TOTAL_RECARGO` y
   `MESES_DEUDA`.
3. Un futuro manifiesto separado incluirá hashes, periodo, versiones, conteos y
   aprobador.
4. ARDUR importa el archivo mediante su flujo existente y vuelve a aplicar sus
   controles de catastro e histórico.

El archivo de intercambio también deberá cumplir el contrato vigente de ARDUR:
`NOMBRES` y al menos `CLAVE` o `CIU`; importes no negativos con máximo dos
decimales; `MESES_DEUDA` entero no negativo. La carga, revisión y aprobación
final permanecen bajo el rol `JEFE_FINANCIERA` de ARDUR, y sus bytes no pueden
reimportarse de forma idéntica porque ARDUR registra un SHA-256 único.

Hasta que el responsable de ARDUR apruebe una API, este puente será manual y no
escribirá en sus tablas ni importará `ardur.apps.*`.

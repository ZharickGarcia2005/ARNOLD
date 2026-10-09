/*
 * Catálogo y reglas derivados del análisis estructural de las fuentes de julio
 * y agosto de 2026. Este archivo contiene solo metadatos agregados: nunca PII.
 */
(function () {
  const schemas = {
    carteraMensual: {
      required: ["CIU", "CEDULA_RUC", "NOMBRES", "CLAVE", "TOTAL_EMISION", "TOTAL_INTERES", "TOTAL_COACTIVA", "TOTAL_RECARGO", "MESES_DEUDA"],
      optional: ["DIRECCION", "PARROQUIA", "TELEF", "CORREO"],
      primaryKey: ["CLAVE"],
      comparisonKey: ["CEDULA_RUC", "CIU"],
      rowIdentity: ["CEDULA_RUC", "CIU", "CLAVE"]
    },
    carteraUnificada: {
      required: ["PREDIO_MUN", "NOMBRES", "CEDULA_RUC", "CIU", "EMISION", "INTERES", "COACTIVA", "TOTAL_RECARGO", "VALOR_TOTAL", "TITULOS"],
      optional: ["TP", "EXP", "CLAVE", "OP", "OC", "DIGIT", "DIRECCION", "PARROQUIA", "COD_PARROQUIA", "ZONA", "SECTOR", "MANZANA", "PREDIO", "ID_PLAN", "TELEFONO", "CORREO"],
      primaryKey: ["CEDULA_RUC", "CIU"]
    },
    ordenPreliminar: {
      required: ["PREDIO_MUN", "NOMBRES", "CEDULA_RUC", "CLAVE", "CIU", "EMISION", "INTERES", "RECARGO", "TOTAL"],
      optional: ["TP", "EXP", "OP", "OC", "DIGIT", "DIRECCION", "PARROQUIA", "PARROQ", "ZONA", "SECTOR", "MZ", "PREDIO", "ID_PLAN", "TELEFONO", "CORREO", "TITULOS", "DIGITADOR", "FECHA", "HORA", "NOVEDAD"],
      primaryKey: ["CEDULA", "CIU"]
    }
  };

  const sources = [
    {
      id: "julio-2026",
      label: "Cartera vencida · julio 2026",
      format: "XLSX",
      status: "recognized",
      rawRows: 37330,
      resultRows: 26927,
      sheets: 6,
      schema: "carteraMensual",
      notes: [
        "La hoja principal contiene encabezados monetarios duplicados.",
        "El consolidado usa el segundo bloque monetario y excluye 10.403 claves.",
        "La versión sin coactiva elimina 500 registros; no recalcula montos."
      ]
    },
    {
      id: "agosto-2026",
      label: "Cartera vencida · agosto 2026",
      format: "XLSX",
      status: "warning",
      rawRows: 38042,
      resultRows: 32560,
      sheets: 5,
      schema: "carteraMensual",
      notes: [
        "CLAVE es única en la fuente; CEDULA_RUC y CIU pueden repetirse.",
        "El consolidado representa una fila por CEDULA_RUC + CIU y no debe sumar duplicados.",
        "Hay 18.234 errores de fórmula almacenados; 42 consolidaciones requieren revisión, 4 de ellas en grupos repetidos."
      ]
    },
    {
      id: "legado-coactiva",
      label: "Exportación heredada · coactiva",
      format: "XLS",
      status: "duplicate",
      rawRows: 38042,
      resultRows: 38042,
      sheets: 1,
      schema: "carteraMensual",
      notes: [
        "38.038 filas coinciden exactamente con la hoja fuente de agosto.",
        "Solo 4 filas difieren; debe tratarse como copia histórica, no como un lote adicional.",
        "El formato XLS se convertirá en un entorno aislado antes de validarlo."
      ]
    },
    {
      id: "ordenes-030-034",
      label: "Órdenes preliminares 030–034",
      format: "XLSX",
      status: "warning",
      rawRows: 2619,
      resultRows: 2619,
      sheets: 6,
      schema: "ordenPreliminar",
      notes: [
        "Las 2.618 filas con clave coinciden con el consolidado de julio; 2.612 coinciden con agosto.",
        "La hoja de inconsistencias contiene 50 registros.",
        "608 filas no tienen ID de plan o importes completos y requieren evidencia antes de cerrar."
      ]
    }
  ];

  const rules = [
    { id: "SCHEMA-001", severity: "critical", title: "Columnas requeridas", description: "Detener el lote si faltan columnas obligatorias o el tipo de hoja no puede reconocerse." },
    { id: "SCHEMA-002", severity: "critical", title: "Encabezados duplicados", description: "Conservar cada columna original con sufijo y bloquear asignaciones ambiguas. Para julio, el consolidado comprobado usa el segundo bloque monetario." },
    { id: "KEY-001", severity: "critical", title: "Clave mensual única", description: "CLAVE identifica la fila de la cartera mensual. CEDULA_RUC + CIU se usa para consolidar y comparar." },
    { id: "KEY-002", severity: "warning", title: "Conflicto de identidad", description: "Alertar si una misma CLAVE cambia de CEDULA_RUC o CIU entre meses." },
    { id: "DUP-001", severity: "warning", title: "Repetición consolidable", description: "Agrupar por CEDULA_RUC + CIU, pero no sumar importes. Comparar las filas normalizadas y escalar cualquier diferencia." },
    { id: "CAT-001", severity: "warning", title: "Catálogo contradictorio", description: "Alertar si CLAVE_NUEV aparece asociada a identidades distintas o si existe una fila exacta repetida." },
    { id: "FORMULA-001", severity: "critical", title: "Fórmula o error almacenado", description: "No ejecutar fórmulas del libro. Registrar #N/A, #NAME? y similares como evidencia y recalcular únicamente con reglas del servidor." },
    { id: "MONTH-001", severity: "info", title: "Altas y ausencias mensuales", description: "Informar claves nuevas o ausentes. Una ausencia no prueba por sí sola pago o cancelación." },
    { id: "PAYMENT-001", severity: "critical", title: "Pago o cancelación con respaldo", description: "Cambiar el estado solo con una fuente autorizada o evidencia aprobada por un jefe." },
    { id: "ORDER-001", severity: "warning", title: "Orden trazable", description: "Cada fila de orden debe existir en el consolidado origen mediante CEDULA + CIU y conservar el lote de procedencia." },
    { id: "ORDER-002", severity: "critical", title: "Orden incompleta", description: "Marcar CLAVE, ID de plan, importes o referencias faltantes antes de aprobar la orden." }
  ];

  const headerAliases = {
    "CEDULA": "CEDULA_RUC",
    "RUC_CEDULA": "CEDULA_RUC",
    "CONTRIBUYENTE": "NOMBRES",
    "PREDIO MUNICIPAL": "PREDIO_MUN",
    "ID PLAN": "ID_PLAN",
    "TITULO": "TITULOS",
    "MZ": "MANZANA",
    "PARROQ": "COD_PARROQUIA"
  };

  function normalizeHeader(value) {
    const clean = String(value ?? "")
      .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .trim().toUpperCase().replace(/\s+/g, " ");
    return (headerAliases[clean] || clean).replace(/ /g, "_");
  }

  function makeUniqueHeaders(values) {
    const seen = new Map();
    return values.map(value => {
      const base = normalizeHeader(value) || "SIN_ENCABEZADO";
      const count = (seen.get(base) || 0) + 1;
      seen.set(base, count);
      return count === 1 ? base : `${base}__${count}`;
    });
  }

  function recognizeSchema(headers) {
    const normalized = new Set(makeUniqueHeaders(headers).map(h => h.replace(/__\d+$/, "")));
    const candidates = Object.entries(schemas).map(([name, schema]) => ({
      name,
      missing: schema.required.filter(field => !normalized.has(field))
    })).sort((a, b) => a.missing.length - b.missing.length);
    return { schema: candidates[0].name, valid: candidates[0].missing.length === 0, missing: candidates[0].missing };
  }

  function canonicalKey(record, fields) {
    return fields.map(field => String(record[field] ?? "").trim().toUpperCase()).join("|");
  }

  window.ARNOLD_SOURCE_CATALOG = Object.freeze({ version: "2026.09.24", sources, schemas, rules });
  window.ARNOLD_VALIDATOR = Object.freeze({ normalizeHeader, makeUniqueHeaders, recognizeSchema, canonicalKey });
}());

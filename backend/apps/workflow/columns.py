"""Contrato único POR ORDEN: referencia (1), pantalla y dos descargas."""
from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from apps.batches.crypto import decrypt_json
from apps.validation.rules import make_unique_headers, normalize_header

MANIFEST = json.loads(Path(__file__).with_name("order_manifest.json").read_text(encoding="utf-8"))
CONTRACT_VERSION = MANIFEST["version"]
SHEETS = {sheet["id"]: sheet for sheet in MANIFEST["sheets"]}
MONEY_FIELDS = ("TOTAL_EMISION", "TOTAL_INTERES", "TOTAL_COACTIVA", "TOTAL_RECARGO")
PRESENTATION_ALIASES = {"TELEFONO": "TELEF", "EMISION": "TOTAL_EMISION", "INTERES": "TOTAL_INTERES", "RECARGO": "TOTAL_RECARGO", "TOTAL": "SOURCE_TOTAL"}

def canonical(label):
    normalized = normalize_header(label, "ordenPreliminar")
    return PRESENTATION_ALIASES.get(normalized, normalized)

BUSINESS_FIELDS = tuple(dict.fromkeys(canonical(c["label"]) for s in SHEETS.values() for c in s["columns"] if c["label"]))
WORKING_FIELDS = tuple(dict.fromkeys((*BUSINESS_FIELDS, "TOTAL_COACTIVA", "CATASTRO", "MESES_DEUDA", "FECHA_VENCIMIENTO", "ORDEN_PRELIMINAR")))
PROTECTED_FIELDS = frozenset(("CIU", "CEDULA_RUC", "CLAVE", "CATASTRO", "TITULO", "TITULOS", "TITULOS_VENCIDOS", "TITULOS_VENC", "PREDIO_MUN", "OP", "OC", "ORDEN_PRELIMINAR", "SOURCE_TOTAL", "SUBTOTAL", *MONEY_FIELDS, "MESES_DEUDA"))

@dataclass(frozen=True)
class Column:
    field: str
    label: str
    source_field: str = ""
    raw_key: str = ""
    original_header: str = ""
    source_position: int | None = None
    occurrence: int | None = None
    editable: bool = False
    calculated: bool = False
    control: bool = False
    protected: bool = False
    type: str = "text"
    number_format: str = "@"
    width: int = 130
    working: bool = False
    hidden: bool = False
    outline: int = 0
    letter: str = ""
    auxiliary: bool = False

    def payload(self, position):
        return {**asdict(self), "position": position, "export": "saved_working" if self.working else "control" if self.control else "original_evidence",
                "trace": "Record + encabezado/ocurrencia + WorksheetRow/version"}

def excel_letter(position):
    text = ""
    while position:
        position, digit = divmod(position - 1, 26); text = chr(65 + digit) + text
    return text

def kind(field):
    return "money" if field in (*MONEY_FIELDS, "SOURCE_TOTAL", "SUBTOTAL") else "integer" if field in ("NO", "MESES_DEUDA") else "date" if field in ("FECHA", "FECHA_VENCIMIENTO") else "time" if field == "HORA" else "text"

def format_for(field):
    return {"money":"#,##0.00", "integer":"0", "date":"yyyy-mm-dd", "time":"hh:mm:ss"}.get(kind(field), "@")

def headers_for(batch):
    return decrypt_json(batch.headers_ciphertext, associated_data=f"batch-headers:{batch.pk}") if batch.headers_ciphertext else batch.original_headers

def columns_for(batch, order="030"):
    if order not in SHEETS: raise ValueError("Orden de presentación inexistente")
    occurrences = make_unique_headers(headers_for(batch) or [], batch.schema_name)
    counts = Counter(item.normalized for item in occurrences)
    source = []
    for pos, item in enumerate(occurrences, 1):
        source.append({"field": canonical(item.original), "normalized": item.normalized,
                       "raw_key": f"{item.normalized}__{item.occurrence}" if counts[item.normalized] > 1 else item.normalized,
                       "original_header": item.original, "source_position": pos, "occurrence": item.occurrence})
    columns, used = [], set()
    for template in SHEETS[order]["columns"]:
        label, position = template["label"], template["position"]
        field = canonical(label) if label else f"blank:{order}:{position}"
        found = next((item for item in source if item["field"] == field and item["occurrence"] == batch.selected_occurrences.get(item["normalized"], 1)), None)
        if found and found["original_header"] == label: used.add(found["source_position"])
        value_type = kind(field)
        source_format = template["source_number_format"]
        columns.append(Column(field, label, source_field=found["normalized"] if found else field,
                              raw_key=found["raw_key"] if found else "", original_header=found["original_header"] if found else "",
                              source_position=found["source_position"] if found else None, occurrence=found["occurrence"] if found else None,
                              working=bool(label), editable=bool(label), protected=field in PROTECTED_FIELDS,
                              type=value_type, number_format=source_format if value_type in ("money", "date", "time") and source_format != "General" else format_for(field),
                              width=max(8, round(template["width"] * 7 + 5)), hidden=template["hidden"], outline=template["outline"], letter=excel_letter(position)))
    represented = {col.field for col in columns}
    for item in source:
        if item["source_position"] in used: continue
        field = item["field"] if item["field"] not in represented and item["field"] in WORKING_FIELDS else f"source:{item['source_position']}:{item['normalized']}"
        columns.append(Column(field, item["original_header"], source_field=item["normalized"], raw_key=item["raw_key"], original_header=item["original_header"],
                              source_position=item["source_position"], occurrence=item["occurrence"], hidden=True, auxiliary=True,
                              working=field in WORKING_FIELDS, editable=field in WORKING_FIELDS, protected=field in PROTECTED_FIELDS,
                              type=kind(item["field"]), number_format=format_for(item["field"]), letter=excel_letter(len(columns) + 1)))
        represented.add(field)
    if order == "issues":
        columns.extend((Column("#", "FILA_ORIGEN", control=True, type="integer", number_format="0", width=85),
                        Column("QUALITY", "ESTADO_REVISION", control=True, width=150), Column("ORDER", "ORDEN_ORIGEN", control=True, width=130),
                        Column("ERRORS", "MOTIVOS", control=True, width=400)))
    return columns

def original_record_payload(record):
    return decrypt_json(record.data_ciphertext, associated_data=f"record:{record.batch_id}:{record.pk}:{record.source_row}")

def original_payload(row):
    return original_record_payload(row.record)

def original_fields(row):
    return original_payload(row)["fields"]

def raw_text(cell):
    value = cell.get("raw") if cell.get("raw") is not None else cell.get("value")
    return "" if value is None else str(value)

def source_values(row, columns):
    raw = original_fields(row)
    # En un libro multihoja una cabecera puede estar repetida sólo en algunas
    # hojas. La primera aparición simple no desaparece por la unión de cabeceras.
    return {col.field: raw_text(raw.get(col.raw_key, raw.get(col.source_field, {}) if col.occurrence == 1 else {}))
            for col in columns if col.raw_key}

def cell_value(payload, column):
    if column.field == "#": return payload.get("source_excel_row", payload["source_row"])
    if column.field == "QUALITY": return payload.get("presentation_quality", payload["quality"])
    if column.field == "ORDER": return payload.get("order", "")
    if column.field == "ERRORS": return "; ".join(e["message"] for e in payload["errors"])
    stored = payload.get("stored_fields", payload["values"])
    if column.working and column.field in stored: return payload["values"].get(column.field, "")
    return payload.get("source_values", {}).get(column.field, "")

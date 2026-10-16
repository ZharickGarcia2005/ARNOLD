"""Excel descargable de la revisión actual con origen y versión verificables."""

from copy import copy
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from hashlib import sha256
from tempfile import SpooledTemporaryFile

from django.db import transaction
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from apps.audit.services import append_audit_event
from apps.batches.crypto import decrypt_json
from apps.validation.exporters import safe_excel_value
from apps.validation.rules import make_unique_headers
from apps.validation.services import _headers_aad, _record_aad

from .models import Worksheet
from .worksheet import FIELDS, MONEY, SheetError, filter_rows, row_payload
from .presentation import effective_style, read_document


@dataclass(frozen=True)
class ExportColumn:
    label: str
    field: str
    raw_key: str = ""
    working: bool = True


def export_columns(batch):
    """Orden y rótulos originales; solo la ocurrencia validada recibe ediciones."""
    headers = decrypt_json(batch.headers_ciphertext, associated_data=_headers_aad(batch.id)) if batch.headers_ciphertext else batch.original_headers
    if not headers:
        return [ExportColumn(field, field) for field in FIELDS]
    occurrences = make_unique_headers(headers, batch.schema_name)
    counts = Counter(item.normalized for item in occurrences)
    columns, represented = [], set()
    for item in occurrences:
        field = item.normalized
        selected = batch.selected_occurrences.get(field, 1)
        working = field in FIELDS and item.occurrence == selected
        raw_key = f"{field}__{item.occurrence}" if counts[field] > 1 else field
        columns.append(ExportColumn(item.original, field, raw_key, working))
        if working:
            represented.add(field)
    columns.extend(ExportColumn(field, field) for field in FIELDS if field not in represented)
    return columns


def typed_value(field, value):
    if value not in (None, ""):
        if field in MONEY:
            try:
                decimal = Decimal(str(value))
                if decimal.is_finite() and abs(decimal) <= Decimal("999999999999.99"):
                    value = decimal
            except ArithmeticError:
                pass
        elif field == "MESES_DEUDA":
            try:
                months = Decimal(str(value))
                if months.is_finite() and 0 <= months <= 999999 and months == months.to_integral_value():
                    value = int(months)
            except ArithmeticError:
                pass
        elif field == "FECHA_VENCIMIENTO" and isinstance(value, str):
            try:
                value = date.fromisoformat(value)
            except ValueError:
                pass
    return value if isinstance(value, date) else safe_excel_value(value)


@transaction.atomic
def export_sheet(batch, actor, scope, search="", expected_revision=None):
    if scope not in ("clean", "problem"):
        raise SheetError("invalid_scope", "Seleccione el lote principal o las filas con problemas.")
    sheet = Worksheet.objects.select_for_update().get(batch=batch)
    presentation = read_document(sheet, actor)
    if expected_revision != sheet.revision:
        raise SheetError("version_conflict", "La hoja cambió. Actualice antes de descargar.", 409)
    query = filter_rows(sheet, scope, search)
    count = query.count()
    if count == 0:
        raise SheetError("empty_export", "No hay registros en este conjunto. No se generó un Excel vacío.", 422)
    if count > 100000:
        raise SheetError("export_limit", "Divida el lote antes de exportar más de 100.000 filas.")
    workbook = Workbook(write_only=True)
    data = workbook.create_sheet("Principal" if scope == "clean" else "Problemas")
    data.freeze_panes = "E2"
    columns = export_columns(batch)
    headers = [*(column.label for column in columns), "MONTO_PENDIENTE", "FILA_ORIGEN", "ESTADO_REVISION", "MOTIVOS"]
    visual_fields = [*(column.field if column.working else "" for column in columns), "TOTAL", "#", "QUALITY", "ERRORS"]
    header_cells = []
    for position, field in enumerate(headers, 1):
        data.column_dimensions[get_column_letter(position)].width = 80 if field == "MOTIVOS" else 38 if field in ("NOMBRES", "DIRECCION", "CORREO") else 20
        width = presentation["columns"].get(visual_fields[position - 1], {}).get("width")
        if width:
            data.column_dimensions[get_column_letter(position)].width = round((width - 5) / 7, 2)
        cell = WriteOnlyCell(data, safe_excel_value(field))
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="0D8880")
        header_cells.append(cell)
    data.append(header_cells)
    written = 0
    needs_raw = any(not column.working for column in columns)
    for excel_row, row in enumerate(query.iterator(chunk_size=500), 2):
        height = presentation["heights"].get(str(row.pk))
        if height:
            data.row_dimensions[excel_row].height = height * .75
        payload = row_payload(row)
        values = payload["values"]
        raw = decrypt_json(row.record.data_ciphertext, associated_data=_record_aad(batch.id, row.record_id, row.record.source_row))["fields"] if needs_raw else {}
        output = []
        for column in columns:
            original = raw.get(column.raw_key, {})
            value = values.get(column.field, "") if column.working else original.get("value")
            if not column.working and value is None:
                value = original.get("raw")
            if not column.working and column.field in ("CIU", "CEDULA_RUC", "CLAVE", "TELEF"):
                value = original.get("raw") if original.get("raw") is not None else str(value or "")
            output.append(typed_value(column.field, value))
        total = Decimal(payload["total"]) if payload["total"] is not None else None
        if total is not None and abs(total) > Decimal("999999999999999.99"):
            total = str(total)
        output += [total,
                   payload["source_row"], row.quality,
                   safe_excel_value("; ".join(error["message"] for error in payload["errors"]))]
        cells = []
        for position, value in enumerate(output):
            cell = WriteOnlyCell(data, value)
            field = columns[position].field if position < len(columns) else ""
            if field in MONEY or position == len(columns):
                cell.number_format = "#,##0.00"
            elif field in ("CIU", "CEDULA_RUC", "CLAVE", "TELEF"):
                cell.number_format = "@"
            visual = effective_style(presentation, row.pk, visual_fields[position])
            if visual.get("background"):
                cell.fill = PatternFill("solid", fgColor=visual["background"][1:])
            if any(key in visual for key in ("color", "bold", "italic", "underline", "size")):
                font = copy(cell.font)
                for key in ("bold", "italic"):
                    if key in visual:
                        setattr(font, key, visual[key])
                if "underline" in visual:
                    font.underline = "single" if visual["underline"] else None
                if visual.get("color"):
                    font.color = visual["color"][1:]
                if visual.get("size"):
                    font.sz = visual["size"] * .75
                cell.font = font
            if visual.get("align") or "wrap" in visual:
                alignment = copy(cell.alignment)
                if visual.get("align"):
                    alignment.horizontal = visual["align"]
                if "wrap" in visual:
                    alignment.wrap_text = visual["wrap"]
                cell.alignment = alignment
            cells.append(cell)
        data.append(cells)
        written += 1
    if written != count:
        workbook.close()
        raise SheetError("incomplete_export", "La cantidad de filas cambió durante la exportación. Actualice y reintente.", 409)
    data.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{count + 1}"
    meta = workbook.create_sheet("Trazabilidad")
    meta.column_dimensions["A"].width = 25
    meta.column_dimensions["B"].width = 105
    for item in (
        ("Clasificación", "CONFIDENCIAL"), ("Lote", str(batch.id)),
        ("Periodo", str(batch.period)), ("SHA256 original", batch.sha256),
        ("Hoja original", batch.sheet_name), ("Revisión", sheet.revision),
        ("Conjunto", scope), ("Filas", count), ("Usuario", actor.username),
        ("Generado", timezone.now().isoformat()),
        ("Aprobación", "Exportación preliminar. No certifica pago, cancelación ni aprobación del lote."),
        ("Identificación", "Cédula: formato y verificador. RUC: estructura; sin consulta oficial."),
        ("Búsqueda aplicada", "Sí" if search else "No"),
        ("Columnas", "Encabezados originales, campos de trabajo adicionales y trazabilidad al final."),
        ("Formato personal", f"Usuario {actor.username}. Versión {presentation['version']}"),
    ):
        meta.append([safe_excel_value(value) for value in item])
    stream = SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
    try:
        workbook.save(stream)
        stream.seek(0)
        stream.arnold_export_rows = count
        stream.arnold_export_revision = sheet.revision
        digest = sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
        stream.seek(0)
        append_audit_event(actor=actor, action="worksheet.exported", object_type="Batch", object_id=batch.id,
                           metadata={"scope": scope, "rows": count, "revision": sheet.revision, "sha256": digest.hexdigest()})
        return stream, f"ARNOLD_{scope}_{batch.period}_r{sheet.revision}.xlsx"
    except Exception:
        stream.close()
        raise
    finally:
        workbook.close()

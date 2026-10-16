"""Hoja revisable cifrada. La evidencia RAW y el resultado original no se editan."""

from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
import re

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.audit.services import append_audit_event
from apps.batches.crypto import blind_index, decrypt_json, encrypt_json
from apps.batches.models import Batch
from apps.validation.models import ValidationRun
from apps.validation.services import _load_record

from .models import ChangeRequest, Worksheet, WorksheetEdit, WorksheetRow


FIELDS = (
    "CIU", "CEDULA_RUC", "NOMBRES", "CLAVE", "DIRECCION", "PARROQUIA", "TELEF", "CORREO",
    "TOTAL_EMISION", "TOTAL_INTERES", "TOTAL_COACTIVA", "TOTAL_RECARGO", "MESES_DEUDA",
    "FECHA_VENCIMIENTO",
)
MONEY = FIELDS[8:12]
PROTECTED = frozenset(("CIU", "CEDULA_RUC", "CLAVE", *MONEY, "MESES_DEUDA"))
VALIDATOR_VERSION = "worksheet-2026.10.15.2"


class SheetError(ValueError):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status


def index(value):
    return blind_index(str(value).strip().upper()) if str(value).strip() else ""


def aad(row):
    return f"worksheet:{row.worksheet_id}:{row.record_id}"


def values_of(row):
    return decrypt_json(row.data_ciphertext, associated_data=aad(row))


def valid_cedula(value):
    if not re.fullmatch(r"\d{10}", value) or len(set(value)) == 1:
        return False
    if not (1 <= int(value[:2]) <= 24 or value[:2] == "30") or int(value[2]) > 5:
        return False
    total = 0
    for position, digit in enumerate(value[:9]):
        number = int(digit) * (2 if position % 2 == 0 else 1)
        total += number - 9 if number > 9 else number
    return (10 - total % 10) % 10 == int(value[-1])


def check_values(values):
    """Controles locales; RUC es estructural, no consulta de registro oficial."""
    errors = []
    for field in ("NOMBRES", "CLAVE", "CIU", "CEDULA_RUC"):
        if not values.get(field, "").strip():
            errors.append({"field": field, "code": "REQUIRED", "message": f"Falta {field}."})
    identity = values.get("CEDULA_RUC", "")
    if identity:
        valid = valid_cedula(identity) if len(identity) == 10 else (
            bool(re.fullmatch(r"\d{13}", identity)) and len(set(identity)) > 1
            and 1 <= int(identity[:2]) <= 24 and identity[-3:] != "000"
            and (valid_cedula(identity[:10]) if int(identity[2]) < 6 else int(identity[2]) in (6, 9))
        )
        if not valid:
            errors.append({"field": "CEDULA_RUC", "code": "IDENTITY", "message": "Identificación inválida: revise cédula (10 dígitos y verificador) o estructura RUC (13 dígitos)."})
    for field in MONEY:
        try:
            amount = Decimal(values.get(field, ""))
            if not amount.is_finite() or amount < 0 or amount != amount.quantize(Decimal("0.01")) or amount > Decimal("999999999999.99"):
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            errors.append({"field": field, "code": "MONEY", "message": f"{field} debe ser no negativo, con máximo 2 decimales."})
    months = values.get("MESES_DEUDA", "")
    if not re.fullmatch(r"\d{1,6}(?:\.0+)?", months):
        errors.append({"field": "MESES_DEUDA", "code": "MONTHS", "message": "MESES_DEUDA debe ser un entero no negativo."})
    email = values.get("CORREO", "")
    if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        errors.append({"field": "CORREO", "code": "EMAIL", "message": "Formato de correo inválido."})
    due = values.get("FECHA_VENCIMIENTO", "")
    if due:
        try:
            date.fromisoformat(due)
        except ValueError:
            errors.append({"field": "FECHA_VENCIMIENTO", "code": "DATE", "message": "Fecha de vencimiento inválida. Use AAAA-MM-DD."})
    for field, value in values.items():
        if field == "TELEF" and re.fullmatch(r"\+?[\d\s()\-]+", value):
            continue
        if value.lstrip().startswith(("=", "+", "@")):
            errors.append({"field": field, "code": "FORMULA", "message": f"{field} contiene una fórmula o contenido no admitido."})
    return errors


@transaction.atomic
def revalidate_worksheet(sheet):
    sheet = Worksheet.objects.select_for_update().get(pk=sheet.pk)
    buffer = []
    for row in sheet.rows.iterator(chunk_size=500):
        row.errors = check_values(values_of(row)) + row.source_errors
        buffer.append(row)
        if len(buffer) == 500:
            WorksheetRow.objects.bulk_update(buffer, ("errors",))
            buffer.clear()
    if buffer:
        WorksheetRow.objects.bulk_update(buffer, ("errors",))
    refresh_duplicates(sheet)
    sheet.revision += 1
    sheet.save(update_fields=("revision", "updated_at"))
    return sheet


def refresh_duplicates(sheet, keys=None):
    query = sheet.rows.all()
    if keys is not None:
        query = query.filter(clave_hmac__in=keys)
    duplicates = query.exclude(clave_hmac="").values("clave_hmac").annotate(n=Count("record_id")).filter(n__gt=1)
    duplicate_keys = list(duplicates.values_list("clave_hmac", flat=True))
    query.update(duplicate=False)
    query.filter(clave_hmac__in=duplicate_keys).update(duplicate=True)
    query.update(quality="problem")
    query.filter(duplicate=False, errors=[]).update(quality="clean")


@transaction.atomic
def prepare_worksheet(batch):
    Batch.objects.select_for_update().get(id=batch.id)
    existing = Worksheet.objects.filter(batch=batch).first()
    if existing:
        return existing
    run = batch.validation_runs.order_by("-created_at").first()
    if not run or run.status != ValidationRun.Status.SUCCEEDED:
        raise SheetError("not_validated", "La validación del archivo todavía no ha terminado.", 409)
    sheet = Worksheet.objects.create(batch=batch)
    engine_errors = {}
    for issue in run.issues.filter(requires_review=True).exclude(rule_code__in=("KEY-001", "CAT-001")):
        engine_errors.setdefault(str(issue.record_id) if issue.record_id else "batch", []).append({
            "field": issue.field_name, "code": issue.rule_code,
            "message": issue.message,
        })
    buffer = []
    for record in batch.records.order_by("source_row").iterator(chunk_size=500):
        item = _load_record(record, str(batch.id))
        values = {}
        for field in FIELDS:
            cell = item.cell(field)
            value = cell.raw if cell.raw is not None else cell.value
            values[field] = str(value).strip() if value is not None else ""
        source_errors = engine_errors.get(str(record.id), []) + engine_errors.get("batch", [])
        row = WorksheetRow(record=record, worksheet=sheet, clave_hmac=index(values["CLAVE"]),
                           identifier_hmac=index(values["CEDULA_RUC"]), ciu_hmac=index(values["CIU"]),
                           source_errors=source_errors, errors=check_values(values) + source_errors)
        row.data_ciphertext = encrypt_json(values, associated_data=aad(row))
        buffer.append(row)
        if len(buffer) == 500:
            WorksheetRow.objects.bulk_create(buffer)
            buffer.clear()
    if buffer:
        WorksheetRow.objects.bulk_create(buffer)
    refresh_duplicates(sheet)
    append_audit_event(actor=batch.uploaded_by, action="worksheet.prepared", object_type="Batch", object_id=batch.id,
                       metadata={"validator_version": VALIDATOR_VERSION, "rows": batch.row_count})
    return sheet


def row_payload(row, include_values=True):
    problems = list(row.errors)
    if row.duplicate:
        problems.append({"field": "CLAVE", "code": "DUPLICATE_KEY", "message": "La CLAVE aparece en más de una fila; se separaron todas sus apariciones."})
    result = {"id": str(row.record_id), "source_row": row.record.source_row,
              "version": row.version, "quality": row.quality, "errors": problems}
    if include_values:
        values = values_of(row)
        amounts = []
        for field in MONEY:
            try:
                value = Decimal(values[field])
                if not value.is_finite() or abs(value) > Decimal("999999999999.99"):
                    raise InvalidOperation
                amounts.append(value)
            except (InvalidOperation, ValueError):
                amounts = []
                break
        result.update(values=values, total=str(sum(amounts)) if amounts else None)
    return result


def summary(sheet):
    counts = Counter(dict(sheet.rows.values("quality").annotate(n=Count("record_id")).values_list("quality", "n")))
    return {"revision": sheet.revision, "total": sum(counts.values()), "clean": counts["clean"],
            "problem": counts["problem"], "duplicates": sheet.rows.filter(duplicate=True).count(),
            "pending_approvals": ChangeRequest.objects.filter(record__batch_id=sheet.pk, status="pending").count(),
            "validator_version": VALIDATOR_VERSION}


def filter_rows(sheet, scope="clean", search=""):
    query = sheet.rows.select_related("record").order_by("record__source_row")
    if scope not in ("clean", "problem", "all"):
        raise SheetError("invalid_scope", "El conjunto solicitado no existe.")
    if scope != "all":
        query = query.filter(quality=scope)
    if search:
        query = query.filter(Q(clave_hmac=index(search)) | Q(identifier_hmac=index(search)) | Q(ciu_hmac=index(search)))
    return query


def can_edit(user):
    return user.has_perm("batches.change_record") and (user.is_superuser or user.role in ("validator", "supervisor", "admin"))


def can_direct_protected(user):
    return user.is_superuser or (user.role in ("supervisor", "admin") and user.has_perm("workflow.decide_change_request"))


def normalized_updates(updates):
    if not isinstance(updates, dict) or not updates or set(updates) - set(FIELDS):
        raise SheetError("invalid_fields", "La modificación contiene campos no editables.")
    result = {}
    for field, value in updates.items():
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            raise SheetError("invalid_value", "Cada celda debe contener texto o un número.")
        value = str(value).strip()
        if len(value) > 1000 or any(ord(char) < 32 and char not in "\t\n\r" for char in value):
            raise SheetError("invalid_value", "El contenido de la celda excede los límites permitidos.")
        result[field] = value
    return result


def apply_row(row, updates, actor, reason):
    old = values_of(row)
    new = {**old, **updates}
    log = WorksheetEdit(row=row, actor=actor, version=row.version + 1)
    log.detail_ciphertext = encrypt_json({"old": old, "new": new, "reason": reason, "fields": list(updates)}, associated_data=f"worksheet-edit:{log.id}")
    log.save()
    row.data_ciphertext = encrypt_json(new, associated_data=aad(row))
    row.clave_hmac, row.identifier_hmac, row.ciu_hmac = index(new["CLAVE"]), index(new["CEDULA_RUC"]), index(new["CIU"])
    row.errors = check_values(new) + row.source_errors
    row.version += 1
    row.updated_by = actor
    row.save()


@transaction.atomic
def save_changes(batch, actor, changes, reason):
    if not can_edit(actor):
        raise SheetError("permission_denied", "Su usuario no puede editar esta hoja.", 403)
    if not isinstance(reason, str) or not 3 <= len(reason.strip()) <= 500:
        raise SheetError("reason_required", "Escriba un motivo de entre 3 y 500 caracteres.")
    if not isinstance(changes, list) or not 1 <= len(changes) <= 100:
        raise SheetError("invalid_changes", "Guarde entre 1 y 100 filas a la vez.")
    batch = Batch.objects.select_for_update().get(pk=batch.pk)
    sheet = Worksheet.objects.select_for_update().get(batch=batch)
    if batch.status in (Batch.Status.APPROVED, Batch.Status.EXPORTED, Batch.Status.REJECTED):
        raise SheetError("batch_closed", "El lote está cerrado y no admite cambios.", 409)
    checked, keys, seen = [], set(), set()
    for change in changes:
        if not isinstance(change, dict):
            raise SheetError("invalid_changes", "La modificación no es válida.")
        row = sheet.rows.select_related("record").filter(record_id=change.get("id")).first()
        if row is None or str(row.pk) in seen:
            raise SheetError("invalid_row", "La fila no pertenece al lote o está repetida.")
        if row.version != change.get("version"):
            raise SheetError("version_conflict", "Otro usuario modificó una fila. Actualice la hoja antes de guardar.", 409)
        updates = normalized_updates(change.get("values"))
        seen.add(str(row.pk))
        checked.append((row, updates))
    applied, pending = [], []
    for row, updates in checked:
        if PROTECTED.intersection(updates) and not can_direct_protected(actor):
            existing = ChangeRequest.objects.filter(
                record=row.record, field_name="__worksheet__", expected_version=row.version,
                requested_by=actor, status="pending",
            )
            identical = next((item for item in existing if decrypt_json(
                item.new_value_ciphertext, associated_data=f"sheet-change-new:{row.pk}"
            ) == updates), None)
            if identical:
                pending.append(identical.pk)
                continue
            request = ChangeRequest.objects.create(
                record=row.record, field_name="__worksheet__", expected_version=row.version,
                old_value_ciphertext=encrypt_json(values_of(row), associated_data=f"sheet-change-old:{row.pk}"),
                new_value_ciphertext=encrypt_json(updates, associated_data=f"sheet-change-new:{row.pk}"),
                reason=reason.strip(), requested_by=actor,
            )
            pending.append(request.pk)
        else:
            keys.add(row.clave_hmac)
            apply_row(row, updates, actor, reason.strip())
            keys.add(row.clave_hmac)
            applied.append(str(row.pk))
    if applied:
        refresh_duplicates(sheet, keys)
        sheet.revision += 1
        sheet.save(update_fields=("revision", "updated_at"))
    append_audit_event(actor=actor, action="worksheet.saved" if applied else "worksheet.approval_requested",
                       object_type="Batch", object_id=batch.id,
                       metadata={"revision": sheet.revision, "rows": applied, "requests": pending})
    return {"applied": applied, "pending": pending, "summary": summary(sheet)}


@transaction.atomic
def decide_change(batch, actor, request_id, approve):
    if not can_direct_protected(actor):
        raise SheetError("permission_denied", "No tiene permiso para decidir cambios.", 403)
    batch = Batch.objects.select_for_update().get(pk=batch.pk)
    sheet = Worksheet.objects.select_for_update().get(batch=batch)
    if batch.status in (Batch.Status.APPROVED, Batch.Status.EXPORTED, Batch.Status.REJECTED):
        raise SheetError("batch_closed", "El lote está cerrado.", 409)
    request = ChangeRequest.objects.select_for_update().filter(pk=request_id, record__batch=batch, field_name="__worksheet__").first()
    if not request or request.status != "pending":
        raise SheetError("invalid_request", "La solicitud ya se resolvió o no pertenece al lote.", 409)
    if request.requested_by_id == actor.pk:
        raise SheetError("double_control", "El solicitante no puede decidir su propio cambio.", 403)
    row = sheet.rows.select_related("record").get(pk=request.record_id)
    if approve:
        if row.version != request.expected_version:
            raise SheetError("version_conflict", "La fila cambió desde la solicitud. Rechácela y solicite una nueva.", 409)
        updates = decrypt_json(request.new_value_ciphertext, associated_data=f"sheet-change-new:{row.pk}")
        keys = {row.clave_hmac}
        apply_row(row, normalized_updates(updates), actor, request.reason)
        refresh_duplicates(sheet, keys | {row.clave_hmac})
        sheet.revision += 1
        sheet.save(update_fields=("revision", "updated_at"))
    request.status = "approved" if approve else "rejected"
    request.decided_by, request.decided_at = actor, timezone.now()
    request.save()
    append_audit_event(actor=actor, action=f"worksheet.change_{request.status}", object_type="ChangeRequest", object_id=request.pk,
                       metadata={"batch_id": str(batch.pk), "record_id": str(row.pk), "revision": sheet.revision})
    return {"status": request.status, "summary": summary(sheet)}

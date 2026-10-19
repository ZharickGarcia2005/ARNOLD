import json
from functools import wraps

from django.core.exceptions import ValidationError
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from apps.batches.crypto import CryptoConfigurationError, DecryptionError, decrypt_json
from apps.batches.views import _read_denied, _visible_batches

from .models import ChangeRequest, Worksheet, WorksheetEdit
from .sheet_exports import export_sheet
from .columns import CONTRACT_VERSION, SHEETS, cell_value, columns_for, source_values
from .order_projection import decorate, routes, selected_ids, presentation_counts
from .presentation import page_presentation, save_presentation
from .worksheet import FIELDS, SheetError, can_direct_protected, can_edit, decide_change, filter_rows, row_payload, save_changes, summary


def sheet_api(function):
    @wraps(function)
    def wrapper(request, batch_id, *args, **kwargs):
        denied = _read_denied(request)
        if denied:
            return denied
        batch = get_object_or_404(_visible_batches(request), id=batch_id)
        try:
            sheet = Worksheet.objects.filter(batch=batch).first()
            if sheet is None:
                raise SheetError("preparing", "La hoja se está preparando. Su archivo permanece guardado.", 409)
            result = function(request, batch, sheet, *args, **kwargs)
        except SheetError as exc:
            result = JsonResponse({"error": {"code": exc.code, "message": str(exc)}}, status=exc.status)
        except (CryptoConfigurationError, DecryptionError):
            result = JsonResponse({"error": {"code": "data_unavailable", "message": "No se pudo autenticar la información cifrada."}}, status=503)
        except OSError:
            result = JsonResponse({"error": {"code": "presentation_unavailable", "message": "No se pudo acceder al almacenamiento privado de presentación. Sus datos financieros no se modificaron."}}, status=503)
        except (ValueError, TypeError, ValidationError, json.JSONDecodeError):
            result = JsonResponse({"error": {"code": "invalid_input", "message": "La solicitud contiene datos inválidos."}}, status=400)
        result["Cache-Control"] = "no-store"
        return result
    return wrapper


def body(request):
    if len(request.body) > 250000:
        raise SheetError("request_limit", "La modificación supera el tamaño permitido.", 413)
    data = json.loads(request.body or b"{}")
    if not isinstance(data, dict):
        raise SheetError("invalid_input", "La solicitud debe ser un objeto.")
    return data


def sheet_data(request, batch, sheet, data):
    page = max(1, int(data.get("page", 1)))
    scope, search = data.get("scope", "clean"), str(data.get("search", "")).strip()[:120]
    if scope not in ("clean", "problem"): raise SheetError("invalid_scope", "Seleccione principal o inconsistencias.")
    order = data.get("order", "issues" if scope == "problem" else "030")
    if order not in SHEETS: raise SheetError("invalid_order", "La pestaña no existe.")
    scope = "problem" if order == "issues" else "clean"
    ids = selected_ids(sheet, scope, search, order)
    count = len(ids)
    page = min(page, max(1, (count + 99) // 100))
    columns = columns_for(batch, order)
    query = sheet.rows.select_related("record").filter(pk__in=ids[(page - 1) * 100:page * 100]).order_by("record__source_row")
    rows = []
    mapping = routes(sheet)
    for row in query:
        payload = decorate({**row_payload(row), "source_values": source_values(row, columns)}, mapping[str(row.pk)])
        payload["values"].update({col.field: cell_value(payload, col) for col in columns if col.working})
        payload["missing_fields"] = [col.label for col in columns if col.working and not payload["values"].get(col.field)]
        payload["presentation_observations"] = [{"field": col.field, "code": "MISSING_PRESENTATION_VALUE", "severity": "warning",
                                                  "message": f"{col.label}: sin dato de origen o vacío guardado; no se completó automáticamente."}
                                                 for col in columns if col.working and not payload["values"].get(col.field)]
        rows.append(payload)
    counts = presentation_counts(sheet)
    totals = summary(sheet)
    totals.update(clean=totals["total"] - counts["issues"], problem=counts["issues"])
    original_run = batch.validation_runs.order_by("-created_at").first()
    return JsonResponse({
        "batch_id": str(batch.id), "name": batch.display_name, "status": batch.status,
        "summary": totals, "validation_summary": summary(sheet), "page": page, "page_size": 100, "filtered_total": count,
        "order": order, "tabs": [{"id": code, "name": definition["name"], "count": counts[code]} for code, definition in SHEETS.items()],
        "appearance": {key: SHEETS[order][key] for key in ("header_fill", "stripe_fill", "border_color")},
        "unassigned_count": sum(bool(error) for code, error in mapping.values()),
        "has_next": page * 100 < count, "rows": rows, "fields": [col.field for col in columns if col.editable],
        "columns": [col.payload(i) for i, col in enumerate(columns)], "column_contract": CONTRACT_VERSION,
        "compatibility_notice": "Lote histórico conservado. La distribución por órdenes es una vista: no se revalidaron ni modificaron sus registros originales." if any(row["identifier_validation"] != "executed" for row in rows) else "",
        "presentation": page_presentation(sheet, request.user, [row["id"] for row in rows]),
        "capabilities": {"edit": can_edit(request.user) and batch.status not in ("approved", "exported", "rejected"), "protected": can_direct_protected(request.user),
                         "export": request.user.has_perm("batches.export_batch"),
                         "format": can_edit(request.user) and batch.status not in ("approved", "exported", "rejected")},
        "skipped_rules": original_run.skipped_rules if original_run else {},
    })


@require_GET
@sheet_api
def detail(request, batch, sheet):
    return sheet_data(request, batch, sheet, request.GET)


@require_POST
@sheet_api
def query(request, batch, sheet):
    return sheet_data(request, batch, sheet, body(request))


@require_POST
@sheet_api
def save(request, batch, sheet):
    data = body(request)
    return JsonResponse(save_changes(batch, request.user, data.get("changes"), data.get("reason")))


@require_POST
@sheet_api
def presentation(request, batch, sheet):
    data = body(request)
    if "operations" in data:
        version = save_presentation(sheet, request.user, data.get("version"), data["operations"])
        return JsonResponse({"version": version})
    ids = data.get("rows", [])
    if not isinstance(ids, list) or len(ids) > 100:
        raise SheetError("row_limit", "Consulte hasta 100 filas por página.")
    visible_ids = sheet.rows.filter(pk__in=ids).values_list("pk", flat=True)
    return JsonResponse({"presentation": page_presentation(sheet, request.user, visible_ids)})


@require_POST
@sheet_api
def download(request, batch, sheet):
    if not request.user.has_perm("batches.export_batch"):
        raise SheetError("permission_denied", "No tiene permiso para descargar lotes.", 403)
    data = body(request)
    stream, filename = export_sheet(batch, request.user, data.get("scope"), expected_revision=data.get("revision"))
    response = FileResponse(stream, as_attachment=True, filename=filename,
                            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["X-ARNOLD-Export-Rows"] = str(stream.arnold_export_rows)
    response["X-ARNOLD-Export-Revision"] = str(stream.arnold_export_revision)
    response["X-ARNOLD-Export-Batch"] = str(batch.pk)
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_GET
@sheet_api
def requests(request, batch, sheet):
    query = ChangeRequest.objects.filter(record__batch=batch, field_name="__worksheet__").select_related("requested_by", "record").order_by("-requested_at")
    if not can_direct_protected(request.user):
        query = query.filter(requested_by=request.user)
    results = []
    for change in query[:100]:
        values = decrypt_json(change.new_value_ciphertext, associated_data=f"sheet-change-new:{change.record_id}")
        old = decrypt_json(change.old_value_ciphertext, associated_data=f"sheet-change-old:{change.record_id}")
        results.append({"id": change.pk, "source_row": change.record.source_row,
                        "requester": change.requested_by.username, "status": change.status,
                        "values": values, "old": {field: old.get(field) for field in values},
                        "reason": change.reason, "can_decide": can_direct_protected(request.user) and change.requested_by_id != request.user.pk and change.status == "pending"})
    return JsonResponse({"requests": results})


@require_POST
@sheet_api
def decide(request, batch, sheet, request_id):
    data = body(request)
    if not isinstance(data.get("approve"), bool):
        raise SheetError("invalid_decision", "Indique aprobar o rechazar.")
    return JsonResponse(decide_change(batch, request.user, request_id, data["approve"]))


@require_GET
@sheet_api
def history(request, batch, sheet):
    edits = WorksheetEdit.objects.filter(row__worksheet=sheet).select_related("actor", "row__record").order_by("-created_at")[:100]
    rows = []
    for edit in edits:
        detail = decrypt_json(edit.detail_ciphertext, associated_data=f"worksheet-edit:{edit.id}")
        rows.append({"id": str(edit.id), "source_row": edit.row.record.source_row, "user": edit.actor.username,
                     "date": edit.created_at.isoformat(), "version": edit.version, "reason": detail["reason"],
                     "changes": [{"field": field, "old": detail["old"].get(field), "new": detail["new"].get(field)} for field in detail["fields"]]})
    return JsonResponse({"edits": rows})

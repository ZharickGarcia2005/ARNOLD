"""API mínima de lotes; la autorización siempre se decide en el servidor."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import uuid

from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.validation.models import ValidationRun, ValidationIssue
from apps.validation.services import _load_record
from apps.batches.crypto import CryptoConfigurationError, DecryptionError
from apps.validation.rules import SCHEMAS, SOURCE_PROFILES

from .models import Batch, Record
from .services import DuplicateUploadError, UploadError, receive_xlsx, requeue_failed_batch


def _error(code: str, message: str, status: int) -> JsonResponse:
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


def _user_area(request) -> str:
    return str(getattr(request.user, "area", "")).strip()


def _read_denied(request):
    if not request.user.is_authenticated:
        return _error("authentication_required", "Debe iniciar sesión.", 401)
    if not (request.user.has_perm("batches.view_batch") or request.user.has_perm("batches.import_batch")):
        return _error("permission_denied", "No tiene permiso para consultar lotes.", 403)
    if not request.user.is_superuser and not _user_area(request):
        return _error("area_required", "El usuario debe pertenecer a un área.", 403)
    return None


def _visible_batches(request):
    query = Batch.objects.all()
    return query if request.user.is_superuser else query.filter(owner_area=_user_area(request))


@require_GET
def batch_list(request):
    denied = _read_denied(request)
    if denied:
        return denied
    response = JsonResponse({"batches": [
        {"id": str(batch.id), "name": batch.display_name, "status": batch.status,
         "status_label": batch.get_status_display(), "row_count": batch.row_count,
         "period": batch.period.isoformat() if batch.period else None,
         "status_url": reverse("batches:status", args=(batch.id,)),
         "records_url": reverse("batches:records", args=(batch.id,))}
        for batch in _visible_batches(request).order_by("-created_at")[:50]
    ]})
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def batch_records(request, batch_id):
    denied = _read_denied(request)
    if denied:
        return denied
    batch = get_object_or_404(_visible_batches(request), id=batch_id)
    try:
        page = max(1, int(request.GET.get("page", "1")))
    except ValueError:
        return _error("invalid_page", "Página inválida.", 400)
    run = batch.validation_runs.order_by("-created_at").first()
    completed = run is not None and run.status == ValidationRun.Status.SUCCEEDED
    rows = []
    query = batch.records.order_by("source_row") if completed else Record.objects.none()
    total = query.count()
    try:
        for stored in query[(page - 1) * 50:page * 50]:
            item = _load_record(stored, str(batch.id))
            components = [item.decimal(name) for name in (
                "TOTAL_EMISION", "TOTAL_INTERES", "TOTAL_COACTIVA", "TOTAL_RECARGO"
            )]
            amount = str(sum(components, Decimal(0))) if all(value is not None for value in components) else None
            rows.append({"id": str(stored.id), "source_row": stored.source_row,
                         "status": stored.status, "clave": item.text("CLAVE"),
                         "ciu": item.text("CIU"), "identity": item.text("CEDULA_RUC"),
                         "name": item.text("NOMBRES"), "amount": amount})
    except (CryptoConfigurationError, DecryptionError):
        return _error("data_unavailable", "No se pudo autenticar la información del lote.", 503)
    issues = run.issues if completed else ValidationIssue.objects.none()
    counts = dict(query.values("status").annotate(count=Count("id")).values_list("status", "count"))
    response = JsonResponse({
        "batch_id": str(batch.id), "name": batch.display_name, "status": batch.status,
        "total": total, "page": page, "page_size": 50, "has_next": page * 50 < total,
        "counts": counts, "records": rows,
        "issue_count": issues.count(), "critical_count": issues.filter(severity="critical").count(),
        "duplicate_count": issues.filter(rule_code__in=("KEY-001", "DUP-001", "CAT-001")).count(),
        "issues": list(issues.order_by("id").values("rule_code", "severity", "message", "blocking")[:50]),
        "skipped_rules": run.skipped_rules if completed else {},
    })
    response["Cache-Control"] = "no-store"
    return response


def _authorized(request):
    if not request.user.is_authenticated:
        return _error("authentication_required", "Debe iniciar sesión.", 401)
    if not request.user.has_perm("batches.import_batch"):
        return _error("permission_denied", "No tiene permiso para cargar carteras.", 403)
    if not request.user.is_superuser and not _user_area(request):
        return _error("area_required", "El usuario debe pertenecer a un área.", 403)
    return None


def _parse_period(value: str) -> date:
    clean = value.strip()
    if len(clean) == 7:
        clean += "-01"
    result = date.fromisoformat(clean)
    if result.day != 1:
        raise ValueError
    return result


@require_POST
def upload_batch(request):
    denied = _authorized(request)
    if denied:
        return denied
    if len(request.FILES) != 1 or "file" not in request.FILES:
        return _error("single_file_required", "Debe enviar exactamente un archivo.", 400)

    try:
        period = _parse_period(request.POST.get("period", ""))
        header_row = int(request.POST.get("header_row", "1"))
        if header_row < 1 or header_row > 100:
            raise ValueError
    except (TypeError, ValueError):
        return _error("invalid_period_or_header", "Periodo o fila de encabezado inválidos.", 400)

    schema_name = request.POST.get("schema_name", "carteraMensual").strip()
    profile_id = request.POST.get("profile_id", "").strip()
    if schema_name not in SCHEMAS:
        return _error("invalid_schema", "El esquema solicitado no existe.", 400)
    if schema_name != "carteraMensual":
        return _error(
            "schema_not_enabled",
            "La primera integración admite únicamente la cartera mensual.",
            400,
        )
    if profile_id and profile_id not in SOURCE_PROFILES:
        return _error("invalid_profile", "El perfil solicitado no existe.", 400)

    reference = None
    reference_id = request.POST.get("reference_batch_id", "").strip()
    if reference_id:
        try:
            reference_uuid = uuid.UUID(reference_id)
        except ValueError:
            return _error("invalid_reference", "El lote de referencia no es válido.", 400)
        reference_query = Batch.objects.filter(id=reference_uuid)
        if not request.user.is_superuser:
            reference_query = reference_query.filter(owner_area=_user_area(request))
        reference = reference_query.first()
        reference_states = {
            Batch.Status.READY,
            Batch.Status.APPROVED,
            Batch.Status.EXPORTED,
        }
        if (
            reference is None
            or reference.period is None
            or reference.period >= period
            or reference.status not in reference_states
            or reference.schema_name != schema_name
            or not reference.records.exists()
        ):
            return _error("invalid_reference", "La referencia debe pertenecer al área y ser anterior.", 400)

    try:
        result = receive_xlsx(
            request.FILES["file"],
            uploaded_by=request.user,
            source_type="cartera_mensual",
            period=period,
            sheet_name=request.POST.get("sheet_name", ""),
            header_row=header_row,
            schema_name=schema_name,
            profile_id=profile_id,
            reference_batch=reference,
        )
    except DuplicateUploadError as exc:
        payload = {"error": {"code": exc.code, "message": str(exc)}}
        if exc.batch_id:
            payload["existing_batch_id"] = exc.batch_id
        return JsonResponse(payload, status=exc.status)
    except UploadError as exc:
        return _error(exc.code, str(exc), exc.status)

    payload = {
        "batch_id": str(result.batch.id),
        "run_id": str(result.run.id),
        "status": result.batch.status,
        "status_url": reverse("batches:status", args=(result.batch.id,)),
    }
    if result.run.error_code == "queue_unavailable":
        payload["error"] = {
            "code": result.run.error_code,
            "message": "El archivo se conservó, pero el trabajador no está disponible.",
        }
        return JsonResponse(payload, status=503)
    return JsonResponse(payload, status=202)


@require_GET
def batch_status(request, batch_id):
    if not request.user.is_authenticated:
        return _error("authentication_required", "Debe iniciar sesión.", 401)
    if not (
        request.user.has_perm("batches.view_batch")
        or request.user.has_perm("batches.import_batch")
    ):
        return _error("permission_denied", "No tiene permiso para consultar lotes.", 403)
    if not request.user.is_superuser and not _user_area(request):
        return _error("area_required", "El usuario debe pertenecer a un área.", 403)
    query = Batch.objects.all()
    if not request.user.is_superuser:
        query = query.filter(owner_area=_user_area(request))
    batch = get_object_or_404(query, id=batch_id)
    run = ValidationRun.objects.filter(current_batch=batch).order_by("-created_at").first()
    return JsonResponse(
        {
            "batch_id": str(batch.id),
            "name": batch.display_name,
            "period": batch.period.isoformat() if batch.period else None,
            "status": batch.status,
            "row_count": batch.row_count,
            "run": (
                {
                    "id": str(run.id),
                    "status": run.status,
                    "issue_count": run.issue_count,
                    "blocking_count": run.blocking_count,
                    "error_code": run.error_code,
                    "error_message": run.error_message,
                }
                if run else None
            ),
        }
    )


@require_POST
def retry_batch(request, batch_id):
    denied = _authorized(request)
    if denied:
        return denied
    query = Batch.objects.all()
    if not request.user.is_superuser:
        query = query.filter(owner_area=_user_area(request))
    batch = get_object_or_404(query, id=batch_id)
    try:
        run = requeue_failed_batch(batch, requested_by=request.user)
    except UploadError as exc:
        return _error(exc.code, str(exc), exc.status)
    status = 503 if run.error_code == "queue_unavailable" else 202
    return JsonResponse(
        {
            "batch_id": str(batch.id),
            "run_id": str(run.id),
            "status": run.status,
            "status_url": reverse("batches:status", args=(batch.id,)),
        },
        status=status,
    )

"""Recepción en cuarentena de archivos privados de ARNOLD."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import os
import shlex
import subprocess
import tempfile

from django.conf import settings
from django.db import IntegrityError, transaction

from apps.audit.services import append_audit_event
from apps.validation.contracts import ENGINE_VERSION, RuleCode
from apps.validation.digests import validation_input_digest
from apps.validation.excel_adapter import ADAPTER_VERSION, ExcelAdapterError, inspect_xlsx_archive
from apps.validation.models import ValidationRun
from apps.validation.rules import SOURCE_PROFILES
from apps.validation.tasks import validate_batch

from .models import Batch


class UploadError(ValueError):
    def __init__(self, code: str, message: str, *, status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


class DuplicateUploadError(UploadError):
    def __init__(self, batch_id: str | None = None):
        super().__init__("duplicate_file", "Este archivo ya fue recibido.", status=409)
        self.batch_id = batch_id


@dataclass(frozen=True, slots=True)
class UploadResult:
    batch: Batch
    run: ValidationRun


RETRYABLE_RUN_ERRORS = {
    "queue_unavailable",
    "temporary_processing_error",
    "unexpected_processing_error",
}


def batch_file_path(batch: Batch) -> Path:
    return Path(settings.ARNOLD_FILE_ROOT) / "quarantine" / f"{batch.storage_key}.xlsx"


def _safe_display_name(name: str) -> str:
    value = Path(name or "cartera.xlsx").name.replace("\x00", "").strip()
    return (value or "cartera.xlsx")[:255]


def _scan(path: Path) -> str:
    command = str(getattr(settings, "ARNOLD_ANTIVIRUS_COMMAND", "")).strip()
    required = bool(getattr(settings, "ARNOLD_REQUIRE_ANTIVIRUS", False))
    if not command:
        if required:
            raise UploadError("antivirus_unavailable", "El antivirus no está configurado.", status=503)
        return Batch.ScanStatus.NOT_REQUIRED
    command_parts = shlex.split(command, posix=(os.name != "nt"))
    if os.name == "nt":
        command_parts = [part.strip('"') for part in command_parts]
    try:
        completed = subprocess.run(
            [*command_parts, str(path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UploadError("antivirus_unavailable", "No se pudo completar el análisis antivirus.", status=503) from exc
    if completed.returncode != 0:
        raise UploadError("antivirus_rejected", "El archivo no superó el análisis de seguridad.")
    return Batch.ScanStatus.PASSED


def _enqueue_validation(run_id) -> None:
    """Encola sin convertir una caída de Redis en una respuesta HTTP engañosa."""

    if getattr(settings, "ARNOLD_LOCAL_QUEUE", False):
        if not settings.DEBUG:
            raise RuntimeError("La cola local solo está disponible en desarrollo.")
        # El comando process_pending recoge la ejecución confirmada en la DB.
        return
    try:
        validate_batch.delay(str(run_id))
    except Exception:
        try:
            run = ValidationRun.objects.select_related("current_batch").filter(id=run_id).first()
            if run is None:
                return
            run.status = ValidationRun.Status.FAILED
            run.error_code = "queue_unavailable"
            run.error_message = "No se pudo enviar la validación al trabajador."
            run.save(update_fields=("status", "error_code", "error_message", "updated_at"))
            run.current_batch.status = Batch.Status.FAILED
            run.current_batch.failure_code = "queue_unavailable"
            run.current_batch.failure_message = "No se pudo iniciar la validación."
            run.current_batch.save(update_fields=(
                "status", "failure_code", "failure_message", "updated_at",
            ))
        except Exception:
            # El archivo ya está confirmado en almacenamiento privado. Una
            # caída simultánea de DB y cola no debe borrarlo ni exponer datos.
            return


def receive_xlsx(
    uploaded_file,
    *,
    uploaded_by,
    source_type: str,
    period,
    sheet_name: str,
    header_row: int,
    schema_name: str,
    profile_id: str = "",
    reference_batch: Batch | None = None,
) -> UploadResult:
    """Guarda un XLSX privado, registra el lote y encola su validación."""

    display_name = _safe_display_name(getattr(uploaded_file, "name", ""))
    owner_area = str(getattr(uploaded_by, "area", "")).strip()
    is_superuser = bool(getattr(uploaded_by, "is_superuser", False))
    if not is_superuser and not owner_area:
        raise UploadError("area_required", "El usuario debe pertenecer a un área.", status=403)
    if Path(display_name).suffix.lower() != ".xlsx":
        raise UploadError("file_type", "En esta etapa solo se admiten archivos .xlsx.")
    if not sheet_name.strip():
        raise UploadError("sheet_required", "Debe indicar la hoja que se va a validar.")
    if header_row < 1 or header_row > 100:
        raise UploadError("header_row", "La fila de encabezados no es válida.")
    if period is None or period.day != 1:
        raise UploadError("period_required", "Debe indicar el primer día del periodo mensual.")
    if source_type != "cartera_mensual" or schema_name != "carteraMensual":
        raise UploadError(
            "source_not_enabled",
            "La primera integración admite únicamente la cartera mensual.",
        )
    profile = SOURCE_PROFILES.get(profile_id) if profile_id else None
    if profile_id and profile is None:
        raise UploadError("profile_unknown", "El perfil de columnas no está registrado.")
    if profile and (
        profile.schema_name != schema_name
        or (profile.period is not None and profile.period != period)
    ):
        raise UploadError(
            "profile_incompatible",
            "El perfil de columnas no corresponde al esquema o periodo.",
        )
    if reference_batch is not None:
        valid_reference_states = {
            Batch.Status.READY,
            Batch.Status.APPROVED,
            Batch.Status.EXPORTED,
        }
        reference_invalid = (
            (not is_superuser and reference_batch.owner_area != owner_area)
            or reference_batch.status not in valid_reference_states
            or reference_batch.period is None
            or period is None
            or reference_batch.period >= period
            or reference_batch.source_type != "cartera_mensual"
            or reference_batch.schema_name != schema_name
            or not reference_batch.records.exists()
            or (
                bool(getattr(settings, "ARNOLD_REQUIRE_ANTIVIRUS", False))
                and reference_batch.scan_status != Batch.ScanStatus.PASSED
            )
        )
        if reference_invalid:
            raise UploadError(
                "invalid_reference",
                "La referencia debe ser anterior, compatible y estar validada.",
            )

    root = Path(settings.ARNOLD_FILE_ROOT)
    incoming = root / "quarantine" / ".incoming"
    destination_dir = root / "quarantine"
    incoming.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    max_bytes = int(settings.ARNOLD_MAX_UPLOAD_BYTES)
    digest = sha256()
    size = 0
    temp_path: Path | None = None
    destination: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(dir=incoming, suffix=".part", delete=False) as handle:
            temp_path = Path(handle.name)
            for chunk in uploaded_file.chunks():
                size += len(chunk)
                if size > max_bytes:
                    raise UploadError("file_too_large", "El archivo supera el límite permitido.", status=413)
                digest.update(chunk)
                handle.write(chunk)
        os.chmod(temp_path, 0o600)
        if size == 0:
            raise UploadError("empty_file", "El archivo está vacío.")

        try:
            inspect_xlsx_archive(temp_path)
        except ExcelAdapterError as exc:
            raise UploadError(exc.code, str(exc)) from exc
        scan_status = _scan(temp_path)
        file_digest = digest.hexdigest()

        existing = Batch.objects.filter(
            sha256=file_digest,
            owner_area=owner_area,
            period=period,
            source_type=source_type,
            sheet_name=sheet_name.strip()[:120],
            header_row=header_row,
            schema_name=schema_name,
            profile_id=profile_id,
        ).first()
        if existing:
            raise DuplicateUploadError(str(existing.id))

        try:
            with transaction.atomic():
                batch = Batch.objects.create(
                    display_name=display_name,
                    sha256=file_digest,
                    source_type=source_type,
                    period=period,
                    status=Batch.Status.QUARANTINED,
                    file_size=size,
                    content_type=str(getattr(uploaded_file, "content_type", ""))[:120],
                    owner_area=owner_area,
                    sheet_name=sheet_name.strip()[:120],
                    header_row=header_row,
                    schema_name=schema_name,
                    profile_id=profile_id,
                    adapter_version=ADAPTER_VERSION,
                    scan_status=scan_status,
                    uploaded_by=uploaded_by,
                )
                destination = batch_file_path(batch)
                os.replace(temp_path, destination)
                temp_path = None
                run = ValidationRun.objects.create(
                    current_batch=batch,
                    reference_batch=reference_batch,
                    created_by=uploaded_by,
                    input_digest=validation_input_digest(
                        current_batch=batch,
                        reference_batch=reference_batch,
                        enabled_rules=tuple(RuleCode),
                    ),
                    engine_version=ENGINE_VERSION,
                    adapter_version=ADAPTER_VERSION,
                    enabled_rules=[item.value for item in RuleCode],
                )
                append_audit_event(
                    actor=uploaded_by,
                    action="batch.received",
                    object_type="Batch",
                    object_id=batch.id,
                    metadata={
                        "period": period.isoformat() if period else None,
                        "source_type": source_type,
                        "scan_status": scan_status,
                    },
                )
                transaction.on_commit(lambda: _enqueue_validation(run.id))
        except IntegrityError as exc:
            if destination and destination.exists():
                destination.unlink(missing_ok=True)
            raise DuplicateUploadError() from exc
        except Exception:
            if destination and destination.exists():
                destination.unlink(missing_ok=True)
            raise
        batch.refresh_from_db()
        run.refresh_from_db()
        return UploadResult(batch=batch, run=run)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def requeue_failed_batch(batch: Batch, *, requested_by) -> ValidationRun:
    """Reintenta fallos operativos sin volver a cargar ni duplicar el archivo."""

    with transaction.atomic():
        locked_batch = Batch.objects.select_for_update().get(id=batch.id)
        run = (
            ValidationRun.objects.select_for_update()
            .filter(current_batch=locked_batch)
            .order_by("-created_at")
            .first()
        )
        if (
            run is None
            or run.status != ValidationRun.Status.FAILED
            or run.error_code not in RETRYABLE_RUN_ERRORS
        ):
            raise UploadError(
                "not_retryable",
                "Este lote no tiene un fallo operativo reintentable.",
                status=409,
            )
        run.status = ValidationRun.Status.QUEUED
        run.error_code = ""
        run.error_message = ""
        run.finished_at = None
        run.lease_expires_at = None
        run.save(update_fields=(
            "status", "error_code", "error_message", "finished_at",
            "lease_expires_at", "updated_at",
        ))
        locked_batch.status = Batch.Status.QUARANTINED
        locked_batch.failure_code = ""
        locked_batch.failure_message = ""
        locked_batch.save(update_fields=(
            "status", "failure_code", "failure_message", "updated_at",
        ))
        append_audit_event(
            actor=requested_by,
            action="validation.requeued",
            object_type="ValidationRun",
            object_id=run.id,
            metadata={"batch_id": str(locked_batch.id)},
        )
        transaction.on_commit(lambda: _enqueue_validation(run.id))
    run.refresh_from_db()
    return run

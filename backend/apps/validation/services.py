"""Puente entre archivos/lotes persistidos y el motor financiero puro."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.batches.crypto import blind_index, decrypt_json, encrypt_json
from apps.batches.models import Batch, Record
from apps.audit.services import append_audit_event

from .contracts import (
    ENGINE_VERSION,
    CellKind,
    DatasetInput,
    DatasetRole,
    FieldCell,
    RecordInput,
    RuleCode,
    ValidationInput,
    canonical_json,
    json_compatible,
)
from .digests import validation_input_digest
from .excel_adapter import ADAPTER_VERSION, ExcelAdapterError, parse_xlsx
from .models import ValidationIssue, ValidationRun
from .rules import SCHEMAS, normalize_header, validate


class ValidationConfigurationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _file_path(batch: Batch) -> Path:
    return Path(settings.ARNOLD_FILE_ROOT) / "quarantine" / f"{batch.storage_key}.xlsx"


def _verify_file_integrity(batch: Batch, path: Path) -> None:
    digest = sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                size += len(chunk)
                digest.update(chunk)
    except OSError:
        raise
    if size != batch.file_size or digest.hexdigest() != batch.sha256:
        raise ExcelAdapterError(
            "file_integrity",
            "El archivo en cuarentena no coincide con la huella registrada.",
        )


def _cell_payload(cell: FieldCell) -> dict:
    return {
        "value": json_compatible(cell.value),
        "raw": cell.raw,
        "kind": cell.kind.value,
    }


def _record_payload(record: RecordInput) -> dict:
    return {
        "source_row": record.source_row,
        "fields": {name: _cell_payload(cell) for name, cell in record.fields.items()},
    }


def _record_aad(batch_id, record_id, source_row: int) -> str:
    return f"record:{batch_id}:{record_id}:{source_row}"


def _headers_aad(batch_id) -> str:
    return f"batch-headers:{batch_id}"


def _safe_header_manifest(dataset: DatasetInput) -> list[str]:
    schema = SCHEMAS.get(dataset.schema_name, {})
    allowed = set(schema.get("required", ())) | set(schema.get("optional", ()))
    result: list[str] = []
    for position, original in enumerate(dataset.original_headers, start=1):
        normalized = normalize_header(original, dataset.schema_name)
        result.append(normalized if normalized in allowed else f"COLUMNA_{position}")
    return result


def _persist_dataset(batch: Batch, dataset: DatasetInput) -> None:
    objects: list[Record] = []

    def flush() -> None:
        if not objects:
            return
        Record.objects.bulk_create(
            objects,
            update_conflicts=True,
            update_fields=(
                "clave_hmac",
                "ciu_hmac",
                "identifier_hmac",
                "data_ciphertext",
            ),
            unique_fields=("batch", "source_row"),
        )
        objects.clear()

    for item in dataset.records:
        clave = item.text("CLAVE")
        ciu = item.text("CIU")
        identifier = item.text("CEDULA_RUC") or item.text("CEDULA")
        objects.append(
            Record(
                id=item.record_id,
                batch=batch,
                source_row=item.source_row,
                clave_hmac=blind_index(clave) if clave else "",
                ciu_hmac=blind_index(ciu) if ciu else "",
                identifier_hmac=blind_index(identifier) if identifier else "",
                data_ciphertext=encrypt_json(
                    _record_payload(item),
                    associated_data=_record_aad(batch.id, item.record_id, item.source_row),
                ),
                status=Record.Status.PENDING,
            )
        )
        if len(objects) >= 1_000:
            flush()
    flush()

    batch.row_count = len(dataset.records)
    batch.schema_name = dataset.schema_name
    batch.original_headers = _safe_header_manifest(dataset)
    batch.headers_ciphertext = encrypt_json(
        list(dataset.original_headers),
        associated_data=_headers_aad(batch.id),
    )
    batch.selected_occurrences = dict(dataset.selected_occurrences)
    batch.adapter_version = ADAPTER_VERSION
    batch.save(update_fields=(
        "row_count",
        "schema_name",
        "original_headers",
        "headers_ciphertext",
        "selected_occurrences",
        "adapter_version",
        "updated_at",
    ))


def _load_record(record: Record, dataset_id: str) -> RecordInput:
    payload = decrypt_json(
        record.data_ciphertext,
        associated_data=_record_aad(record.batch_id, record.id, record.source_row),
    )
    if int(payload.get("source_row", 0)) != record.source_row:
        raise ValidationConfigurationError(
            "record_integrity",
            "La procedencia autenticada del registro no coincide con la base.",
        )
    fields = {
        name: FieldCell(
            value=cell.get("value"),
            raw=cell.get("raw"),
            kind=CellKind(cell.get("kind", CellKind.VALUE.value)),
        )
        for name, cell in payload["fields"].items()
    }
    return RecordInput(
        dataset_id=dataset_id,
        record_id=str(record.id),
        source_row=record.source_row,
        fields=fields,
    )


def _load_dataset(
    batch: Batch,
    role: DatasetRole,
    *,
    parent_dataset_id: str | None = None,
) -> DatasetInput:
    dataset_id = str(batch.id)
    records = tuple(
        _load_record(record, dataset_id)
        for record in batch.records.order_by("source_row").iterator(chunk_size=1_000)
    )
    original_headers = (
        tuple(decrypt_json(
            batch.headers_ciphertext,
            associated_data=_headers_aad(batch.id),
        ))
        if batch.headers_ciphertext else tuple(batch.original_headers)
    )
    return DatasetInput(
        dataset_id=dataset_id,
        batch_id=dataset_id,
        role=role,
        period=batch.period,
        schema_name=batch.schema_name,
        original_headers=original_headers,
        records=records,
        profile_id=batch.profile_id or None,
        sha256=batch.sha256,
        parent_dataset_id=parent_dataset_id,
        selected_occurrences=batch.selected_occurrences,
    )


def _parse_and_store(
    batch: Batch,
    role: DatasetRole,
    *,
    parent_dataset_id: str | None = None,
) -> DatasetInput:
    path = _file_path(batch)
    _verify_file_integrity(batch, path)
    dataset = parse_xlsx(
        path,
        batch_id=str(batch.id),
        role=role,
        period=batch.period,
        schema_name=batch.schema_name,
        sheet_name=batch.sheet_name,
        header_row=batch.header_row,
        profile_id=batch.profile_id or None,
        parent_dataset_id=parent_dataset_id,
    )
    _persist_dataset(batch, dataset)
    return dataset


def _dataset(
    batch: Batch,
    role: DatasetRole,
    *,
    force_parse: bool = False,
    parent_dataset_id: str | None = None,
) -> DatasetInput:
    if force_parse or not batch.records.exists():
        return _parse_and_store(batch, role, parent_dataset_id=parent_dataset_id)
    return _load_dataset(batch, role, parent_dataset_id=parent_dataset_id)


def _subject_payload(subject) -> dict | None:
    if subject is None:
        return None
    return {
        "dataset_id": subject.dataset_id,
        "batch_id": subject.batch_id,
        "record_id": subject.record_id,
        "source_row": subject.source_row,
        "period": subject.period.isoformat() if subject.period else None,
        "clave": subject.clave,
        "ciu": subject.ciu,
        "cedula_ruc": subject.cedula_ruc,
        "nombres": subject.nombres,
    }


def _persist_report(run: ValidationRun, report) -> None:
    batches = [item for item in (
        run.current_batch,
        run.reference_batch,
        run.consolidated_batch,
        run.catalog_batch,
        run.orders_batch,
    ) if item is not None]
    batch_by_id = {str(item.id): item for item in batches}
    records = Record.objects.filter(batch__in=batches).only("id", "batch_id")
    record_by_id = {str(item.id): item for item in records}
    observed_current: set[str] = set()

    for result in report.issues:
        subject_record = record_by_id.get(result.subject.record_id) if result.subject else None
        subject_batch = (
            batch_by_id.get(result.subject.batch_id)
            if result.subject else
            batch_by_id.get(str(result.evidence.get("dataset_id", "")), run.current_batch)
        )
        private_evidence = {
            "evidence": json_compatible(result.evidence),
            "subject": _subject_payload(result.subject),
            "related": [_subject_payload(item) for item in result.related],
        }
        evidence_json = canonical_json(private_evidence)
        evidence_sha = sha256(evidence_json.encode("utf-8")).hexdigest()
        issue, _ = ValidationIssue.objects.update_or_create(
            run=run,
            fingerprint=result.fingerprint,
            defaults={
                "subject_batch": subject_batch,
                "record": subject_record,
                "rule_code": result.rule_code.value,
                "severity": result.severity.value,
                "blocking": result.blocking,
                "field_name": result.field_name or "",
                "message": result.message[:500],
                "evidence": {"encrypted": True, "sha256": evidence_sha},
                "evidence_ciphertext": encrypt_json(
                    private_evidence,
                    associated_data=f"issue:{run.id}:{result.fingerprint}",
                ),
                "evidence_sha256": evidence_sha,
                "engine_version": result.engine_version,
                "requires_review": result.requires_review,
            },
        )
        related_objects = [
            record_by_id[item.record_id]
            for item in result.related
            if item.record_id in record_by_id
        ]
        issue.related_records.set(related_objects)
        if (
            subject_record
            and subject_record.batch_id == run.current_batch_id
            and result.requires_review
        ):
            observed_current.add(str(subject_record.id))

    Record.objects.filter(batch=run.current_batch).update(status=Record.Status.READY)
    if observed_current:
        Record.objects.filter(id__in=observed_current).update(status=Record.Status.OBSERVED)

    now = timezone.now()
    run.status = ValidationRun.Status.SUCCEEDED
    run.issue_count = len(report.issues)
    run.blocking_count = report.blocking_count
    run.executed_rules = [item.value for item in report.executed_rules]
    run.skipped_rules = {item.value: reason for item, reason in report.skipped_rules.items()}
    run.error_code = ""
    run.error_message = ""
    run.lease_expires_at = None
    run.finished_at = now
    run.save(update_fields=(
        "status", "issue_count", "blocking_count", "executed_rules",
        "skipped_rules", "error_code", "error_message", "lease_expires_at",
        "finished_at", "updated_at",
    ))
    batch = run.current_batch
    batch.status = (
        Batch.Status.REVIEW
        if any(issue.requires_review or issue.blocking for issue in report.issues)
        else Batch.Status.READY
    )
    batch.validated_at = now
    batch.failure_code = ""
    batch.failure_message = ""
    batch.save(update_fields=(
        "status", "validated_at", "failure_code", "failure_message", "updated_at",
    ))
    append_audit_event(
        actor=run.created_by,
        action="validation.completed",
        object_type="ValidationRun",
        object_id=run.id,
        metadata={
            "batch_id": str(batch.id),
            "issue_count": run.issue_count,
            "blocking_count": run.blocking_count,
            "batch_status": batch.status,
            "engine_version": run.engine_version,
        },
    )
    from apps.workflow.worksheet import prepare_worksheet
    prepare_worksheet(batch)


def execute_validation(run_id, *, execution_token: str) -> dict:
    """Ejecuta y guarda una validación; repetirla no duplica incidencias."""

    run = ValidationRun.objects.select_related(
        "current_batch", "reference_batch", "consolidated_batch", "catalog_batch", "orders_batch"
    ).get(id=run_id)
    if run.engine_version != ENGINE_VERSION or run.adapter_version != ADAPTER_VERSION:
        raise ValidationConfigurationError(
            "incompatible_version",
            "La ejecución fue creada con otra versión del motor o adaptador.",
        )
    expected_digest = validation_input_digest(
        current_batch=run.current_batch,
        reference_batch=run.reference_batch,
        consolidated_batch=run.consolidated_batch,
        catalog_batch=run.catalog_batch,
        orders_batch=run.orders_batch,
        enabled_rules=run.enabled_rules,
        engine_version=run.engine_version,
        adapter_version=run.adapter_version,
    )
    if expected_digest != run.input_digest:
        raise ValidationConfigurationError(
            "input_changed",
            "La configuración del lote cambió después de crear la ejecución.",
        )
    current = _dataset(run.current_batch, DatasetRole.CURRENT, force_parse=True)
    reference = (
        _dataset(run.reference_batch, DatasetRole.REFERENCE)
        if run.reference_batch else None
    )
    consolidated = (
        _dataset(
            run.consolidated_batch,
            DatasetRole.CONSOLIDATED,
            parent_dataset_id=current.dataset_id,
        )
        if run.consolidated_batch else None
    )
    catalog = (
        _dataset(run.catalog_batch, DatasetRole.CATALOG)
        if run.catalog_batch else None
    )
    orders_parent = consolidated.dataset_id if consolidated else current.dataset_id
    orders = (
        _dataset(
            run.orders_batch,
            DatasetRole.ORDERS,
            parent_dataset_id=orders_parent,
        )
        if run.orders_batch else None
    )
    validation_input = ValidationInput(
        current=current,
        reference=reference,
        consolidated=consolidated,
        catalog=catalog,
        orders=orders,
    )
    report = validate(validation_input, tuple(RuleCode(item) for item in run.enabled_rules))
    with transaction.atomic():
        locked = ValidationRun.objects.select_for_update().get(id=run.id)
        if (
            locked.status != ValidationRun.Status.RUNNING
            or locked.task_id != execution_token
        ):
            raise ValidationConfigurationError(
                "stale_execution",
                "Otra ejecución obtuvo el control del lote antes de guardar el resultado.",
            )
        _persist_report(locked, report)
    return {
        "run_id": str(run.id),
        "batch_id": str(run.current_batch_id),
        "status": ValidationRun.Status.SUCCEEDED,
        "issues": len(report.issues),
        "blocking": report.blocking_count,
    }

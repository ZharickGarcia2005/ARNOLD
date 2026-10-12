"""Reglas versionadas del validador financiero de ARNOLD."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from itertools import islice
from typing import Callable, Iterable, Mapping
import unicodedata

from .comparators import (
    ConsolidationStatus,
    canonical_key,
    compare_months,
    compare_order_traceability,
    exact_duplicate_groups,
    group_by_key,
    reconcile_consolidated,
)
from .contracts import (
    ENGINE_VERSION,
    CellKind,
    DatasetInput,
    PaymentClaim,
    RecordInput,
    RuleCode,
    RuleResult,
    Severity,
    SourceProfile,
    SubjectRef,
    ValidationInput,
    ValidationReport,
    canonical_json,
    deduplicate_results,
)


SCHEMAS: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "carteraMensual": {
        "required": (
            "CIU",
            "CEDULA_RUC",
            "NOMBRES",
            "CLAVE",
            "TOTAL_EMISION",
            "TOTAL_INTERES",
            "TOTAL_COACTIVA",
            "TOTAL_RECARGO",
            "MESES_DEUDA",
        ),
        "optional": ("DIRECCION", "PARROQUIA", "TELEF", "CORREO"),
    },
    "carteraUnificada": {
        "required": (
            "PREDIO_MUN",
            "NOMBRES",
            "CEDULA_RUC",
            "CIU",
            "EMISION",
            "INTERES",
            "COACTIVA",
            "TOTAL_RECARGO",
            "VALOR_TOTAL",
            "TITULOS",
        ),
        "optional": (
            "TP",
            "EXP",
            "CLAVE",
            "OP",
            "OC",
            "DIGIT",
            "DIRECCION",
            "PARROQUIA",
            "COD_PARROQUIA",
            "ZONA",
            "SECTOR",
            "MANZANA",
            "PREDIO",
            "ID_PLAN",
            "TELEFONO",
            "CORREO",
        ),
    },
    "ordenPreliminar": {
        "required": (
            "PREDIO_MUN",
            "NOMBRES",
            "CEDULA_RUC",
            "CLAVE",
            "CIU",
            "EMISION",
            "INTERES",
            "RECARGO",
            "TOTAL",
        ),
        "optional": (
            "TP",
            "EXP",
            "OP",
            "OC",
            "DIGIT",
            "DIRECCION",
            "PARROQUIA",
            "COD_PARROQUIA",
            "ZONA",
            "SECTOR",
            "MANZANA",
            "PREDIO",
            "ID_PLAN",
            "TELEFONO",
            "CORREO",
            "TITULOS",
            "DIGITADOR",
            "FECHA",
            "HORA",
            "NOVEDAD",
        ),
    },
}

NUMERIC_FIELDS_BY_SCHEMA: Mapping[str, tuple[str, ...]] = {
    "carteraMensual": (
        "TOTAL_EMISION",
        "TOTAL_INTERES",
        "TOTAL_COACTIVA",
        "TOTAL_RECARGO",
    ),
    "carteraUnificada": (
        "EMISION",
        "INTERES",
        "COACTIVA",
        "TOTAL_RECARGO",
        "VALOR_TOTAL",
    ),
    "ordenPreliminar": ("EMISION", "INTERES", "RECARGO", "TOTAL"),
}

MAX_RELATED_SUBJECTS = 50

PAYMENT_STATUSES: Mapping[str, str] = {
    "PAGADO": "pagado",
    "PAGADA": "pagado",
    "PAGO": "pagado",
    "PAID": "pagado",
    "CANCELADO": "cancelado",
    "CANCELADA": "cancelado",
    "CANCELED": "cancelado",
    "CANCELLED": "cancelado",
}

HEADER_ALIASES: Mapping[str, str] = {
    "CEDULA": "CEDULA_RUC",
    "RUC_CEDULA": "CEDULA_RUC",
    "CONTRIBUYENTE": "NOMBRES",
    "PREDIO_MUNICIPAL": "PREDIO_MUN",
    "ID_PLAN": "ID_PLAN",
    "TITULO": "TITULOS",
    "MZ": "MANZANA",
    "PARROQ": "COD_PARROQUIA",
}

SOURCE_PROFILES: Mapping[str, SourceProfile] = {
    "cartera_mensual_strict": SourceProfile(
        "cartera_mensual_strict", "carteraMensual", {}
    ),
    "julio_2026_confirmado": SourceProfile(
        "julio_2026_confirmado",
        "carteraMensual",
        {
            "TOTAL_EMISION": 2,
            "TOTAL_INTERES": 2,
            "TOTAL_COACTIVA": 2,
            "TOTAL_RECARGO": 2,
        },
        period=date(2026, 7, 1),
    ),
}


@dataclass(frozen=True, slots=True)
class RuleDefinition:
    code: RuleCode
    severity: Severity
    title: str
    description: str


RULE_CATALOG: Mapping[RuleCode, RuleDefinition] = {
    RuleCode.SCHEMA_001: RuleDefinition(
        RuleCode.SCHEMA_001,
        Severity.CRITICAL,
        "Estructura y tipos requeridos",
        "Faltan columnas obligatorias, no se reconoce la estructura o hay importes inválidos.",
    ),
    RuleCode.SCHEMA_002: RuleDefinition(
        RuleCode.SCHEMA_002,
        Severity.CRITICAL,
        "Encabezados duplicados",
        "Existen columnas ambiguas sin un perfil de fuente explícito.",
    ),
    RuleCode.KEY_001: RuleDefinition(
        RuleCode.KEY_001,
        Severity.CRITICAL,
        "Clave mensual única",
        "CLAVE debe existir y no repetirse dentro de la cartera mensual.",
    ),
    RuleCode.KEY_002: RuleDefinition(
        RuleCode.KEY_002,
        Severity.WARNING,
        "Conflicto de identidad",
        "La misma CLAVE cambió de identificación o CIU entre periodos.",
    ),
    RuleCode.DUP_001: RuleDefinition(
        RuleCode.DUP_001,
        Severity.WARNING,
        "Repetición consolidable",
        "El consolidado debe coincidir con una fila, no con una suma implícita.",
    ),
    RuleCode.CAT_001: RuleDefinition(
        RuleCode.CAT_001,
        Severity.WARNING,
        "Catálogo contradictorio",
        "Hay una fila exacta repetida o una clave asociada con identidades distintas.",
    ),
    RuleCode.FORMULA_001: RuleDefinition(
        RuleCode.FORMULA_001,
        Severity.CRITICAL,
        "Fórmula o error almacenado",
        "Las fórmulas y errores de Excel se registran como evidencia y no se ejecutan.",
    ),
    RuleCode.MONTH_001: RuleDefinition(
        RuleCode.MONTH_001,
        Severity.INFO,
        "Cambios mensuales",
        "Informa altas, ausencias y cambios monetarios sin inferir pago.",
    ),
    RuleCode.PAYMENT_001: RuleDefinition(
        RuleCode.PAYMENT_001,
        Severity.CRITICAL,
        "Pago o cancelación con respaldo",
        "Un pago o cancelación requiere fuente autorizada y doble control.",
    ),
    RuleCode.ORDER_001: RuleDefinition(
        RuleCode.ORDER_001,
        Severity.WARNING,
        "Orden trazable",
        "Cada orden debe tener un origen único y verificable.",
    ),
    RuleCode.ORDER_002: RuleDefinition(
        RuleCode.ORDER_002,
        Severity.CRITICAL,
        "Orden incompleta",
        "La orden no puede aprobarse si faltan identificadores o importes.",
    ),
}


@dataclass(frozen=True, slots=True)
class HeaderOccurrence:
    original: str
    normalized: str
    occurrence: int
    unique_name: str


@dataclass(frozen=True, slots=True)
class SchemaRecognition:
    schema_name: str | None
    valid: bool
    missing: tuple[str, ...]
    duplicate_headers: Mapping[str, int]


def normalize_header(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    clean = "_".join(text.strip().upper().split())
    return HEADER_ALIASES.get(clean, clean)


def make_unique_headers(headers: Iterable[object]) -> tuple[HeaderOccurrence, ...]:
    seen: Counter[str] = Counter()
    result: list[HeaderOccurrence] = []
    for original_value in headers:
        original = "" if original_value is None else str(original_value)
        base = normalize_header(original_value) or "SIN_ENCABEZADO"
        seen[base] += 1
        occurrence = seen[base]
        unique_name = base if occurrence == 1 else f"{base}__{occurrence}"
        result.append(HeaderOccurrence(original, base, occurrence, unique_name))
    return tuple(result)


def recognize_schema(headers: Iterable[object]) -> SchemaRecognition:
    occurrences = make_unique_headers(headers)
    counts = Counter(item.normalized for item in occurrences)
    available = set(counts)
    candidates: list[tuple[int, str, tuple[str, ...]]] = []
    for name, schema in SCHEMAS.items():
        missing = tuple(field for field in schema["required"] if field not in available)
        candidates.append((len(missing), name, missing))
    _, name, missing = min(candidates, key=lambda item: (item[0], item[1]))
    duplicates = {field: count for field, count in counts.items() if count > 1}
    return SchemaRecognition(name, not missing, missing, duplicates)


def _all_datasets(data: ValidationInput) -> tuple[DatasetInput, ...]:
    return tuple(
        dataset
        for dataset in (
            data.current,
            data.reference,
            data.consolidated,
            data.catalog,
            data.orders,
        )
        if dataset is not None
    )


def _dataset_for_record(data: ValidationInput, record: RecordInput) -> DatasetInput:
    for dataset in _all_datasets(data):
        if dataset.dataset_id == record.dataset_id:
            return dataset
    return data.current


def _subject(record: RecordInput, dataset: DatasetInput) -> SubjectRef:
    return SubjectRef.from_record(record, dataset)


def _related(
    records: Iterable[RecordInput],
    dataset: DatasetInput,
    *,
    limit: int = MAX_RELATED_SUBJECTS,
) -> tuple[SubjectRef, ...]:
    return tuple(_subject(record, dataset) for record in islice(records, limit))


def _group_evidence(
    records: Iterable[RecordInput],
    *,
    key: str = "filas",
    limit: int = MAX_RELATED_SUBJECTS,
) -> Mapping[str, object]:
    """Resume grupos grandes sin construir evidencia cuadrática por fila."""

    ordered = tuple(sorted(records, key=lambda item: (item.source_row, item.record_id)))
    rows = tuple(item.source_row for item in ordered)
    return {
        key: rows[:limit],
        "cantidad_total": len(rows),
        "cantidad_omitida": max(0, len(rows) - limit),
        "huella_grupo": sha256(canonical_json(rows).encode("utf-8")).hexdigest(),
    }


def _result(
    code: RuleCode,
    *,
    subject: SubjectRef | None,
    message: str,
    evidence: Mapping[str, object],
    related: tuple[SubjectRef, ...] = (),
    field_name: str | None = None,
    severity: Severity | None = None,
    blocking: bool | None = None,
    requires_review: bool = True,
) -> RuleResult:
    definition = RULE_CATALOG[code]
    selected_severity = severity or definition.severity
    if blocking is None:
        blocking = selected_severity == Severity.CRITICAL
    return RuleResult(
        rule_code=code,
        severity=selected_severity,
        blocking=blocking,
        requires_review=requires_review,
        subject=subject,
        related=related,
        field_name=field_name,
        message=message,
        evidence=evidence,
    )


def _schema_001(data: ValidationInput) -> list[RuleResult]:
    results: list[RuleResult] = []
    for dataset in _all_datasets(data):
        is_current = dataset is data.current
        severity = Severity.CRITICAL if is_current else Severity.WARNING
        recognition = recognize_schema(dataset.original_headers)
        schema = SCHEMAS.get(dataset.schema_name)
        available = {
            item.normalized for item in make_unique_headers(dataset.original_headers)
        }
        if schema is None:
            missing = recognition.missing
            message = f"Esquema desconocido: {dataset.schema_name or '(vacío)'}"
        else:
            missing = tuple(field for field in schema["required"] if field not in available)
            message = "Faltan columnas requeridas: " + ", ".join(missing)
        if schema is None or missing:
            results.append(
                _result(
                    RuleCode.SCHEMA_001,
                    subject=None,
                    message=message,
                    evidence={
                        "dataset_id": dataset.dataset_id,
                        "schema_declarado": dataset.schema_name,
                        "schema_reconocido": recognition.schema_name,
                        "faltantes": missing,
                    },
                    severity=severity,
                    blocking=is_current,
                )
            )
        if schema is None:
            continue
        for record in dataset.records:
            numeric_fields = set(
                NUMERIC_FIELDS_BY_SCHEMA.get(dataset.schema_name, ())
            )
            for field_name in schema["required"]:
                if field_name not in available or field_name in numeric_fields:
                    continue
                if not _is_blank(record, field_name):
                    continue
                results.append(
                    _result(
                        RuleCode.SCHEMA_001,
                        subject=_subject(record, dataset),
                        field_name=field_name,
                        message=f"El campo obligatorio {field_name} está vacío.",
                        evidence={
                            "tipo": "campo_requerido_vacio",
                            "dataset_id": dataset.dataset_id,
                            "rol_dataset": dataset.role.value,
                            "campo": field_name,
                        },
                        severity=severity,
                        blocking=is_current,
                    )
                )
            for field_name in NUMERIC_FIELDS_BY_SCHEMA.get(dataset.schema_name, ()):
                if field_name not in available:
                    continue
                cell = record.cell(field_name)
                if record.decimal(field_name) is not None:
                    continue
                results.append(
                    _result(
                        RuleCode.SCHEMA_001,
                        subject=_subject(record, dataset),
                        field_name=field_name,
                        message=f"El importe {field_name} no es un número finito válido.",
                        evidence={
                            "tipo": "importe_invalido",
                            "dataset_id": dataset.dataset_id,
                            "rol_dataset": dataset.role.value,
                            "valor": cell.value,
                            "original": cell.raw,
                        },
                        severity=severity,
                        blocking=is_current,
                    )
                )
    return results


def _schema_002(data: ValidationInput) -> list[RuleResult]:
    results: list[RuleResult] = []
    for dataset in _all_datasets(data):
        recognition = recognize_schema(dataset.original_headers)
        duplicates = recognition.duplicate_headers
        if not duplicates:
            continue
        profile = SOURCE_PROFILES.get(dataset.profile_id or "")
        profile_valid = bool(
            profile
            and profile.schema_name == dataset.schema_name
            and (profile.period is None or profile.period == dataset.period)
        )
        if profile_valid:
            expected = dict(profile.selected_occurrences)
            applied = dict(dataset.selected_occurrences)
            profile_valid = (
                set(duplicates) == set(expected)
                and all(duplicates[field] == expected[field] for field in duplicates)
                and applied == expected
            )
        if not profile_valid:
            results.append(
                _result(
                    RuleCode.SCHEMA_002,
                    subject=None,
                    message="Hay encabezados duplicados sin un perfil explícito válido.",
                    evidence={
                        "dataset_id": dataset.dataset_id,
                        "duplicados": duplicates,
                        "perfil": dataset.profile_id,
                        "apariciones_aplicadas": dict(dataset.selected_occurrences),
                        "apariciones_esperadas": (
                            dict(profile.selected_occurrences) if profile else {}
                        ),
                        "periodo_esperado": (
                            profile.period.isoformat()
                            if profile and profile.period is not None
                            else None
                        ),
                        "periodo_dataset": (
                            dataset.period.isoformat()
                            if dataset.period is not None
                            else None
                        ),
                    },
                )
            )
    return results


def _key_001(data: ValidationInput) -> list[RuleResult]:
    dataset = data.current
    results: list[RuleResult] = []
    for record in dataset.records:
        if canonical_key(record, ("CLAVE",)) is None:
            results.append(
                _result(
                    RuleCode.KEY_001,
                    subject=_subject(record, dataset),
                    field_name="CLAVE",
                    message="El registro no contiene una CLAVE válida.",
                    evidence={"tipo": "clave_vacia"},
                )
            )
    for key, records in group_by_key(dataset.records, ("CLAVE",)).items():
        if len(records) < 2:
            continue
        group_evidence = _group_evidence(records)
        for record in records:
            results.append(
                _result(
                    RuleCode.KEY_001,
                    subject=_subject(record, dataset),
                    related=_related(
                        (item for item in records if item.record_id != record.record_id),
                        dataset,
                    ),
                    field_name="CLAVE",
                    message="La misma CLAVE aparece más de una vez en el periodo.",
                    evidence={"clave": key[0], **group_evidence},
                )
            )
    return results


def _key_002(data: ValidationInput) -> list[RuleResult]:
    assert data.reference is not None
    comparison = compare_months(data.current, data.reference)
    results: list[RuleResult] = []
    for change in comparison.identity_changes:
        evidence_changes = [
            {
                "campo": item.field_name,
                "anterior": item.previous,
                "actual": item.current,
            }
            for item in change.changes
        ]
        results.append(
            _result(
                RuleCode.KEY_002,
                subject=_subject(change.current, data.current),
                related=(_subject(change.reference, data.reference),),
                message="La identidad asociada con la CLAVE cambió entre periodos.",
                evidence={"cambios": evidence_changes},
                blocking=False,
            )
        )
    for ambiguity in comparison.ambiguous:
        subject = _subject(ambiguity.current[0], data.current) if ambiguity.current else None
        related = _related(ambiguity.current[1:], data.current)
        related += _related(ambiguity.reference, data.reference)
        results.append(
            _result(
                RuleCode.KEY_002,
                subject=subject,
                related=related,
                message="La CLAVE no puede compararse de forma unívoca entre periodos.",
                evidence={
                    "clave": ambiguity.key,
                    "actual": _group_evidence(ambiguity.current),
                    "referencia": _group_evidence(ambiguity.reference),
                },
                blocking=False,
            )
        )
    return results


def _dup_001(data: ValidationInput) -> list[RuleResult]:
    assert data.consolidated is not None
    comparison = reconcile_consolidated(data.current, data.consolidated)
    results: list[RuleResult] = []
    for fact in comparison.facts:
        if fact.status == ConsolidationStatus.MATCHED:
            continue
        if fact.consolidated_record is not None:
            subject = _subject(fact.consolidated_record, data.consolidated)
        elif fact.source_records:
            subject = _subject(fact.source_records[0], data.current)
        else:
            subject = None
        results.append(
            _result(
                RuleCode.DUP_001,
                subject=subject,
                related=_related(fact.source_records, data.current),
                message="El consolidado no coincide con una fila normalizada del grupo.",
                evidence={
                    "estado": fact.status.value,
                    "clave_grupo": fact.key,
                    "fuente": _group_evidence(fact.source_records),
                },
                blocking=False,
            )
        )
    return results


def _cat_001(data: ValidationInput) -> list[RuleResult]:
    results: list[RuleResult] = []
    for duplicate_group in exact_duplicate_groups(data.current.records):
        group_evidence = _group_evidence(duplicate_group)
        for record in duplicate_group:
            results.append(
                _result(
                    RuleCode.CAT_001,
                    subject=_subject(record, data.current),
                    related=_related(
                        (
                            item
                            for item in duplicate_group
                            if item.record_id != record.record_id
                        ),
                        data.current,
                    ),
                    message="La fila está repetida exactamente dentro del archivo.",
                    evidence={"tipo": "fila_exacta", **group_evidence},
                    blocking=False,
                )
            )

    if data.catalog is None:
        return results
    grouped_catalog: dict[tuple[str, ...], list[RecordInput]] = defaultdict(list)
    for record in data.catalog.records:
        key = canonical_key(record, ("CLAVE_NUEV",)) or canonical_key(
            record, ("CLAVE",)
        )
        if key is not None:
            grouped_catalog[key].append(record)
    catalog_groups = {
        key: tuple(sorted(records, key=lambda item: (item.source_row, item.record_id)))
        for key, records in sorted(grouped_catalog.items())
    }
    for key, records in catalog_groups.items():
        identities = {
            canonical_key(record, ("CEDULA_RUC", "CIU"))
            for record in records
            if canonical_key(record, ("CEDULA_RUC", "CIU")) is not None
        }
        if len(identities) <= 1:
            continue
        ordered_identities = tuple(sorted(identities))
        identity_evidence = {
            "identidades": ordered_identities[:MAX_RELATED_SUBJECTS],
            "cantidad_total": len(ordered_identities),
            "cantidad_omitida": max(
                0, len(ordered_identities) - MAX_RELATED_SUBJECTS
            ),
            "huella_grupo": sha256(
                canonical_json(ordered_identities).encode("utf-8")
            ).hexdigest(),
        }
        for record in records:
            results.append(
                _result(
                    RuleCode.CAT_001,
                    subject=_subject(record, data.catalog),
                    related=_related(
                        (item for item in records if item.record_id != record.record_id),
                        data.catalog,
                    ),
                    message="La clave del catálogo está asociada con identidades distintas.",
                    evidence={"clave": key, **identity_evidence},
                    blocking=False,
                )
            )
    return results


def _formula_001(data: ValidationInput) -> list[RuleResult]:
    results: list[RuleResult] = []
    for dataset in _all_datasets(data):
        is_current = dataset is data.current
        for record in dataset.records:
            for field_name, cell in record.fields.items():
                if cell.kind not in {CellKind.FORMULA, CellKind.ERROR}:
                    continue
                results.append(
                    _result(
                        RuleCode.FORMULA_001,
                        subject=_subject(record, dataset),
                        field_name=field_name,
                        message=(
                            "La cartera actual contiene una fórmula o un error de Excel."
                            if is_current
                            else "Una fuente auxiliar contiene una fórmula o un error de Excel."
                        ),
                        evidence={
                            "dataset_id": dataset.dataset_id,
                            "rol_dataset": dataset.role.value,
                            "tipo_celda": cell.kind.value,
                            "valor": cell.value,
                            "original": cell.raw,
                        },
                        severity=Severity.CRITICAL if is_current else Severity.WARNING,
                        blocking=is_current,
                    )
                )
    return results


def _month_001(data: ValidationInput) -> list[RuleResult]:
    assert data.reference is not None
    comparison = compare_months(data.current, data.reference)
    results: list[RuleResult] = []
    for record in comparison.new_records:
        results.append(
            _result(
                RuleCode.MONTH_001,
                subject=_subject(record, data.current),
                message="La CLAVE aparece por primera vez en el periodo actual.",
                evidence={"tipo": "alta", "implica_pago": False},
                blocking=False,
                requires_review=False,
            )
        )
    for record in comparison.missing_records:
        results.append(
            _result(
                RuleCode.MONTH_001,
                subject=_subject(record, data.reference),
                message="La CLAVE no aparece en el periodo actual; esto no demuestra pago.",
                evidence={"tipo": "ausencia", "implica_pago": False},
                blocking=False,
                requires_review=True,
            )
        )
    for change in comparison.amount_changes:
        evidence_changes = [
            {
                "campo": item.field_name,
                "anterior": item.previous,
                "actual": item.current,
            }
            for item in change.changes
        ]
        results.append(
            _result(
                RuleCode.MONTH_001,
                subject=_subject(change.current, data.current),
                related=(_subject(change.reference, data.reference),),
                message="Uno o más importes cambiaron respecto del periodo anterior.",
                evidence={
                    "tipo": "cambio_importe",
                    "cambios": evidence_changes,
                    "implica_pago": False,
                },
                blocking=False,
                requires_review=True,
            )
        )
    return results


def _payment_is_authorized(claim: PaymentClaim) -> bool:
    requester = (
        claim.requested_by.strip().casefold()
        if isinstance(claim.requested_by, str)
        else ""
    )
    approver = (
        claim.approved_by.strip().casefold()
        if isinstance(claim.approved_by, str)
        else ""
    )
    evidence = (
        claim.evidence_id.strip()
        if isinstance(claim.evidence_id, str)
        else ""
    )
    return bool(
        requester
        and approver
        and evidence
        and claim.authorized_source is True
        and isinstance(claim.approved_at, datetime)
        and approver != requester
    )


def _payment_001(data: ValidationInput) -> list[RuleResult]:
    results: list[RuleResult] = []
    for claim in data.payment_claims:
        status = normalize_header(claim.requested_status)
        dataset = _dataset_for_record(data, claim.record)
        if status not in PAYMENT_STATUSES:
            results.append(
                _result(
                    RuleCode.PAYMENT_001,
                    subject=_subject(claim.record, dataset),
                    message="La solicitud contiene un estado de pago no reconocido.",
                    evidence={
                        "tipo": "estado_no_reconocido",
                        "estado_solicitado": claim.requested_status,
                    },
                )
            )
            continue
        if _payment_is_authorized(claim):
            continue
        results.append(
            _result(
                RuleCode.PAYMENT_001,
                subject=_subject(claim.record, dataset),
                message="El pago o cancelación no cuenta con evidencia y doble control completos.",
                evidence={
                    "tipo": "doble_control_incompleto",
                    "estado_solicitado": claim.requested_status,
                    "estado_normalizado": PAYMENT_STATUSES[status],
                    "evidencia": claim.evidence_id,
                    "fuente_autorizada": claim.authorized_source,
                    "solicitante": claim.requested_by,
                    "aprobador": claim.approved_by,
                    "fecha_aprobacion": claim.approved_at,
                },
            )
        )
    return results


def _order_001(data: ValidationInput) -> list[RuleResult]:
    assert data.orders is not None
    source = data.consolidated or data.current
    key_fields = (
        ("PREDIO_MUN", "CEDULA_RUC", "CIU")
        if data.consolidated is not None
        else ("CLAVE", "CEDULA_RUC", "CIU")
    )
    comparison = compare_order_traceability(
        data.orders,
        source,
        key_fields=key_fields,
    )
    results: list[RuleResult] = []
    for status, facts in (("sin_origen", comparison.missing), ("origen_ambiguo", comparison.ambiguous)):
        for fact in facts:
            results.append(
                _result(
                    RuleCode.ORDER_001,
                    subject=_subject(fact.order, data.orders),
                    related=_related(fact.sources, source),
                    message="La orden no tiene un origen único y trazable.",
                    evidence={
                        "estado": status,
                        "campos_trazabilidad": key_fields,
                        "origen": _group_evidence(fact.sources),
                    },
                    blocking=False,
                )
            )
    return results


def _is_blank(record: RecordInput, field_name: str) -> bool:
    return not record.text(field_name)


def _order_002(data: ValidationInput) -> list[RuleResult]:
    assert data.orders is not None
    results: list[RuleResult] = []
    required = ("CLAVE", "CIU", "CEDULA_RUC", "ID_PLAN", "EMISION", "INTERES", "RECARGO", "TOTAL")
    numeric_fields = {"EMISION", "INTERES", "RECARGO", "TOTAL"}
    for record in data.orders.records:
        for field_name in required:
            if field_name == "CEDULA_RUC" and not _is_blank(record, "CEDULA"):
                continue
            if _is_blank(record, field_name):
                results.append(
                    _result(
                        RuleCode.ORDER_002,
                        subject=_subject(record, data.orders),
                        field_name=field_name,
                        message=f"La orden no contiene el campo obligatorio {field_name}.",
                        evidence={"tipo": "campo_faltante", "campo": field_name},
                    )
                )
                continue
            if field_name in numeric_fields and record.decimal(field_name) is None:
                cell = record.cell(field_name)
                results.append(
                    _result(
                        RuleCode.ORDER_002,
                        subject=_subject(record, data.orders),
                        field_name=field_name,
                        message=f"La orden contiene un importe inválido en {field_name}.",
                        evidence={
                            "tipo": "importe_invalido",
                            "campo": field_name,
                            "valor": cell.value,
                            "original": cell.raw,
                        },
                    )
                )
    return results


RuleHandler = Callable[[ValidationInput], list[RuleResult]]

_HANDLERS: Mapping[RuleCode, RuleHandler] = {
    RuleCode.SCHEMA_001: _schema_001,
    RuleCode.SCHEMA_002: _schema_002,
    RuleCode.KEY_001: _key_001,
    RuleCode.KEY_002: _key_002,
    RuleCode.DUP_001: _dup_001,
    RuleCode.CAT_001: _cat_001,
    RuleCode.FORMULA_001: _formula_001,
    RuleCode.MONTH_001: _month_001,
    RuleCode.PAYMENT_001: _payment_001,
    RuleCode.ORDER_001: _order_001,
    RuleCode.ORDER_002: _order_002,
}


def _skip_reason(code: RuleCode, data: ValidationInput) -> str | None:
    if code in {RuleCode.KEY_002, RuleCode.MONTH_001} and data.reference is None:
        return "No se proporcionó una cartera histórica de referencia."
    if code == RuleCode.DUP_001 and data.consolidated is None:
        return "No se proporcionó una cartera consolidada."
    if code in {RuleCode.ORDER_001, RuleCode.ORDER_002} and data.orders is None:
        return "No se proporcionó un conjunto de órdenes."
    return None


def validate(
    validation_input: ValidationInput,
    enabled_rules: Iterable[RuleCode] | None = None,
) -> ValidationReport:
    selected = tuple(
        RuleCode(code) for code in (enabled_rules if enabled_rules is not None else RuleCode)
    )
    issues: list[RuleResult] = []
    executed: list[RuleCode] = []
    skipped: dict[RuleCode, str] = {}

    for code in selected:
        reason = _skip_reason(code, validation_input)
        if reason:
            skipped[code] = reason
            continue
        executed.append(code)
        issues.extend(_HANDLERS[code](validation_input))

    severity_order = {
        Severity.CRITICAL: 0,
        Severity.WARNING: 1,
        Severity.INFO: 2,
    }
    unique = deduplicate_results(issues)
    ordered = tuple(
        sorted(
            unique,
            key=lambda item: (
                severity_order[item.severity],
                item.rule_code.value,
                item.subject.source_row if item.subject else 0,
                item.subject.record_id if item.subject else "",
                item.fingerprint,
            ),
        )
    )
    return ValidationReport(
        engine_version=ENGINE_VERSION,
        current_dataset_id=validation_input.current.dataset_id,
        reference_dataset_id=(
            validation_input.reference.dataset_id if validation_input.reference else None
        ),
        issues=ordered,
        executed_rules=tuple(executed),
        skipped_rules=skipped,
    )

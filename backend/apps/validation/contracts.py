"""Contratos puros del motor financiero.

Este módulo no depende de Django ni de los modelos del proyecto. Esa separación
permite probar las reglas y acordar una interfaz con ARDUR-BETA sin acoplarse a
su implementación interna.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
from math import isfinite
from types import MappingProxyType
from typing import Any, Iterable, Mapping, TypeAlias


ENGINE_VERSION = "2026.10.1"

Scalar: TypeAlias = str | int | float | Decimal | bool | date | datetime | None
JsonValue: TypeAlias = (
    str
    | int
    | float
    | bool
    | None
    | list["JsonValue"]
    | dict[str, "JsonValue"]
)


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class RuleCode(str, Enum):
    SCHEMA_001 = "SCHEMA-001"
    SCHEMA_002 = "SCHEMA-002"
    KEY_001 = "KEY-001"
    KEY_002 = "KEY-002"
    DUP_001 = "DUP-001"
    CAT_001 = "CAT-001"
    FORMULA_001 = "FORMULA-001"
    MONTH_001 = "MONTH-001"
    PAYMENT_001 = "PAYMENT-001"
    ORDER_001 = "ORDER-001"
    ORDER_002 = "ORDER-002"


class DatasetRole(str, Enum):
    CURRENT = "current"
    REFERENCE = "reference"
    CONSOLIDATED = "consolidated"
    CATALOG = "catalog"
    ORDERS = "orders"


class CellKind(str, Enum):
    VALUE = "value"
    BLANK = "blank"
    FORMULA = "formula"
    ERROR = "error"


def _deep_freeze(value: Any) -> Any:
    """Copia y congela estructuras anidadas usadas como evidencia.

    Un ``dataclass(frozen=True)`` no protege listas o diccionarios contenidos en
    sus atributos. Congelar toda la estructura evita que una modificación
    externa cambie posteriormente la huella de una incidencia.
    """

    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        frozen = (_deep_freeze(item) for item in value)
        return tuple(sorted(frozen, key=canonical_json))
    return value


def _immutable_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return _deep_freeze(value or {})


def json_compatible(value: Any) -> JsonValue:
    """Convierte valores de dominio a una representación JSON estable."""

    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if isfinite(value) else str(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return json_compatible(value.value)
    if isinstance(value, Mapping):
        return {
            str(key): json_compatible(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [json_compatible(item) for item in value]
    if isinstance(value, (set, frozenset)):
        converted = [json_compatible(item) for item in value]
        return sorted(converted, key=canonical_json)
    return str(value)


def canonical_json(value: Any) -> str:
    return json.dumps(
        json_compatible(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


@dataclass(frozen=True, slots=True)
class FieldCell:
    value: Scalar = None
    raw: str | None = None
    kind: CellKind = CellKind.VALUE

    def __post_init__(self) -> None:
        if not isinstance(self.kind, CellKind):
            object.__setattr__(self, "kind", CellKind(self.kind))
        allowed = (str, int, float, Decimal, bool, date, datetime, type(None))
        if not isinstance(self.value, allowed):
            raise TypeError("FieldCell.value debe ser un valor escalar")
        if self.raw is not None and not isinstance(self.raw, str):
            raise TypeError("FieldCell.raw debe ser texto o None")


@dataclass(frozen=True, slots=True)
class RecordInput:
    dataset_id: str
    record_id: str
    source_row: int
    fields: Mapping[str, FieldCell]

    def __post_init__(self) -> None:
        if not self.dataset_id.strip():
            raise ValueError("dataset_id es obligatorio")
        if not self.record_id.strip():
            raise ValueError("record_id es obligatorio")
        if self.source_row <= 0:
            raise ValueError("source_row debe ser mayor que cero")

        normalized: dict[str, FieldCell] = {}
        for name, cell in self.fields.items():
            key = str(name).strip().upper()
            if not key:
                raise ValueError("Los campos deben tener nombre")
            normalized[key] = cell if isinstance(cell, FieldCell) else FieldCell(cell)
        object.__setattr__(self, "fields", MappingProxyType(normalized))

    def cell(self, name: str) -> FieldCell:
        return self.fields.get(name.strip().upper(), FieldCell(kind=CellKind.BLANK))

    def text(self, name: str) -> str:
        cell = self.cell(name)
        if cell.kind != CellKind.VALUE:
            return ""
        value = cell.raw if cell.raw is not None else cell.value
        if value is None:
            return ""
        if isinstance(value, float) and not isfinite(value):
            return ""
        if isinstance(value, Decimal) and not value.is_finite():
            return ""
        text = str(value).strip()
        if text.casefold() in {
            "nan",
            "+nan",
            "-nan",
            "inf",
            "+inf",
            "-inf",
            "infinity",
            "+infinity",
            "-infinity",
        }:
            return ""
        return text

    def decimal(self, name: str) -> Decimal | None:
        value = self.cell(name).value
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        if isinstance(value, bool):
            return None
        try:
            result = value if isinstance(value, Decimal) else Decimal(str(value).strip())
            return result if result.is_finite() else None
        except (ValueError, TypeError, ArithmeticError):
            return None


@dataclass(frozen=True, slots=True)
class DatasetInput:
    dataset_id: str
    batch_id: str
    role: DatasetRole
    period: date | None
    schema_name: str
    original_headers: tuple[str, ...]
    records: tuple[RecordInput, ...]
    profile_id: str | None = None
    sha256: str | None = None
    parent_dataset_id: str | None = None
    selected_occurrences: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.dataset_id.strip() or not self.batch_id.strip():
            raise ValueError("dataset_id y batch_id son obligatorios")
        if not isinstance(self.role, DatasetRole):
            object.__setattr__(self, "role", DatasetRole(self.role))
        object.__setattr__(self, "original_headers", tuple(self.original_headers))
        object.__setattr__(self, "records", tuple(self.records))
        if any(record.dataset_id != self.dataset_id for record in self.records):
            raise ValueError("Todos los registros deben pertenecer al dataset")
        record_ids = [record.record_id for record in self.records]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("record_id debe ser único dentro del dataset")
        source_rows = [record.source_row for record in self.records]
        if len(source_rows) != len(set(source_rows)):
            raise ValueError("source_row debe ser único dentro del dataset")
        selected = {
            str(name).strip().upper(): int(occurrence)
            for name, occurrence in self.selected_occurrences.items()
        }
        if any(not name or occurrence <= 0 for name, occurrence in selected.items()):
            raise ValueError("Las apariciones aplicadas deben tener nombre y ser positivas")
        object.__setattr__(self, "selected_occurrences", MappingProxyType(selected))


@dataclass(frozen=True, slots=True)
class SourceProfile:
    profile_id: str
    schema_name: str
    selected_occurrences: Mapping[str, int]
    period: date | None = None

    def __post_init__(self) -> None:
        normalized = {
            str(name).strip().upper(): int(occurrence)
            for name, occurrence in self.selected_occurrences.items()
        }
        if any(value <= 0 for value in normalized.values()):
            raise ValueError("Las apariciones seleccionadas deben ser positivas")
        object.__setattr__(self, "selected_occurrences", MappingProxyType(normalized))


@dataclass(frozen=True, slots=True)
class PaymentClaim:
    record: RecordInput
    requested_status: str
    requested_by: str
    evidence_id: str | None = None
    authorized_source: bool = False
    approved_by: str | None = None
    approved_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ValidationInput:
    current: DatasetInput
    reference: DatasetInput | None = None
    consolidated: DatasetInput | None = None
    catalog: DatasetInput | None = None
    orders: DatasetInput | None = None
    payment_claims: tuple[PaymentClaim, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "payment_claims", tuple(self.payment_claims))
        datasets = tuple(
            dataset
            for dataset in (
                self.current,
                self.reference,
                self.consolidated,
                self.catalog,
                self.orders,
            )
            if dataset is not None
        )
        expected_roles = (
            ("current", self.current, DatasetRole.CURRENT),
            ("reference", self.reference, DatasetRole.REFERENCE),
            ("consolidated", self.consolidated, DatasetRole.CONSOLIDATED),
            ("catalog", self.catalog, DatasetRole.CATALOG),
            ("orders", self.orders, DatasetRole.ORDERS),
        )
        for slot, dataset, expected_role in expected_roles:
            if dataset is not None and dataset.role != expected_role:
                raise ValueError(
                    f"El dataset {slot} debe tener el rol {expected_role.value}"
                )
        dataset_ids = [dataset.dataset_id for dataset in datasets]
        if len(dataset_ids) != len(set(dataset_ids)):
            raise ValueError("dataset_id debe ser único dentro de la validación")
        if self.reference is not None:
            if self.reference.schema_name != self.current.schema_name:
                raise ValueError(
                    "La cartera actual y la referencia deben usar el mismo esquema"
                )
            if self.current.period is None or self.reference.period is None:
                raise ValueError(
                    "La cartera actual y la referencia deben declarar su periodo"
                )
            if self.reference.period >= self.current.period:
                raise ValueError(
                    "El periodo de referencia debe ser anterior al periodo actual"
                )
        if self.consolidated is not None:
            if self.consolidated.parent_dataset_id != self.current.dataset_id:
                raise ValueError(
                    "El consolidado debe declarar como padre al dataset actual"
                )
        if self.orders is not None:
            expected_parent = (
                self.consolidated.dataset_id
                if self.consolidated is not None
                else self.current.dataset_id
            )
            if self.orders.parent_dataset_id != expected_parent:
                raise ValueError(
                    "Las órdenes deben declarar el dataset de origen correcto"
                )
        current_records = {
            (record.dataset_id, record.record_id): record
            for record in self.current.records
        }
        if any(
            current_records.get((claim.record.dataset_id, claim.record.record_id))
            != claim.record
            for claim in self.payment_claims
        ):
            raise ValueError(
                "Toda solicitud de pago debe referir a un registro de la cartera actual"
            )


@dataclass(frozen=True, slots=True)
class SubjectRef:
    dataset_id: str
    batch_id: str
    record_id: str
    source_row: int
    period: date | None
    clave: str = ""
    ciu: str = ""
    cedula_ruc: str = ""
    nombres: str = ""

    @classmethod
    def from_record(cls, record: RecordInput, dataset: DatasetInput) -> "SubjectRef":
        return cls(
            dataset_id=dataset.dataset_id,
            batch_id=dataset.batch_id,
            record_id=record.record_id,
            source_row=record.source_row,
            period=dataset.period,
            clave=record.text("CLAVE"),
            ciu=record.text("CIU"),
            cedula_ruc=record.text("CEDULA_RUC") or record.text("CEDULA"),
            nombres=record.text("NOMBRES"),
        )

    def identity_payload(self) -> dict[str, JsonValue]:
        return {
            "dataset_id": self.dataset_id,
            "record_id": self.record_id,
            "source_row": self.source_row,
        }


@dataclass(frozen=True, slots=True)
class RuleResult:
    rule_code: RuleCode
    severity: Severity
    blocking: bool
    requires_review: bool
    subject: SubjectRef | None
    related: tuple[SubjectRef, ...] = ()
    field_name: str | None = None
    message: str = ""
    evidence: Mapping[str, Any] = field(default_factory=dict)
    engine_version: str = ENGINE_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.rule_code, RuleCode):
            object.__setattr__(self, "rule_code", RuleCode(self.rule_code))
        if not isinstance(self.severity, Severity):
            object.__setattr__(self, "severity", Severity(self.severity))
        object.__setattr__(self, "related", tuple(self.related))
        object.__setattr__(self, "evidence", _immutable_mapping(self.evidence))

    @property
    def fingerprint(self) -> str:
        payload = {
            "engine_version": self.engine_version,
            "rule_code": self.rule_code.value,
            "severity": self.severity.value,
            "blocking": self.blocking,
            "requires_review": self.requires_review,
            "subject": self.subject.identity_payload() if self.subject else None,
            "related": sorted(
                (item.identity_payload() for item in self.related),
                key=lambda item: canonical_json(item),
            ),
            "field_name": self.field_name,
            "evidence": self.evidence,
        }
        return sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ValidationReport:
    engine_version: str
    current_dataset_id: str
    reference_dataset_id: str | None
    issues: tuple[RuleResult, ...]
    executed_rules: tuple[RuleCode, ...]
    skipped_rules: Mapping[RuleCode, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "issues", tuple(self.issues))
        object.__setattr__(self, "executed_rules", tuple(self.executed_rules))
        normalized_skipped = {
            (key if isinstance(key, RuleCode) else RuleCode(key)): str(reason)
            for key, reason in self.skipped_rules.items()
        }
        object.__setattr__(self, "skipped_rules", MappingProxyType(normalized_skipped))

    @property
    def blocking_count(self) -> int:
        return sum(issue.blocking for issue in self.issues)

    def issues_for(self, code: RuleCode) -> tuple[RuleResult, ...]:
        return tuple(issue for issue in self.issues if issue.rule_code == code)


def deduplicate_results(results: Iterable[RuleResult]) -> tuple[RuleResult, ...]:
    unique: dict[str, RuleResult] = {}
    for result in results:
        unique.setdefault(result.fingerprint, result)
    return tuple(unique.values())

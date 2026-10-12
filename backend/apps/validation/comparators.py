"""Comparaciones deterministas entre registros y periodos.

Las funciones de este módulo devuelven hechos estructurados. No escriben en la
base, no deciden aprobaciones y no interpretan la ausencia como pago.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from hashlib import sha256
from typing import Iterable, Mapping
import unicodedata

from .contracts import DatasetInput, RecordInput, canonical_json


DEFAULT_AMOUNT_FIELDS = (
    "TOTAL_EMISION",
    "TOTAL_INTERES",
    "TOTAL_COACTIVA",
    "TOTAL_RECARGO",
    "VALOR_TOTAL",
    "TOTAL",
)


def normalized_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().upper()
    text = unicodedata.normalize("NFD", text)
    return "".join(char for char in text if unicodedata.category(char) != "Mn")


def field_text(record: RecordInput, field_name: str) -> str:
    return record.text(field_name)


def canonical_key(
    record: RecordInput,
    fields: tuple[str, ...],
) -> tuple[str, ...] | None:
    values = tuple(normalized_text(field_text(record, field)) for field in fields)
    return values if all(values) else None


def group_by_key(
    records: Iterable[RecordInput],
    fields: tuple[str, ...],
) -> Mapping[tuple[str, ...], tuple[RecordInput, ...]]:
    grouped: dict[tuple[str, ...], list[RecordInput]] = defaultdict(list)
    for record in records:
        key = canonical_key(record, fields)
        if key is not None:
            grouped[key].append(record)
    return {
        key: tuple(sorted(items, key=lambda item: (item.source_row, item.record_id)))
        for key, items in sorted(grouped.items())
    }


def exact_row_fingerprint(
    record: RecordInput,
    fields: tuple[str, ...] | None = None,
) -> str:
    selected = fields or tuple(sorted(record.fields))
    payload = {
        field: {
            "value": record.cell(field).value,
            "raw": record.cell(field).raw,
            "kind": record.cell(field).kind.value,
        }
        for field in selected
    }
    return sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def exact_duplicate_groups(
    records: Iterable[RecordInput],
    fields: tuple[str, ...] | None = None,
) -> tuple[tuple[RecordInput, ...], ...]:
    grouped: dict[str, list[RecordInput]] = defaultdict(list)
    for record in records:
        grouped[exact_row_fingerprint(record, fields)].append(record)
    duplicates = [
        tuple(sorted(items, key=lambda item: (item.source_row, item.record_id)))
        for items in grouped.values()
        if len(items) > 1
    ]
    return tuple(sorted(duplicates, key=lambda group: (group[0].source_row, group[0].record_id)))


@dataclass(frozen=True, slots=True)
class FieldChange:
    field_name: str
    previous: object
    current: object


@dataclass(frozen=True, slots=True)
class RecordComparison:
    current: RecordInput
    reference: RecordInput
    changes: tuple[FieldChange, ...]


@dataclass(frozen=True, slots=True)
class AmbiguousKey:
    key: tuple[str, ...]
    current: tuple[RecordInput, ...]
    reference: tuple[RecordInput, ...]


@dataclass(frozen=True, slots=True)
class MonthlyComparison:
    new_records: tuple[RecordInput, ...]
    missing_records: tuple[RecordInput, ...]
    matched: tuple[RecordComparison, ...]
    identity_changes: tuple[RecordComparison, ...]
    amount_changes: tuple[RecordComparison, ...]
    ambiguous: tuple[AmbiguousKey, ...]


def _decimal(record: RecordInput, field_name: str) -> Decimal | None:
    return record.decimal(field_name)


def _validated_tolerance(value: Decimal) -> Decimal:
    try:
        tolerance = value if isinstance(value, Decimal) else Decimal(str(value))
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise ValueError("La tolerancia monetaria debe ser un decimal finito") from exc
    if not tolerance.is_finite() or tolerance < 0:
        raise ValueError("La tolerancia monetaria debe ser finita y no negativa")
    return tolerance


def compare_months(
    current: DatasetInput,
    reference: DatasetInput,
    *,
    key_fields: tuple[str, ...] = ("CLAVE",),
    identity_fields: tuple[str, ...] = ("CEDULA_RUC", "CIU"),
    amount_fields: tuple[str, ...] = DEFAULT_AMOUNT_FIELDS,
    tolerance: Decimal = Decimal("0.01"),
) -> MonthlyComparison:
    tolerance = _validated_tolerance(tolerance)
    if current.schema_name != reference.schema_name:
        raise ValueError("La cartera actual y la referencia deben usar el mismo esquema")
    if current.period is None or reference.period is None:
        raise ValueError("La cartera actual y la referencia deben declarar su periodo")
    if reference.period >= current.period:
        raise ValueError("El periodo de referencia debe ser anterior al periodo actual")
    current_groups = group_by_key(current.records, key_fields)
    reference_groups = group_by_key(reference.records, key_fields)

    new_records: list[RecordInput] = []
    missing_records: list[RecordInput] = []
    matched: list[RecordComparison] = []
    identity_changes: list[RecordComparison] = []
    amount_changes: list[RecordComparison] = []
    ambiguous: list[AmbiguousKey] = []

    for key in sorted(set(current_groups) | set(reference_groups)):
        current_items = current_groups.get(key, ())
        reference_items = reference_groups.get(key, ())
        if not reference_items:
            new_records.extend(current_items)
            continue
        if not current_items:
            missing_records.extend(reference_items)
            continue
        if len(current_items) != 1 or len(reference_items) != 1:
            ambiguous.append(AmbiguousKey(key, current_items, reference_items))
            continue

        current_record = current_items[0]
        reference_record = reference_items[0]
        identity_delta: list[FieldChange] = []
        amount_delta: list[FieldChange] = []

        for field in identity_fields:
            before = field_text(reference_record, field)
            after = field_text(current_record, field)
            if normalized_text(before) != normalized_text(after):
                identity_delta.append(FieldChange(field, before, after))

        for field in amount_fields:
            before = _decimal(reference_record, field)
            after = _decimal(current_record, field)
            if before is None and after is None:
                continue
            if before is None or after is None or abs(after - before) > tolerance:
                amount_delta.append(FieldChange(field, before, after))

        all_changes = tuple(identity_delta + amount_delta)
        comparison = RecordComparison(current_record, reference_record, all_changes)
        matched.append(comparison)
        if identity_delta:
            identity_changes.append(
                RecordComparison(current_record, reference_record, tuple(identity_delta))
            )
        if amount_delta:
            amount_changes.append(
                RecordComparison(current_record, reference_record, tuple(amount_delta))
            )

    sorter = lambda item: (item.source_row, item.record_id)
    return MonthlyComparison(
        new_records=tuple(sorted(new_records, key=sorter)),
        missing_records=tuple(sorted(missing_records, key=sorter)),
        matched=tuple(sorted(matched, key=lambda item: sorter(item.current))),
        identity_changes=tuple(sorted(identity_changes, key=lambda item: sorter(item.current))),
        amount_changes=tuple(sorted(amount_changes, key=lambda item: sorter(item.current))),
        ambiguous=tuple(sorted(ambiguous, key=lambda item: item.key)),
    )


class ConsolidationStatus(str, Enum):
    MATCHED = "matched"
    NO_SOURCE = "no_source"
    NO_MATCH = "no_match"
    SUMMED_NOT_ALLOWED = "summed_not_allowed"
    MISSING_CONSOLIDATED = "missing_consolidated"
    DUPLICATE_CONSOLIDATED = "duplicate_consolidated"
    AMBIGUOUS_SOURCE_MATCH = "ambiguous_source_match"
    MISSING_GROUP_KEY = "missing_group_key"


@dataclass(frozen=True, slots=True)
class ConsolidationFact:
    status: ConsolidationStatus
    key: tuple[str, ...]
    consolidated_record: RecordInput | None
    source_records: tuple[RecordInput, ...]
    matched_record: RecordInput | None = None


@dataclass(frozen=True, slots=True)
class ConsolidationComparison:
    facts: tuple[ConsolidationFact, ...]


def _mapped_amounts_match(
    source: RecordInput,
    consolidated: RecordInput,
    amount_mapping: Mapping[str, str],
    tolerance: Decimal,
) -> bool:
    for consolidated_field, source_field in amount_mapping.items():
        expected = source.decimal(source_field)
        actual = consolidated.decimal(consolidated_field)
        if expected is None or actual is None or abs(actual - expected) > tolerance:
            return False
    return True


def reconcile_consolidated(
    source: DatasetInput,
    consolidated: DatasetInput,
    *,
    group_fields: tuple[str, ...] = ("CEDULA_RUC", "CIU"),
    amount_mapping: Mapping[str, str] | None = None,
    tolerance: Decimal = Decimal("0.01"),
) -> ConsolidationComparison:
    tolerance = _validated_tolerance(tolerance)
    mapping = amount_mapping or {
        "EMISION": "TOTAL_EMISION",
        "INTERES": "TOTAL_INTERES",
        "COACTIVA": "TOTAL_COACTIVA",
        "TOTAL_RECARGO": "TOTAL_RECARGO",
    }
    source_groups = group_by_key(source.records, group_fields)
    consolidated_groups = group_by_key(consolidated.records, group_fields)
    facts: list[ConsolidationFact] = []

    for source_record in source.records:
        if canonical_key(source_record, group_fields) is None:
            facts.append(
                ConsolidationFact(
                    ConsolidationStatus.MISSING_GROUP_KEY,
                    (),
                    None,
                    (source_record,),
                )
            )
    for consolidated_record in consolidated.records:
        if canonical_key(consolidated_record, group_fields) is None:
            facts.append(
                ConsolidationFact(
                    ConsolidationStatus.MISSING_GROUP_KEY,
                    (),
                    consolidated_record,
                    (),
                )
            )

    for key in sorted(set(source_groups) | set(consolidated_groups)):
        source_items = source_groups.get(key, ())
        consolidated_items = consolidated_groups.get(key, ())
        if not consolidated_items:
            facts.append(
                ConsolidationFact(
                    ConsolidationStatus.MISSING_CONSOLIDATED,
                    key,
                    None,
                    source_items,
                )
            )
            continue
        if len(consolidated_items) > 1:
            for consolidated_record in consolidated_items:
                facts.append(
                    ConsolidationFact(
                        ConsolidationStatus.DUPLICATE_CONSOLIDATED,
                        key,
                        consolidated_record,
                        source_items,
                    )
                )
            continue
        for consolidated_record in consolidated_items:
            if not source_items:
                facts.append(
                    ConsolidationFact(
                        ConsolidationStatus.NO_SOURCE,
                        key,
                        consolidated_record,
                        (),
                    )
                )
                continue

            matches = tuple(
                source_record
                for source_record in source_items
                if _mapped_amounts_match(
                    source_record, consolidated_record, mapping, tolerance
                )
            )
            if len(matches) == 1:
                facts.append(
                    ConsolidationFact(
                        ConsolidationStatus.MATCHED,
                        key,
                        consolidated_record,
                        source_items,
                        matches[0],
                    )
                )
                continue
            if len(matches) > 1:
                facts.append(
                    ConsolidationFact(
                        ConsolidationStatus.AMBIGUOUS_SOURCE_MATCH,
                        key,
                        consolidated_record,
                        source_items,
                    )
                )
                continue

            summed = len(source_items) > 1
            if summed:
                for consolidated_field, source_field in mapping.items():
                    actual = consolidated_record.decimal(consolidated_field)
                    values = [item.decimal(source_field) for item in source_items]
                    if actual is None or any(value is None for value in values):
                        summed = False
                        break
                    if abs(actual - sum(values, Decimal("0"))) > tolerance:
                        summed = False
                        break

            facts.append(
                ConsolidationFact(
                    ConsolidationStatus.SUMMED_NOT_ALLOWED if summed else ConsolidationStatus.NO_MATCH,
                    key,
                    consolidated_record,
                    source_items,
                )
            )

    return ConsolidationComparison(tuple(facts))


@dataclass(frozen=True, slots=True)
class TraceabilityFact:
    order: RecordInput
    sources: tuple[RecordInput, ...]


@dataclass(frozen=True, slots=True)
class OrderTraceability:
    matched: tuple[TraceabilityFact, ...]
    missing: tuple[TraceabilityFact, ...]
    ambiguous: tuple[TraceabilityFact, ...]


def compare_order_traceability(
    orders: DatasetInput,
    source: DatasetInput,
    *,
    key_fields: tuple[str, ...] = ("CLAVE", "CEDULA_RUC", "CIU"),
) -> OrderTraceability:
    source_groups = group_by_key(source.records, key_fields)
    matched: list[TraceabilityFact] = []
    missing: list[TraceabilityFact] = []
    ambiguous: list[TraceabilityFact] = []

    for order in sorted(orders.records, key=lambda item: (item.source_row, item.record_id)):
        key = canonical_key(order, key_fields)
        sources = source_groups.get(key, ()) if key else ()
        fact = TraceabilityFact(order, sources)
        if not sources:
            missing.append(fact)
        elif len(sources) > 1:
            ambiguous.append(fact)
        else:
            matched.append(fact)

    return OrderTraceability(tuple(matched), tuple(missing), tuple(ambiguous))

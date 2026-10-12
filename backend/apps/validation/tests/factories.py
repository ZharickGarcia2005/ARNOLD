"""Fábricas con datos ficticios para las pruebas del motor financiero."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from apps.validation.contracts import (
    CellKind,
    DatasetInput,
    DatasetRole,
    FieldCell,
    RecordInput,
)


MONTHLY_HEADERS = (
    "CIU",
    "CEDULA_RUC",
    "NOMBRES",
    "CLAVE",
    "DIRECCION",
    "PARROQUIA",
    "TELEF",
    "CORREO",
    "TOTAL_EMISION",
    "TOTAL_INTERES",
    "TOTAL_COACTIVA",
    "TOTAL_RECARGO",
    "MESES_DEUDA",
)

AMOUNT_FIELDS = (
    "TOTAL_EMISION",
    "TOTAL_INTERES",
    "TOTAL_COACTIVA",
    "TOTAL_RECARGO",
)

_DEFAULT_PERIOD = object()


def cell(value=None, *, raw: str | None = None, kind: CellKind = CellKind.VALUE):
    return FieldCell(value=value, raw=raw, kind=kind)


def record(
    record_id: str,
    source_row: int,
    *,
    dataset_id: str = "actual",
    clave: str = "000123",
    ciu: str = "000987",
    cedula_ruc: str = "0912345678",
    nombres: str = "PERSONA FICTICIA",
    total_emision: Decimal | str = Decimal("100.00"),
    total_interes: Decimal | str = Decimal("10.00"),
    total_coactiva: Decimal | str = Decimal("5.00"),
    total_recargo: Decimal | str = Decimal("2.00"),
    meses_deuda: str = "3",
    extra: dict[str, object] | None = None,
) -> RecordInput:
    fields: dict[str, FieldCell] = {
        "CIU": cell(ciu),
        "CEDULA_RUC": cell(cedula_ruc),
        "NOMBRES": cell(nombres),
        "CLAVE": cell(clave),
        "DIRECCION": cell("CALLE FICTICIA 1"),
        "PARROQUIA": cell("CENTRO"),
        "TELEF": cell("0990000000"),
        "CORREO": cell("persona@example.invalid"),
        "TOTAL_EMISION": cell(total_emision),
        "TOTAL_INTERES": cell(total_interes),
        "TOTAL_COACTIVA": cell(total_coactiva),
        "TOTAL_RECARGO": cell(total_recargo),
        "MESES_DEUDA": cell(meses_deuda),
    }
    for name, value in (extra or {}).items():
        fields[name] = value if isinstance(value, FieldCell) else cell(value)
    return RecordInput(
        dataset_id=dataset_id,
        record_id=record_id,
        source_row=source_row,
        fields=fields,
    )


def dataset(
    *records: RecordInput,
    dataset_id: str = "actual",
    batch_id: str | None = None,
    role: DatasetRole = DatasetRole.CURRENT,
    period: date | None | object = _DEFAULT_PERIOD,
    headers: tuple[str, ...] = MONTHLY_HEADERS,
    profile_id: str | None = None,
    selected_occurrences: dict[str, int] | None = None,
    schema_name: str = "carteraMensual",
    parent_dataset_id: str | None = None,
) -> DatasetInput:
    if period is _DEFAULT_PERIOD:
        effective_period = (
            date(2026, 7, 1)
            if role == DatasetRole.REFERENCE
            else date(2026, 8, 1)
        )
    else:
        effective_period = period
    return DatasetInput(
        dataset_id=dataset_id,
        batch_id=batch_id or f"lote-{dataset_id}",
        role=role,
        period=effective_period,
        schema_name=schema_name,
        original_headers=headers,
        records=records,
        profile_id=profile_id,
        selected_occurrences=selected_occurrences or {},
        parent_dataset_id=parent_dataset_id,
    )

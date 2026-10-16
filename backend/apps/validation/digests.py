"""Huellas reproducibles de los insumos de una ejecución."""

from hashlib import sha256

from .contracts import ENGINE_VERSION, RuleCode, canonical_json
from .excel_adapter import ADAPTER_VERSION


def _batch_payload(batch):
    if batch is None:
        return None
    return {
        "id": str(batch.id),
        "sha256": batch.sha256,
        "content_version": batch.content_version,
        "period": batch.period.isoformat() if batch.period else None,
        "source_type": batch.source_type,
        "sheet": batch.sheet_name,
        "header_row": batch.header_row,
        "schema": batch.schema_name,
        "profile": batch.profile_id,
    }


def validation_input_digest(
    *,
    current_batch,
    reference_batch=None,
    consolidated_batch=None,
    catalog_batch=None,
    orders_batch=None,
    enabled_rules=None,
    engine_version: str = ENGINE_VERSION,
    adapter_version: str = ADAPTER_VERSION,
) -> str:
    payload = {
        "adapter_version": adapter_version,
        "engine_version": engine_version,
        "rules": [
            RuleCode(item).value
            for item in (tuple(RuleCode) if enabled_rules is None else enabled_rules)
        ],
        "current": _batch_payload(current_batch),
        "reference": _batch_payload(reference_batch),
        "consolidated": _batch_payload(consolidated_batch),
        "catalog": _batch_payload(catalog_batch),
        "orders": _batch_payload(orders_batch),
    }
    return sha256(canonical_json(payload).encode("utf-8")).hexdigest()

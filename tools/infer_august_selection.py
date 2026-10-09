"""Infer which source row feeds August's one-row-per-person/CIU output."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

from profile_validator_sources import load_tables, make_key


def number(value: str) -> Decimal | None:
    if not value:
        return None
    candidate = value.replace("$", "").replace(" ", "")
    if "," in candidate and "." in candidate:
        candidate = candidate.replace(",", "")
    elif "," in candidate:
        candidate = candidate.replace(",", ".")
    try:
        return Decimal(candidate)
    except (InvalidOperation, ValueError):
        return None


def signature(row: dict[str, str], fields: tuple[str, ...]) -> tuple[Decimal | None, ...]:
    return tuple(number(row.get(field, "")) for field in fields)


def same(a: tuple[Decimal | None, ...], b: tuple[Decimal | None, ...]) -> bool:
    return all(x is not None and y is not None and abs(x - y) <= Decimal("0.01") for x, y in zip(a, b))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("august", type=Path)
    args = parser.parse_args()
    tables = load_tables(args.august, ["SSheet 1", "SHEET-UNIFICADO"])
    source = tables["SSheet 1"]["rows"]
    target = tables["SHEET-UNIFICADO"]["rows"]

    source_groups: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    target_groups: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in source:
        key = make_key(row, ("CEDULA_RUC", "CIU"))
        if key:
            source_groups[key].append(row)
    for row in target:
        key = make_key(row, ("CEDULA_RUC", "CIU"))
        if key:
            target_groups[key].append(row)

    source_fields = ("T_EMISION", "T_INTERES", "T_COACTIVA", "T_RECARGO", "MES_DEUDA")
    original_fields = ("TOTAL_EMISION", "TOTAL_INTERES", "TOTAL_COACTIVA", "TOTAL_RECARGO", "MESES_DEUDA")
    target_fields = ("EMISION", "INTERES", "COACTIVA", "TOTAL_RECARGO", "TITULOS")
    stats: Counter[str] = Counter()

    for key in source_groups.keys() & target_groups.keys():
        if len(target_groups[key]) != 1:
            continue
        rows = source_groups[key]
        target_sig = signature(target_groups[key][0], target_fields)
        cleaned = [signature(row, source_fields) for row in rows]
        original = [signature(row, original_fields) for row in rows]
        stats["groups"] += 1
        stats["multirow_groups"] += len(rows) > 1
        if any(same(item, target_sig) for item in cleaned):
            stats["matches_any_cleaned_row"] += 1
        if any(same(item, target_sig) for item in original):
            stats["matches_any_original_row"] += 1
        if same(cleaned[0], target_sig):
            stats["matches_first_cleaned_row"] += 1
        if same(cleaned[-1], target_sig):
            stats["matches_last_cleaned_row"] += 1
        if len(rows) > 1:
            stats["multi_matches_any_cleaned_row"] += any(same(item, target_sig) for item in cleaned)
            stats["multi_matches_first_cleaned_row"] += same(cleaned[0], target_sig)
            stats["multi_matches_last_cleaned_row"] += same(cleaned[-1], target_sig)
            valid_debt = [(number(row.get("MES_DEUDA", "")), idx) for idx, row in enumerate(rows)]
            valid_debt = [(value, idx) for value, idx in valid_debt if value is not None]
            if valid_debt:
                max_idx = max(valid_debt)[1]
                min_idx = min(valid_debt)[1]
                stats["multi_matches_max_months_row"] += same(cleaned[max_idx], target_sig)
                stats["multi_matches_min_months_row"] += same(cleaned[min_idx], target_sig)
            valid_emission = [(number(row.get("T_EMISION", "")), idx) for idx, row in enumerate(rows)]
            valid_emission = [(value, idx) for value, idx in valid_emission if value is not None]
            if valid_emission:
                max_idx = max(valid_emission)[1]
                min_idx = min(valid_emission)[1]
                stats["multi_matches_max_emission_row"] += same(cleaned[max_idx], target_sig)
                stats["multi_matches_min_emission_row"] += same(cleaned[min_idx], target_sig)

    print(json.dumps(dict(stats), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

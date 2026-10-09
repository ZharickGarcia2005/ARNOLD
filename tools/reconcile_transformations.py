"""Reconcile known ARNOLD spreadsheet transformations using numeric comparisons."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from profile_validator_sources import load_tables, make_key, order_union


def decimal(value: str) -> Decimal | None:
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


def numeric_equal(left: str, right: str, tolerance: Decimal = Decimal("0.01")) -> bool:
    a, b = decimal(left), decimal(right)
    return a is not None and b is not None and abs(a - b) <= tolerance


def direct_reconcile(
    source: dict[str, Any],
    target: dict[str, Any],
    source_keys: tuple[str, ...],
    target_keys: tuple[str, ...],
    field_pairs: list[tuple[str, str]],
) -> dict[str, Any]:
    source_map: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    target_map: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in source["rows"]:
        key = make_key(row, source_keys)
        if key:
            source_map[key].append(row)
    for row in target["rows"]:
        key = make_key(row, target_keys)
        if key:
            target_map[key].append(row)
    common = {key for key in source_map.keys() & target_map.keys() if len(source_map[key]) == 1 and len(target_map[key]) == 1}
    results: dict[str, Any] = {}
    for source_field, target_field in field_pairs:
        matched = 0
        changed = 0
        unavailable = 0
        for key in common:
            left = source_map[key][0].get(source_field, "")
            right = target_map[key][0].get(target_field, "")
            if decimal(left) is None or decimal(right) is None:
                unavailable += 1
            elif numeric_equal(left, right):
                matched += 1
            else:
                changed += 1
        results[f"{source_field}->{target_field}"] = {
            "numeric_match": matched,
            "numeric_change": changed,
            "unavailable": unavailable,
        }
    return {"unique_common_keys": len(common), "fields": results}


def grouped_reconcile(
    source: dict[str, Any],
    target: dict[str, Any],
    key_fields: tuple[str, ...],
    field_pairs: list[tuple[str, str]],
) -> dict[str, Any]:
    groups: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    target_map: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in source["rows"]:
        key = make_key(row, key_fields)
        if key:
            groups[key].append(row)
    for row in target["rows"]:
        key = make_key(row, key_fields)
        if key:
            target_map[key].append(row)
    common = {key for key in groups.keys() & target_map.keys() if len(target_map[key]) == 1}
    results: dict[str, Any] = {}
    for source_field, target_field in field_pairs:
        matched = 0
        changed = 0
        unavailable = 0
        for key in common:
            numbers = [decimal(row.get(source_field, "")) for row in groups[key]]
            target_number = decimal(target_map[key][0].get(target_field, ""))
            if target_number is None or any(number is None for number in numbers):
                unavailable += 1
                continue
            source_sum = sum((number for number in numbers if number is not None), Decimal(0))
            if abs(source_sum - target_number) <= Decimal("0.01"):
                matched += 1
            else:
                changed += 1
        results[f"SUM({source_field})->{target_field}"] = {
            "numeric_match": matched,
            "numeric_change": changed,
            "unavailable": unavailable,
        }
    count_match = 0
    count_changed = 0
    count_unavailable = 0
    for key in common:
        target_number = decimal(target_map[key][0].get("TITULOS", ""))
        if target_number is None:
            count_unavailable += 1
        elif target_number == len(groups[key]):
            count_match += 1
        else:
            count_changed += 1
    results["COUNT(rows)->TITULOS"] = {
        "numeric_match": count_match,
        "numeric_change": count_changed,
        "unavailable": count_unavailable,
    }
    return {
        "common_groups": len(common),
        "source_groups_with_multiple_rows": sum(len(groups[key]) > 1 for key in common),
        "fields": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--july", type=Path, required=True)
    parser.add_argument("--august", type=Path, required=True)
    parser.add_argument("--orders", type=Path, required=True)
    args = parser.parse_args()

    july = load_tables(args.july, ["Sheet 1", "UNIF-SHEET 1"])
    august = load_tables(args.august, ["SSheet 1", "SHEET-UNIFICADO"])
    order_names = ["030-SAN CARLOS (LISTA)", "031-(24 DE MAYO) LISTA", "032-SAN CRISTOBAL(LISTA)", "033-GUAYACAN", "034-NICOLAS ALTA"]
    orders = order_union(load_tables(args.orders, order_names), order_names)

    results = {
        "july_second_amount_set_to_unified": direct_reconcile(
            july["Sheet 1"], july["UNIF-SHEET 1"],
            ("CEDULA_RUC", "CIU", "CLAVE"), ("CEDULA_RUC", "CIU", "CLAVE"),
            [
                ("TOTAL_EMISION__2", "EMISION"),
                ("TOTAL_INTERES__2", "INTERES"),
                ("TOTAL_COACTIVA__2", "COACTIVA"),
                ("TOTAL_RECARGO__2", "TOTAL_RECARGO"),
            ],
        ),
        "august_cleaned_group_to_unified": grouped_reconcile(
            august["SSheet 1"], august["SHEET-UNIFICADO"], ("CEDULA_RUC", "CIU"),
            [
                ("T_EMISION", "EMISION"),
                ("T_INTERES", "INTERES"),
                ("T_COACTIVA", "COACTIVA"),
                ("T_RECARGO", "TOTAL_RECARGO"),
            ],
        ),
        "july_unified_to_orders": direct_reconcile(
            july["UNIF-SHEET 1"], orders, ("CEDULA_RUC", "CIU"), ("CEDULA_RUC", "CIU"),
            [
                ("EMISION", "EMISION"),
                ("INTERES", "INTERES"),
                ("COACTIVA", "COACTIVA"),
                ("TOTAL_RECARGO", "COACTIVA"),
                ("VALOR_TOTAL", "VALOR_TOTAL"),
            ],
        ),
        "august_unified_to_orders": direct_reconcile(
            august["SHEET-UNIFICADO"], orders, ("CEDULA_RUC", "CIU"), ("CEDULA_RUC", "CIU"),
            [
                ("EMISION", "EMISION"),
                ("INTERES", "INTERES"),
                ("COACTIVA", "COACTIVA"),
                ("TOTAL_RECARGO", "COACTIVA"),
                ("VALOR_TOTAL", "VALOR_TOTAL"),
            ],
        ),
    }
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Privacy-safe cross-source comparison for ARNOLD's known monthly formats."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from profile_validator_sources import load_tables, make_key, order_union


def compare(
    first: dict[str, Any],
    second: dict[str, Any],
    first_keys: tuple[str, ...],
    second_keys: tuple[str, ...],
    fields: list[tuple[str, str]],
) -> dict[str, Any]:
    first_map: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    second_map: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in first["rows"]:
        key = make_key(row, first_keys)
        if key:
            first_map[key].append(row)
    for row in second["rows"]:
        key = make_key(row, second_keys)
        if key:
            second_map[key].append(row)
    common = set(first_map) & set(second_map)
    changed: dict[str, int] = {}
    for left, right in fields:
        count = 0
        for key in common:
            left_values = {row.get(left, "") for row in first_map[key]}
            right_values = {row.get(right, "") for row in second_map[key]}
            if left_values != right_values:
                count += 1
        changed[f"{left}->{right}"] = count
    return {
        "first_key": "+".join(first_keys),
        "second_key": "+".join(second_keys),
        "first_distinct": len(first_map),
        "second_distinct": len(second_map),
        "common": len(common),
        "only_first": len(set(first_map) - set(second_map)),
        "only_second": len(set(second_map) - set(first_map)),
        "common_with_multiple_first_rows": sum(len(first_map[key]) > 1 for key in common),
        "common_with_multiple_second_rows": sum(len(second_map[key]) > 1 for key in common),
        "changed_common_keys": changed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--july", type=Path, required=True)
    parser.add_argument("--august", type=Path, required=True)
    parser.add_argument("--orders", type=Path, required=True)
    args = parser.parse_args()

    july = load_tables(args.july, ["Sheet 1", "UNIF-SHEET 1", "SHEET 1-SIN COACTIVA"])
    august = load_tables(args.august, ["Sheet 1", "SSheet 1", "SHEET-UNIFICADO", "CAT ACTUALIZADO"])
    order_names = ["030-SAN CARLOS (LISTA)", "031-(24 DE MAYO) LISTA", "032-SAN CRISTOBAL(LISTA)", "033-GUAYACAN", "034-NICOLAS ALTA"]
    order_tables = load_tables(args.orders, order_names + ["INCONSISTENCIAS"])
    orders = order_union(order_tables, order_names)

    amount_same = [(field, field) for field in ("TOTAL_EMISION", "TOTAL_INTERES", "TOTAL_COACTIVA", "TOTAL_RECARGO", "MESES_DEUDA")]
    unified_same = [(field, field) for field in ("EMISION", "INTERES", "COACTIVA", "TOTAL_RECARGO", "VALOR_TOTAL", "TITULOS")]
    raw_to_unified = [
        ("TOTAL_EMISION", "EMISION"),
        ("TOTAL_INTERES", "INTERES"),
        ("TOTAL_COACTIVA", "COACTIVA"),
        ("TOTAL_RECARGO", "TOTAL_RECARGO"),
    ]
    unified_to_orders = [
        ("EMISION", "EMISION"),
        ("INTERES", "INTERES"),
        ("COACTIVA", "COACTIVA"),
        ("VALOR_TOTAL", "VALOR_TOTAL"),
    ]

    results = {
        "july_raw_to_august_raw": compare(
            july["Sheet 1"], august["Sheet 1"], ("CLAVE",), ("CLAVE",),
            [("CEDULA_RUC", "CEDULA_RUC"), ("CIU", "CIU")] + amount_same,
        ),
        "august_raw_to_cleaned": compare(
            august["Sheet 1"], august["SSheet 1"], ("CLAVE",), ("CLAVE",),
            [
                ("TOTAL_EMISION", "T_EMISION"),
                ("TOTAL_INTERES", "T_INTERES"),
                ("TOTAL_COACTIVA", "T_COACTIVA"),
                ("TOTAL_RECARGO", "T_RECARGO"),
                ("MESES_DEUDA", "MES_DEUDA"),
            ],
        ),
        "july_raw_to_unified": compare(
            july["Sheet 1"], july["UNIF-SHEET 1"],
            ("CEDULA_RUC", "CIU", "CLAVE"), ("CEDULA_RUC", "CIU", "CLAVE"), raw_to_unified,
        ),
        "august_raw_to_unified": compare(
            august["Sheet 1"], august["SHEET-UNIFICADO"],
            ("CEDULA_RUC", "CIU"), ("CEDULA_RUC", "CIU"), raw_to_unified,
        ),
        "july_to_august_unified": compare(
            july["UNIF-SHEET 1"], august["SHEET-UNIFICADO"],
            ("CEDULA_RUC", "CIU"), ("CEDULA_RUC", "CIU"), unified_same,
        ),
        "july_unified_to_orders": compare(
            july["UNIF-SHEET 1"], orders,
            ("CEDULA_RUC", "CIU"), ("CEDULA_RUC", "CIU"), unified_to_orders,
        ),
        "august_unified_to_orders": compare(
            august["SHEET-UNIFICADO"], orders,
            ("CEDULA_RUC", "CIU"), ("CEDULA_RUC", "CIU"), unified_to_orders,
        ),
        "august_catalog_to_raw": compare(
            august["CAT ACTUALIZADO"], august["Sheet 1"],
            ("RUC_CEDULA", "CLAVE_NUEV"), ("CEDULA_RUC", "CLAVE"), [],
        ),
        "july_unified_to_without_coactiva": compare(
            july["UNIF-SHEET 1"], july["SHEET 1-SIN COACTIVA"],
            ("CEDULA_RUC", "CIU"), ("CEDULA_RUC", "CIU"), unified_same,
        ),
    }
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

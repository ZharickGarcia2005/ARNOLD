"""Read-only structural and quality analysis for ARNOLD source workbooks.

The script prints aggregate metadata only. It does not emit names, identifiers,
addresses, phone numbers, email addresses, title numbers, or individual amounts.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from openpyxl import load_workbook


HEADER_WORDS = (
    "CLAVE", "CEDULA", "RUC", "IDENTIFIC", "NOMBRE", "CONTRIBUYENTE",
    "TITULO", "EXP", "VALOR", "EMISION", "INTERES", "TOTAL", "CIU",
    "CUENTA", "PREDIO", "PARROQUIA", "SECTOR", "DIRECCION", "ORDEN",
)


def norm(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text).strip().upper()
    return text


def detect_header(rows: list[list[Any]]) -> tuple[int, list[str], int]:
    best_score = -1
    best_row = 1
    best_headers: list[str] = []
    for row_num, row in enumerate(rows, start=1):
        headers = [norm(value) for value in row[:120]]
        nonempty = sum(bool(value) for value in headers)
        keyword_hits = sum(any(word in value for word in HEADER_WORDS) for value in headers if value)
        distinct = len({value for value in headers if value})
        score = keyword_hits * 20 + min(nonempty, 40) + min(distinct, 20)
        if score > best_score:
            best_score = score
            best_row = row_num
            best_headers = headers
    while best_headers and not best_headers[-1]:
        best_headers.pop()
    return best_row, best_headers, best_score


def structural_profile(path: Path) -> dict[str, Any]:
    workbook = load_workbook(path, read_only=True, data_only=False, keep_links=False)
    sheets = []
    for ws in workbook.worksheets:
        sample: list[list[Any]] = []
        row_count = 0
        column_count = 0
        for row in ws.iter_rows(values_only=True):
            values = list(row)
            row_count += 1
            column_count = max(column_count, len(values))
            if len(sample) < 40:
                sample.append(values)
        header_row, headers, score = detect_header(sample)
        sheets.append({
            "name": ws.title,
            "rows": row_count,
            "columns": column_count,
            "header_row": header_row,
            "header_score": score,
            "headers": headers,
        })
    workbook.close()
    return {
        "file": path.name,
        "size_bytes": path.stat().st_size,
        "sheets": sheets,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    output = [structural_profile(path) for path in args.paths]
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

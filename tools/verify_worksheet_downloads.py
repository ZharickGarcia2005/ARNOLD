"""Comprobación de descargas existentes, sin escribir ni modificar los Excel."""

import argparse
from decimal import Decimal
import json
from pathlib import Path
from zipfile import ZipFile

from openpyxl import load_workbook


SOURCE_HEADERS = ["CIU", "CEDULA_RUC", "NOMBRES", "CLAVE", "DIRECCION", "PARROQUIA",
                  "TELEF", "CORREO", "TOTAL_EMISION", "TOTAL_INTERES", "TOTAL_COACTIVA",
                  "TOTAL_RECARGO", "MESES_DEUDA"]
MONEY = SOURCE_HEADERS[8:12]


def inspect_download(path, scope, expected):
    with ZipFile(path) as archive:
        assert archive.testzip() is None, "Contenedor ZIP dañado"
    book = load_workbook(path, read_only=True, data_only=False)
    try:
        name = "Principal" if scope == "clean" else "Problemas"
        assert book.sheetnames == [name, "Trazabilidad"], "Conjuntos mezclados o incompletos"
        rows = book[name].iter_rows()
        header = [cell.value for cell in next(rows)]
        assert header[:len(SOURCE_HEADERS)] == SOURCE_HEADERS, "Encabezados originales alterados"
        columns = {field: header.index(field) for field in header}
        source_rows, count, numeric, formulas = set(), 0, 0, 0
        totals = dict.fromkeys(MONEY, Decimal(0))
        for row in rows:
            count += 1
            source = row[columns["FILA_ORIGEN"]].value
            assert source not in source_rows, "Fila de origen repetida en la exportación"
            source_rows.add(source)
            assert row[columns["ESTADO_REVISION"]].value == scope, "Clasificación mezclada"
            for field in ("CIU", "CEDULA_RUC", "CLAVE", "TELEF"):
                cell = row[columns[field]]
                assert cell.value is None or isinstance(cell.value, str), "Identificador convertido a número"
                assert cell.number_format == "@", "Formato de identificador perdido"
            amounts = []
            for field in MONEY:
                cell = row[columns[field]]
                assert cell.number_format == "#,##0.00", "Formato monetario perdido"
                if cell.data_type == "n" and cell.value is not None:
                    numeric += 1
                    amount = Decimal(str(cell.value)); totals[field] += amount; amounts.append(amount)
            total = row[columns["MONTO_PENDIENTE"]].value
            if len(amounts) == 4 and isinstance(total, (int, float)):
                assert sum(amounts) == Decimal(str(total)), "Total financiero inconsistente"
            formulas += sum(cell.data_type == "f" for cell in row)
        meta = dict(book["Trazabilidad"].values)
        assert count == expected == meta["Filas"], "Cantidad de registros incompleta"
        assert meta["Conjunto"] == scope and meta["Revisión"] == 2
        assert not formulas, "Contenido ejecutable en el archivo"
        return {"file": str(Path(path).resolve()), "rows": count, "original_headers": True,
                "xlsx_crc": "ok", "numeric_money_cells": numeric,
                "financial_totals": {field: str(total) for field, total in totals.items()},
                "revision": meta["Revisión"]}, source_rows
    finally:
        book.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("clean"); parser.add_argument("problems")
    args = parser.parse_args()
    clean, clean_ids = inspect_download(args.clean, "clean", 35106)
    problems, problem_ids = inspect_download(args.problems, "problem", 2936)
    assert not clean_ids.intersection(problem_ids), "Conjuntos solapados"
    assert len(clean_ids | problem_ids) == 38042, "Faltan registros importados"
    print(json.dumps({"clean": clean, "problems": problems, "disjoint": True,
                      "total": 38042}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

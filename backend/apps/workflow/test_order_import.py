"""Regresiones de importación operativa. Ningún dato de clientes en fixtures."""
from pathlib import Path
import tempfile
from unittest.mock import patch
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.batches.models import Batch
from apps.batches.services import UploadError, batch_file_path
from apps.validation.contracts import DatasetInput, DatasetRole, FieldCell, RecordInput
from .columns import SHEETS, original_payload
from .models import WorksheetEdit
from .order_import import import_order_book
from .order_projection import presentation_counts
from .sheet_exports import export_sheet
from .worksheet import values_of, save_changes


class OrderBookImportTests(TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="test-column-contract-import-", dir=Path(__file__).resolve().parent)
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        config = override_settings(DEBUG=True, ARNOLD_FILE_ROOT=self.root / "private", ARNOLD_REQUIRE_ANTIVIRUS=False,
                                   ARNOLD_DATA_ENCRYPTION_KEY="", ARNOLD_LOCAL_QUEUE=True)
        config.enable(); self.addCleanup(config.disable)
        self.actor = get_user_model().objects.create_superuser("order-tester", password="synthetic-test-only")
        self.path = self.root / "synthetic-original.xlsx"
        # No libro escrito/recalculado: se sustituye sólo la lectura de Excel.
        # El servicio real de cifrado, motor, Worksheet, API y auditoría sí corre.
        self.path.write_bytes(b"synthetic-original-byte-evidence")
        self.archives = patch("apps.workflow.order_import.inspect_xlsx_archive")
        self.archives.start(); self.addCleanup(self.archives.stop)
        self.reader = patch("apps.workflow.order_import.read_order_book", side_effect=self.dataset)
        self.reader.start(); self.addCleanup(self.reader.stop)

    def dataset(self, _path, batch_id):
        headers = ("PREDIO MUNICIPAL", "CONTRIBUYENTE", "CEDULA", "CLAVE", "CIU", "EMISION", "INTERES", "RECARGO", "TOTAL", "TITULO", "TITULOS")
        rows, origins, counts = [], {}, {}
        for number, (code, template) in enumerate(SHEETS.items(), 1):
            fields = {key: FieldCell(value=value, raw=value) for key, value in {
                "PREDIO_MUN": f"000{number}", "NOMBRES": "PERSONA SINTETICA", "CEDULA_RUC": "1710034065",
                "CLAVE": f"KEY-{number}", "CIU": "00042", "EMISION": "10.00", "INTERES": "2.00",
                "RECARGO": "1.00", "TOTAL": "13.00", "TITULO": "0007", "TITULOS": "8"}.items()}
            record_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{batch_id}:{code}"))
            rows.append(RecordInput(str(batch_id), record_id, number, fields))
            origins[record_id] = {"sheet": template["name"], "excel_row": 2, "order": code if code != "issues" else "", "headers": list(headers)}
            counts[template["name"]] = 1
        return (DatasetInput(str(batch_id), str(batch_id), DatasetRole.CURRENT, None, "ordenPreliminar", headers, tuple(rows)),
                origins, {"rows": 12, "sheets": counts, "ignored_sheets": ["COACTIVA"], "formula_cells": 0, "error_cells": 0})

    def test_all_orders_keep_source_and_no_invented_months_or_coactiva(self):
        batch, result = import_order_book(self.path, actor=self.actor)
        self.assertEqual(result["rows"], 12)
        self.assertIsNone(batch.period)
        self.assertEqual(presentation_counts(batch.worksheet), {**dict.fromkeys(list(SHEETS)[:-1], 1), "issues": 1})
        self.assertEqual(batch_file_path(batch).read_bytes(), self.path.read_bytes())
        for row in batch.worksheet.rows.select_related("record"):
            origin = original_payload(row)["origin"]
            self.assertEqual(origin["excel_row"], 2)
            values = values_of(row)
            self.assertEqual((values["TITULO"], values["TITULOS"]), ("0007", "8"))
            self.assertEqual((values["MESES_DEUDA"], values["TOTAL_COACTIVA"]), ("", ""))
            self.assertNotIn("MONTHS", [error["code"] for error in row.errors])
        from openpyxl import load_workbook
        import json
        for scope, expected in (("clean", 11), ("problem", 1)):
            stream, _ = export_sheet(batch, self.actor, scope, expected_revision=1)
            try:
                book = load_workbook(stream, read_only=True, data_only=False)
                try:
                    trace = dict(book["Trazabilidad"].values)
                    self.assertEqual(trace["Filas"], expected)
                    records = [json.loads(value) for key, value in trace.items() if str(key).startswith("Record ")]
                    self.assertTrue(all(record["source_origin"]["excel_row"] == 2 for record in records))
                    self.assertTrue(all(record["source_origin"]["sheet"] in [s["name"] for s in SHEETS.values()] for record in records))
                finally: book.close()
            finally: stream.close()
        again, _ = import_order_book(self.path, actor=self.actor)
        self.assertEqual(again.pk, batch.pk)
        self.assertEqual(Batch.objects.count(), 1)

    def test_no_writes_in_preflight_and_rollback_on_validation_failure(self):
        batch, result = import_order_book(self.path, actor=self.actor, dry_run=True)
        self.assertIsNone(batch); self.assertEqual(result["rows"], 12)
        self.assertEqual(Batch.objects.count(), 0)
        with patch("apps.workflow.order_import._persist_report", side_effect=RuntimeError("synthetic failure")):
            with self.assertRaises(RuntimeError): import_order_book(self.path, actor=self.actor)
        self.assertEqual(Batch.objects.count(), 0)
        self.assertFalse(list((self.root / "private" / "quarantine").glob("*.xlsx")))
        self.assertEqual(self.path.read_bytes(), b"synthetic-original-byte-evidence")

    def test_permission_and_reediting_preserve_schema_and_origin(self):
        denied = get_user_model().objects.create_user("without-import", area="Other")
        with self.assertRaises(UploadError): import_order_book(self.path, actor=denied)
        batch, _ = import_order_book(self.path, actor=self.actor)
        row = batch.worksheet.rows.select_related("record").order_by("record__source_row").first()
        original = bytes(row.record.data_ciphertext)
        save_changes(batch, self.actor, [{"id": str(row.pk), "version": 1, "values": {"NOMBRES": "NOMBRE CONFIRMADO"}}], "Prueba de edición sintética")
        row.refresh_from_db(); self.assertEqual(row.quality, "clean")
        row.record.refresh_from_db(); self.assertEqual(bytes(row.record.data_ciphertext), original)
        self.assertEqual(WorksheetEdit.objects.count(), 1)

    def test_formulas_errors_and_cross_sheet_duplicates_are_not_approved(self):
        from dataclasses import replace
        from apps.validation.contracts import CellKind
        def with_problems(path, batch_id):
            dataset, origins, stats = self.dataset(path, batch_id)
            rows = list(dataset.records)
            for position in (0, 1):
                rows[position] = replace(rows[position], fields={**rows[position].fields, "CLAVE": FieldCell("REPETIDA")})
            rows[2] = replace(rows[2], fields={**rows[2].fields, "TOTAL": FieldCell("=1+1", "=1+1", CellKind.FORMULA)})
            rows[3] = replace(rows[3], fields={**rows[3].fields, "NOVEDAD": FieldCell("#N/A", "#N/A", CellKind.ERROR)})
            return replace(dataset, records=tuple(rows)), origins, stats
        with patch("apps.workflow.order_import.read_order_book", side_effect=with_problems):
            batch, _ = import_order_book(self.path, actor=self.actor)
        self.assertEqual(presentation_counts(batch.worksheet)["issues"], 5)
        self.assertEqual(batch.worksheet.rows.filter(duplicate=True).count(), 2)
        self.assertTrue(batch.validation_runs.get().issues.filter(rule_code="FORMULA-001").exists())
        self.assertEqual(values_of(batch.worksheet.rows.get(record__source_row=3))["SOURCE_TOTAL"], "=1+1")

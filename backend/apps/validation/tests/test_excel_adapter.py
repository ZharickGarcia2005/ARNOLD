"""Pruebas del adaptador Excel con libros sintéticos.

No se usan carteras reales: cada caso crea un ``.xlsx`` mínimo en un
directorio temporal y comprueba el contrato que consume el motor financiero.
"""

from datetime import date
from io import BytesIO
import zipfile

from django.test import SimpleTestCase
from openpyxl import Workbook

from apps.validation.contracts import CellKind, DatasetRole
from apps.validation.excel_adapter import ExcelAdapterError, inspect_xlsx_archive, parse_xlsx


MONTHLY_HEADERS = (
    "CIU",
    "CEDULA_RUC",
    "NOMBRES",
    "CLAVE",
    "TOTAL_EMISION",
    "TOTAL_INTERES",
    "TOTAL_COACTIVA",
    "TOTAL_RECARGO",
    "MESES_DEUDA",
)


class ExcelAdapterTests(SimpleTestCase):
    databases = []

    def _workbook(self, headers, values, *, configure_cells=None) -> BytesIO:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Cartera"
        sheet.append(list(headers))
        sheet.append(list(values))
        if configure_cells is not None:
            configure_cells(sheet)

        stream = BytesIO()
        workbook.save(stream)
        workbook.close()
        stream.seek(0)
        return stream

    def _parse(self, source: BytesIO, **overrides):
        arguments = {
            "batch_id": "00000000-0000-0000-0000-000000000001",
            "role": DatasetRole.CURRENT,
            "period": date(2026, 8, 1),
            "schema_name": "carteraMensual",
            "sheet_name": "Cartera",
            "header_row": 1,
        }
        arguments.update(overrides)
        return parse_xlsx(source, **arguments)

    def test_maps_t_recargo_alias_and_keeps_original_header(self):
        headers = tuple(
            "T_RECARGO" if header == "TOTAL_RECARGO" else header
            for header in MONTHLY_HEADERS
        )
        source = self._workbook(
            headers,
            ("000042", "0123456789", "Persona sintética", "000123", 10, 2, 3, 4, 1),
        )

        dataset = self._parse(source)
        record = dataset.records[0]

        self.assertIn("T_RECARGO", dataset.original_headers)
        self.assertEqual(record.cell("TOTAL_RECARGO").value, 4)
        self.assertEqual(record.cell("TOTAL_RECARGO").raw, "4")

    def test_keeps_duplicate_columns_and_applies_explicit_occurrence_profile(self):
        headers = MONTHLY_HEADERS + (
            "TOTAL_EMISION",
            "TOTAL_INTERES",
            "TOTAL_COACTIVA",
            "TOTAL_RECARGO",
        )
        values = (
            "000042",
            "0123456789",
            "Persona sintética",
            "000123",
            10,
            2,
            3,
            4,
            1,
            100,
            20,
            30,
            40,
        )
        source = self._workbook(headers, values)

        dataset = self._parse(source, profile_id="julio_2026_confirmado", period=date(2026, 7, 1))
        record = dataset.records[0]

        self.assertEqual(dataset.original_headers.count("TOTAL_EMISION"), 2)
        self.assertEqual(dataset.selected_occurrences["TOTAL_EMISION"], 2)
        self.assertEqual(record.cell("TOTAL_EMISION__1").value, 10)
        self.assertEqual(record.cell("TOTAL_EMISION__2").value, 100)
        self.assertEqual(record.cell("TOTAL_EMISION").value, 100)

    def test_preserves_formula_and_excel_error_as_non_value_cells(self):
        values = (
            "000042",
            "0123456789",
            "Persona sintética",
            "000123",
            "=1+2",
            "#DIV/0!",
            3,
            4,
            1,
        )
        source = self._workbook(MONTHLY_HEADERS, values)

        record = self._parse(source).records[0]

        self.assertEqual(record.cell("TOTAL_EMISION").kind, CellKind.FORMULA)
        self.assertEqual(record.cell("TOTAL_EMISION").raw, "=1+2")
        self.assertEqual(record.cell("TOTAL_INTERES").kind, CellKind.ERROR)
        self.assertEqual(record.cell("TOTAL_INTERES").raw, "#DIV/0!")

    def test_interprets_identifier_number_formats_without_losing_leading_zeroes(self):
        def configure_identifiers(sheet):
            sheet["A2"] = 42
            sheet["A2"].number_format = "000000"
            sheet["B2"] = 123456789
            sheet["B2"].number_format = "0000000000"
            sheet["D2"] = 123
            sheet["D2"].number_format = "000000"

        source = self._workbook(
            MONTHLY_HEADERS,
            (42, 123456789, "Persona sintética", 123, 10, 2, 3, 4, 1),
            configure_cells=configure_identifiers,
        )

        record = self._parse(source).records[0]

        self.assertEqual(record.text("CIU"), "000042")
        self.assertEqual(record.text("CEDULA_RUC"), "0123456789")
        self.assertEqual(record.text("CLAVE"), "000123")

    def test_integral_float_identifier_does_not_gain_decimal_suffix(self):
        def configure_identifiers(sheet):
            sheet["A2"] = 42.0
            sheet["B2"] = 123456789.0
            sheet["D2"] = 123.0

        source = self._workbook(
            MONTHLY_HEADERS,
            (42.0, 123456789.0, "Persona sintética", 123.0, 10, 2, 3, 4, 1),
            configure_cells=configure_identifiers,
        )

        record = self._parse(source).records[0]

        self.assertEqual(record.text("CIU"), "42")
        self.assertEqual(record.text("CEDULA_RUC"), "123456789")
        self.assertEqual(record.text("CLAVE"), "123")

    def test_recargo_alias_is_contextual_and_preserves_order_schema(self):
        headers = (
            "PREDIO_MUN", "NOMBRES", "CEDULA_RUC", "CLAVE", "CIU",
            "EMISION", "INTERES", "RECARGO", "TOTAL",
        )
        source = self._workbook(
            headers,
            ("P-1", "Persona sintética", "0123456789", "000123", "000042", 10, 2, 3, 15),
        )

        dataset = self._parse(source, schema_name="ordenPreliminar")
        record = dataset.records[0]

        self.assertEqual(record.cell("RECARGO").value, 3)
        self.assertNotIn("TOTAL_RECARGO", record.fields)

    def test_archive_preflight_rejects_active_content_case_insensitively(self):
        source = self._workbook(
            MONTHLY_HEADERS,
            ("000042", "0123456789", "Persona sintética", "000123", 10, 2, 3, 4, 1),
        )
        unsafe = BytesIO()
        with zipfile.ZipFile(source) as original, zipfile.ZipFile(unsafe, "w") as rebuilt:
            for item in original.infolist():
                rebuilt.writestr(item, original.read(item))
            rebuilt.writestr("xl/ActiveX/control.bin", b"contenido activo")
        unsafe.seek(0)

        with self.assertRaisesRegex(ExcelAdapterError, "macros"):
            inspect_xlsx_archive(unsafe)

    def test_rejects_a_sheet_that_only_contains_headers(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Cartera"
        sheet.append(list(MONTHLY_HEADERS))
        source = BytesIO()
        workbook.save(source)
        workbook.close()
        source.seek(0)

        with self.assertRaisesRegex(ExcelAdapterError, "no contiene registros"):
            self._parse(source)

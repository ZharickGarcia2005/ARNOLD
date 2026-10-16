"""Prueba vertical: archivo en cuarentena → registros → motor → resultado."""

from datetime import date, timedelta
import base64
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from openpyxl import Workbook

from apps.batches.models import Batch, Record
from apps.batches.services import receive_xlsx
from apps.validation.models import ValidationIssue, ValidationRun
from apps.validation.services import _parse_and_store
from apps.validation.contracts import DatasetRole
from apps.validation.tasks import _claim, validate_batch


class ValidationPipelineTests(TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temporary_directory.cleanup)
        self.settings_override = override_settings(
            ARNOLD_LOCAL_QUEUE=False,
            ARNOLD_FILE_ROOT=Path(self.temporary_directory.name),
            ARNOLD_REQUIRE_ANTIVIRUS=False,
            ARNOLD_DATA_ENCRYPTION_KEY=base64.b64encode(b"d" * 32).decode("ascii"),
            ARNOLD_HMAC_KEY="h" * 32,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.user = get_user_model().objects.create_user(
            username="pipeline-sintetico",
            password="una-clave-de-prueba-segura",
            area="Pruebas",
        )

    @staticmethod
    def _file(rows=None) -> SimpleUploadedFile:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Cartera"
        sheet.append([
            "CIU", "CEDULA_RUC", "NOMBRES", "CLAVE", "TOTAL_EMISION",
            "TOTAL_INTERES", "TOTAL_COACTIVA", "TOTAL_RECARGO", "MESES_DEUDA",
        ])
        for row in rows or [
            ["000042", "0123456789", "Persona sintética", "000123", 10, 2, 3, 4, 1]
        ]:
            sheet.append(row)
        stream = BytesIO()
        workbook.save(stream)
        workbook.close()
        return SimpleUploadedFile(
            "cartera-sintetica.xlsx",
            stream.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_pipeline_persists_encrypted_records_and_is_idempotent(self):
        with patch.object(validate_batch, "delay"):
            received = receive_xlsx(
                self._file(),
                uploaded_by=self.user,
                source_type="cartera_mensual",
                period=date(2026, 8, 1),
                sheet_name="Cartera",
                header_row=1,
                schema_name="carteraMensual",
            )

        first = validate_batch.run(str(received.run.id))
        second = validate_batch.run(str(received.run.id))
        received.batch.refresh_from_db()
        received.run.refresh_from_db()

        self.assertEqual(first["status"], ValidationRun.Status.SUCCEEDED, received.run.error_message)
        self.assertTrue(second["idempotent"])
        record = Record.objects.get(batch=received.batch)
        self.assertEqual(received.batch.status, Batch.Status.READY)
        self.assertEqual(received.batch.row_count, 1)
        self.assertEqual(received.run.status, ValidationRun.Status.SUCCEEDED)
        self.assertEqual(ValidationIssue.objects.filter(run=received.run).count(), 0)
        self.assertNotIn(b"000123", bytes(record.data_ciphertext))
        self.assertEqual(len(record.clave_hmac), 64)

    def test_real_records_api_is_paginated_and_scoped_to_the_user_area(self):
        with patch.object(validate_batch, "delay"):
            received = receive_xlsx(
                self._file(), uploaded_by=self.user, source_type="cartera_mensual",
                period=date(2026, 8, 1), sheet_name="Cartera", header_row=1,
                schema_name="carteraMensual",
            )
        self.user.user_permissions.add(Permission.objects.get(codename="view_batch"))
        self.client.force_login(self.user)
        url = f"/api/v1/batches/{received.batch.id}/records/"
        self.assertEqual(self.client.get(url).json()["records"], [])
        validate_batch.run(str(received.run.id))
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(response.json()["records"][0]["clave"], "000123")
        self.assertEqual(response.json()["records"][0]["amount"], "19")
        self.assertEqual(len(self.client.get("/api/v1/batches/").json()["batches"]), 1)
        self.user.area = "Otra área"
        self.user.save(update_fields=("area",))
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/batches/").json()["batches"], [])

    @override_settings(DEBUG=True, ARNOLD_LOCAL_QUEUE=True)
    def test_local_worker_processes_committed_queue_without_redis(self):
        with self.captureOnCommitCallbacks(execute=True):
            received = receive_xlsx(
                self._file(), uploaded_by=self.user, source_type="cartera_mensual",
                period=date(2026, 8, 1), sheet_name="Cartera", header_row=1,
                schema_name="carteraMensual",
            )
        call_command("process_pending")
        received.run.refresh_from_db()
        self.assertEqual(received.run.status, ValidationRun.Status.SUCCEEDED)

    def test_pipeline_encrypts_and_deduplicates_validation_issues(self):
        rows = [
            ["000042", "0123456789", "Persona A", "000123", 10, 2, 3, 4, 1],
            ["000043", "0123456790", "Persona B", "000123", 11, 2, 3, 4, 1],
        ]
        with patch.object(validate_batch, "delay"):
            received = receive_xlsx(
                self._file(rows),
                uploaded_by=self.user,
                source_type="cartera_mensual",
                period=date(2026, 8, 1),
                sheet_name="Cartera",
                header_row=1,
                schema_name="carteraMensual",
            )

        first = validate_batch.run(str(received.run.id))
        issue_count = ValidationIssue.objects.filter(run=received.run).count()
        second = validate_batch.run(str(received.run.id))
        issues = list(ValidationIssue.objects.filter(run=received.run))
        received.batch.refresh_from_db()

        self.assertEqual(first["status"], ValidationRun.Status.SUCCEEDED)
        self.assertTrue(second["idempotent"])
        self.assertGreaterEqual(issue_count, 2)
        self.assertEqual(len(issues), issue_count)
        self.assertEqual(len({issue.fingerprint for issue in issues}), issue_count)
        self.assertEqual(received.batch.status, Batch.Status.REVIEW)
        self.assertTrue(all(issue.evidence == {
            "encrypted": True,
            "sha256": issue.evidence_sha256,
        } for issue in issues))
        self.assertTrue(all(b"000123" not in bytes(issue.evidence_ciphertext) for issue in issues))

    def test_pipeline_compares_against_a_previous_validated_batch(self):
        july_row = [["000042", "0123456789", "Persona A", "000123", 10, 2, 3, 4, 1]]
        august_row = [["000042", "0999999999", "Persona B", "000123", 10, 2, 3, 4, 1]]
        with patch.object(validate_batch, "delay"):
            july = receive_xlsx(
                self._file(july_row), uploaded_by=self.user,
                source_type="cartera_mensual", period=date(2026, 7, 1),
                sheet_name="Cartera", header_row=1, schema_name="carteraMensual",
            )
        validate_batch.run(str(july.run.id))
        july.batch.refresh_from_db()

        with patch.object(validate_batch, "delay"):
            august = receive_xlsx(
                self._file(august_row), uploaded_by=self.user,
                source_type="cartera_mensual", period=date(2026, 8, 1),
                sheet_name="Cartera", header_row=1, schema_name="carteraMensual",
                reference_batch=july.batch,
            )
        result = validate_batch.run(str(august.run.id))

        issue = ValidationIssue.objects.get(run=august.run, rule_code="KEY-002")
        self.assertEqual(result["status"], ValidationRun.Status.SUCCEEDED)
        self.assertEqual(issue.record.batch_id, august.batch.id)
        self.assertTrue(issue.related_records.filter(batch=july.batch).exists())

    def test_active_lease_rejects_even_a_redelivery_with_the_same_task_id(self):
        with patch.object(validate_batch, "delay"):
            received = receive_xlsx(
                self._file(),
                uploaded_by=self.user,
                source_type="cartera_mensual",
                period=date(2026, 8, 1),
                sheet_name="Cartera",
                header_row=1,
                schema_name="carteraMensual",
            )

        claimed, _, first_token, _ = _claim(received.run.id, "celery-task")
        duplicate_claimed, status, duplicate_token, retry_after = _claim(
            received.run.id,
            "celery-task",
        )

        self.assertTrue(claimed)
        self.assertFalse(duplicate_claimed)
        self.assertEqual(status, ValidationRun.Status.RUNNING)
        self.assertEqual(duplicate_token, "")
        self.assertGreaterEqual(retry_after, 5)

        ValidationRun.objects.filter(id=received.run.id).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1),
        )
        reclaimed, _, second_token, _ = _claim(received.run.id, "celery-task")
        self.assertTrue(reclaimed)
        self.assertNotEqual(first_token, second_token)

    def test_a_stale_reparse_cannot_reset_a_completed_record_to_pending(self):
        with patch.object(validate_batch, "delay"):
            received = receive_xlsx(
                self._file(),
                uploaded_by=self.user,
                source_type="cartera_mensual",
                period=date(2026, 8, 1),
                sheet_name="Cartera",
                header_row=1,
                schema_name="carteraMensual",
            )
        validate_batch.run(str(received.run.id))
        record = Record.objects.get(batch=received.batch)
        self.assertEqual(record.status, Record.Status.READY)

        _parse_and_store(received.batch, DatasetRole.CURRENT)

        record.refresh_from_db()
        self.assertEqual(record.status, Record.Status.READY)

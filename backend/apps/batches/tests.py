"""Pruebas de seguridad y contrato para la carga inicial de carteras."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from openpyxl import Workbook

from apps.audit.models import AuditEvent
from apps.batches.models import Batch
from apps.batches.services import batch_file_path
from apps.validation.models import ValidationRun
from apps.validation.tasks import validate_batch


UPLOAD_URL = "/api/v1/batches/uploads/"


class BatchUploadTests(TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory(
            dir=Path(__file__).resolve().parent,
        )
        self.addCleanup(self.temporary_directory.cleanup)
        self.settings_override = override_settings(
            ARNOLD_LOCAL_QUEUE=False,
            ARNOLD_FILE_ROOT=Path(self.temporary_directory.name),
            ARNOLD_REQUIRE_ANTIVIRUS=False,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.user = get_user_model().objects.create_user(
            username="validador-sintetico",
            password="una-clave-de-prueba-segura",
            area="Pruebas",
        )

    @staticmethod
    def _xlsx_bytes() -> bytes:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Cartera"
        sheet.append(
            [
                "CIU",
                "CEDULA_RUC",
                "NOMBRES",
                "CLAVE",
                "TOTAL_EMISION",
                "TOTAL_INTERES",
                "TOTAL_COACTIVA",
                "TOTAL_RECARGO",
                "MESES_DEUDA",
            ]
        )
        sheet.append(
            ["000042", "0123456789", "Persona sintética", "000123", 10, 2, 3, 4, 1]
        )

        from io import BytesIO

        stream = BytesIO()
        workbook.save(stream)
        workbook.close()
        return stream.getvalue()

    def _file(self, *, name="cartera-sintetica.xlsx", content=None, content_type=None):
        return SimpleUploadedFile(
            name,
            self._xlsx_bytes() if content is None else content,
            content_type=content_type
            or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def _payload(self, *, uploaded_file=None):
        return {
            "file": uploaded_file or self._file(),
            "source_type": "cartera_mensual",
            "dataset_role": "current",
            "period": "2026-08-01",
            "schema_name": "carteraMensual",
            "sheet_name": "Cartera",
            "header_row": "1",
        }

    def _grant_import_permission(self, user=None):
        content_type = ContentType.objects.get_for_model(Batch)
        permission, _ = Permission.objects.get_or_create(
            content_type=content_type,
            codename="import_batch",
            defaults={"name": "Puede cargar lotes para validación"},
        )
        (user or self.user).user_permissions.add(permission)

    def test_anonymous_upload_is_rejected_without_persisting_a_batch(self):
        response = self.client.post(UPLOAD_URL, self._payload())

        self.assertIn(response.status_code, (401, 403))
        self.assertFalse(Batch.objects.exists())

    def test_authenticated_user_without_import_permission_is_forbidden(self):
        self.client.force_login(self.user)

        response = self.client.post(UPLOAD_URL, self._payload())

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Batch.objects.exists())

    def test_valid_xlsx_creates_batch_and_validation_run(self):
        self._grant_import_permission()
        self.client.force_login(self.user)

        with patch.object(validate_batch, "delay") as enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(UPLOAD_URL, self._payload())

        self.assertEqual(response.status_code, 202)
        body = response.json()
        batch = Batch.objects.get(pk=body["batch_id"])
        run = ValidationRun.objects.get(pk=body["run_id"])
        self.assertEqual(run.current_batch, batch)
        self.assertEqual(batch.uploaded_by, self.user)
        self.assertEqual(batch.owner_area, "Pruebas")
        self.assertEqual(batch.status, Batch.Status.QUARANTINED)
        self.assertEqual(batch.period.isoformat(), "2026-08-01")
        self.assertEqual(body["status"], batch.status)
        self.assertTrue(body["status_url"].endswith(f"/{batch.pk}/"))
        enqueue.assert_called_once_with(str(run.pk))

    def test_same_file_cannot_be_uploaded_twice(self):
        self._grant_import_permission()
        self.client.force_login(self.user)

        with patch.object(validate_batch, "delay"):
            first = self.client.post(UPLOAD_URL, self._payload())
            second = self.client.post(UPLOAD_URL, self._payload())

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(Batch.objects.count(), 1)
        self.assertEqual(ValidationRun.objects.count(), 1)

    def test_non_xlsx_file_is_rejected_before_persistence(self):
        self._grant_import_permission()
        self.client.force_login(self.user)
        csv_file = self._file(
            name="cartera.csv",
            content=b"CLAVE,TOTAL\n000123,19.00\n",
            content_type="text/csv",
        )

        response = self.client.post(
            UPLOAD_URL,
            self._payload(uploaded_file=csv_file),
        )

        self.assertIn(response.status_code, (400, 415))
        self.assertFalse(Batch.objects.exists())

    def test_upload_requires_a_valid_csrf_token(self):
        self._grant_import_permission()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)

        response = csrf_client.post(UPLOAD_URL, self._payload())

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Batch.objects.exists())

    def test_batch_status_is_isolated_by_area(self):
        self._grant_import_permission()
        self.client.force_login(self.user)
        with patch.object(validate_batch, "delay"):
            created = self.client.post(UPLOAD_URL, self._payload())

        other = get_user_model().objects.create_user(
            username="otra-area-sintetica",
            password="otra-clave-de-prueba-segura",
            area="Otra área",
        )
        self._grant_import_permission(other)
        self.client.force_login(other)

        response = self.client.get(created.json()["status_url"])

        self.assertEqual(response.status_code, 404)

    def test_area_whitespace_is_normalized_for_upload_and_status(self):
        self.user.area = "  Pruebas  "
        self.user.save(update_fields=("area",))
        self._grant_import_permission()
        self.client.force_login(self.user)
        with patch.object(validate_batch, "delay"):
            created = self.client.post(UPLOAD_URL, self._payload())

        batch = Batch.objects.get(id=created.json()["batch_id"])
        response = self.client.get(created.json()["status_url"])

        self.assertEqual(created.status_code, 202)
        self.assertEqual(batch.owner_area, "Pruebas")
        self.assertEqual(response.status_code, 200)

    def test_queue_failure_preserves_the_file_and_allows_an_audited_retry(self):
        self._grant_import_permission()
        self.client.force_login(self.user)
        with patch(
            "apps.batches.services.transaction.on_commit",
            side_effect=lambda callback: callback(),
        ):
            with patch.object(validate_batch, "delay", side_effect=RuntimeError("cola caída")):
                created = self.client.post(UPLOAD_URL, self._payload())

        self.assertEqual(created.status_code, 503)
        batch = Batch.objects.get(id=created.json()["batch_id"])
        run = ValidationRun.objects.get(id=created.json()["run_id"])
        self.assertTrue(batch_file_path(batch).exists())
        self.assertEqual(batch.status, Batch.Status.FAILED)
        self.assertEqual(run.status, ValidationRun.Status.FAILED)
        self.assertEqual(run.error_code, "queue_unavailable")

        supervisor = get_user_model().objects.create_user(
            username="supervisor-reintento",
            password="otra-clave-de-prueba-segura",
            area="Pruebas",
        )
        self._grant_import_permission(supervisor)
        self.client.force_login(supervisor)
        with patch(
            "apps.batches.services.transaction.on_commit",
            side_effect=lambda callback: callback(),
        ):
            with patch.object(validate_batch, "delay") as enqueue:
                retried = self.client.post(f"/api/v1/batches/{batch.id}/retry/")

        self.assertEqual(retried.status_code, 202)
        enqueue.assert_called_once_with(str(run.id))
        run.refresh_from_db()
        self.assertEqual(run.status, ValidationRun.Status.QUEUED)
        self.assertEqual(
            AuditEvent.objects.get(action="validation.requeued").actor,
            supervisor,
        )

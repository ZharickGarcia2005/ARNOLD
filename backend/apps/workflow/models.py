import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from apps.batches.models import Batch, Record


class ChangeRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        APPROVED = "approved", "Aprobada"
        REJECTED = "rejected", "Rechazada"

    record = models.ForeignKey(Record, on_delete=models.PROTECT, related_name="change_requests")
    field_name = models.CharField(max_length=120)
    old_value_ciphertext = models.BinaryField()
    new_value_ciphertext = models.BinaryField()
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="requested_changes"
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.PROTECT, related_name="decided_changes"
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    expected_version = models.PositiveIntegerField(null=True, blank=True)

    def clean(self):
        if self.decided_by_id and self.decided_by_id == self.requested_by_id:
            raise ValidationError("El solicitante no puede aprobar su propio cambio.")

    class Meta:
        permissions = [
            ("decide_change_request", "Puede aprobar o rechazar cambios protegidos"),
        ]


class Worksheet(models.Model):
    batch = models.OneToOneField(Batch, primary_key=True, on_delete=models.PROTECT, related_name="worksheet")
    revision = models.PositiveIntegerField(default=1)
    prepared_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class WorksheetRow(models.Model):
    record = models.OneToOneField(Record, primary_key=True, on_delete=models.PROTECT, related_name="worksheet_row")
    worksheet = models.ForeignKey(Worksheet, on_delete=models.PROTECT, related_name="rows")
    data_ciphertext = models.BinaryField()
    version = models.PositiveIntegerField(default=1)
    clave_hmac = models.CharField(max_length=64, blank=True, db_index=True)
    identifier_hmac = models.CharField(max_length=64, blank=True, db_index=True)
    ciu_hmac = models.CharField(max_length=64, blank=True, db_index=True)
    source_errors = models.JSONField(default=list)
    errors = models.JSONField(default=list)
    duplicate = models.BooleanField(default=False)
    quality = models.CharField(max_length=10, default="clean", db_index=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)


class WorksheetEdit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    row = models.ForeignKey(WorksheetRow, on_delete=models.PROTECT, related_name="edits")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    detail_ciphertext = models.BinaryField()
    version = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)


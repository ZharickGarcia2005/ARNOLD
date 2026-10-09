import uuid
from django.conf import settings
from django.db import models


class Batch(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "Recibido"
        QUARANTINED = "quarantined", "En cuarentena"
        PROCESSING = "processing", "Procesando"
        REVIEW = "review", "En revisión"
        APPROVED = "approved", "Aprobado"
        REJECTED = "rejected", "Rechazado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    display_name = models.CharField(max_length=255)
    storage_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    sha256 = models.CharField(max_length=64, unique=True, editable=False)
    source_type = models.CharField(max_length=40)
    period = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED)
    row_count = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        permissions = [
            ("approve_batch", "Puede aprobar y cerrar lotes"),
            ("export_batch", "Puede exportar lotes"),
        ]


class Record(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        OBSERVED = "observed", "Observado"
        READY = "ready", "Sin alertas"
        APPROVED = "approved", "Aprobado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="records")
    source_row = models.PositiveIntegerField()
    clave_hmac = models.CharField(max_length=64, blank=True, db_index=True)
    ciu_hmac = models.CharField(max_length=64, blank=True, db_index=True)
    identifier_hmac = models.CharField(max_length=64, blank=True, db_index=True)
    data_ciphertext = models.BinaryField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    version = models.PositiveIntegerField(default=1)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="assigned_records"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("batch", "source_row"), name="unique_source_row_per_batch"),
        ]
        indexes = [
            models.Index(fields=("batch", "status")),
            models.Index(fields=("batch", "clave_hmac", "ciu_hmac")),
        ]

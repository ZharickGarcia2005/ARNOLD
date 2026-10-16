import uuid
from django.conf import settings
from django.db import models


class Batch(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "Recibido"
        QUARANTINED = "quarantined", "En cuarentena"
        PROCESSING = "processing", "Validando"
        REVIEW = "review", "En revisión"
        READY = "ready", "Listo para aprobar"
        APPROVED = "approved", "Aprobado"
        REJECTED = "rejected", "Rechazado"
        EXPORTED = "exported", "Exportado"
        FAILED = "failed", "Fallido"

    class ScanStatus(models.TextChoices):
        NOT_REQUIRED = "not_required", "No requerido (solo desarrollo)"
        PASSED = "passed", "Aprobado por antivirus"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    display_name = models.CharField(max_length=255)
    storage_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    sha256 = models.CharField(max_length=64, db_index=True, editable=False)
    source_type = models.CharField(max_length=40)
    period = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED)
    row_count = models.PositiveIntegerField(default=0)
    file_size = models.PositiveBigIntegerField(default=0)
    content_type = models.CharField(max_length=120, blank=True)
    owner_area = models.CharField(max_length=120, blank=True, db_index=True)
    sheet_name = models.CharField(max_length=120, blank=True)
    header_row = models.PositiveIntegerField(default=1)
    schema_name = models.CharField(max_length=80, blank=True)
    profile_id = models.CharField(max_length=80, blank=True)
    original_headers = models.JSONField(default=list, blank=True)
    headers_ciphertext = models.BinaryField(null=True, blank=True)
    selected_occurrences = models.JSONField(default=dict, blank=True)
    adapter_version = models.CharField(max_length=40, blank=True)
    content_version = models.PositiveIntegerField(default=1)
    scan_status = models.CharField(
        max_length=20,
        choices=ScanStatus.choices,
        default=ScanStatus.NOT_REQUIRED,
    )
    failure_code = models.CharField(max_length=60, blank=True)
    failure_message = models.CharField(max_length=500, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "sha256", "owner_area", "period", "source_type", "sheet_name",
                    "header_row", "schema_name", "profile_id",
                ),
                name="unique_batch_import_configuration",
            ),
        ]
        permissions = [
            ("import_batch", "Puede cargar lotes para validación"),
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

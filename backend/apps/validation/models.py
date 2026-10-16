import uuid

from django.conf import settings
from django.db import models

from apps.batches.models import Batch, Record


class ValidationRun(models.Model):
    """Ejecución reproducible del motor sobre un conjunto concreto de lotes."""

    class Status(models.TextChoices):
        QUEUED = "queued", "En cola"
        RUNNING = "running", "En ejecución"
        SUCCEEDED = "succeeded", "Completada"
        FAILED = "failed", "Fallida"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    current_batch = models.ForeignKey(
        Batch, on_delete=models.PROTECT, related_name="validation_runs"
    )
    reference_batch = models.ForeignKey(
        Batch, null=True, blank=True, on_delete=models.PROTECT,
        related_name="reference_validation_runs",
    )
    consolidated_batch = models.ForeignKey(
        Batch, null=True, blank=True, on_delete=models.PROTECT,
        related_name="consolidated_validation_runs",
    )
    catalog_batch = models.ForeignKey(
        Batch, null=True, blank=True, on_delete=models.PROTECT,
        related_name="catalog_validation_runs",
    )
    orders_batch = models.ForeignKey(
        Batch, null=True, blank=True, on_delete=models.PROTECT,
        related_name="orders_validation_runs",
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    input_digest = models.CharField(max_length=64, unique=True, editable=False)
    engine_version = models.CharField(max_length=40)
    adapter_version = models.CharField(max_length=40)
    enabled_rules = models.JSONField(default=list, blank=True)
    executed_rules = models.JSONField(default=list, blank=True)
    skipped_rules = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    issue_count = models.PositiveIntegerField(default=0)
    blocking_count = models.PositiveIntegerField(default=0)
    task_id = models.CharField(max_length=255, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=60, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("current_batch", "status")),
            models.Index(fields=("created_by", "created_at")),
        ]


class ValidationIssue(models.Model):
    class Severity(models.TextChoices):
        INFO = "info", "Informativa"
        WARNING = "warning", "Alerta"
        CRITICAL = "critical", "Crítica"

    class ReviewStatus(models.TextChoices):
        PENDING = "pending", "Pendiente"
        IN_REVIEW = "in_review", "En revisión"
        RESOLVED = "resolved", "Resuelta"
        DISMISSED = "dismissed", "Descartada"

    run = models.ForeignKey(
        ValidationRun, null=True, blank=True, on_delete=models.PROTECT,
        related_name="issues",
    )
    subject_batch = models.ForeignKey(
        Batch, null=True, blank=True, on_delete=models.PROTECT,
        related_name="validation_issues",
    )
    record = models.ForeignKey(
        Record, null=True, blank=True, on_delete=models.PROTECT,
        related_name="issues",
    )
    related_records = models.ManyToManyField(Record, blank=True, related_name="related_issues")
    fingerprint = models.CharField(max_length=64, blank=True)
    rule_code = models.CharField(max_length=40)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    blocking = models.BooleanField(default=False)
    field_name = models.CharField(max_length=120, blank=True)
    message = models.CharField(max_length=500)
    evidence = models.JSONField(default=dict, blank=True)
    evidence_ciphertext = models.BinaryField(null=True, blank=True)
    evidence_sha256 = models.CharField(max_length=64, blank=True)
    engine_version = models.CharField(max_length=40, blank=True)
    requires_review = models.BooleanField(default=True)
    review_status = models.CharField(
        max_length=20,
        choices=ReviewStatus.choices,
        default=ReviewStatus.PENDING,
        db_index=True,
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("run", "fingerprint"),
                condition=models.Q(run__isnull=False),
                name="unique_issue_per_validation_run",
            ),
        ]
        indexes = [
            models.Index(fields=("rule_code", "severity")),
            models.Index(fields=("record", "resolved_at")),
            models.Index(fields=("run", "blocking")),
        ]


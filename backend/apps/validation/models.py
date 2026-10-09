from django.db import models
from apps.batches.models import Record


class ValidationIssue(models.Model):
    class Severity(models.TextChoices):
        INFO = "info", "Informativa"
        WARNING = "warning", "Alerta"
        CRITICAL = "critical", "Crítica"

    record = models.ForeignKey(Record, on_delete=models.CASCADE, related_name="issues")
    rule_code = models.CharField(max_length=40)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    field_name = models.CharField(max_length=120, blank=True)
    message = models.CharField(max_length=500)
    evidence = models.JSONField(default=dict, blank=True)
    requires_review = models.BooleanField(default=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=("rule_code", "severity")),
            models.Index(fields=("record", "resolved_at")),
        ]


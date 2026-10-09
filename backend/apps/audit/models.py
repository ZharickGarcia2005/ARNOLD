import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="audit_events"
    )
    action = models.CharField(max_length=120, db_index=True)
    object_type = models.CharField(max_length=120)
    object_id = models.CharField(max_length=120)
    metadata = models.JSONField(default=dict, blank=True)
    previous_hash = models.CharField(max_length=64, blank=True)
    event_hash = models.CharField(max_length=64, unique=True)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Los eventos de auditoría son inmutables.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Los eventos de auditoría no pueden eliminarse.")

    class Meta:
        ordering = ("-occurred_at",)
        permissions = [("export_audit", "Puede exportar la bitácora")]


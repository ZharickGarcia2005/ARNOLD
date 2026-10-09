from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from apps.batches.models import Record


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

    def clean(self):
        if self.decided_by_id and self.decided_by_id == self.requested_by_id:
            raise ValidationError("El solicitante no puede aprobar su propio cambio.")

    class Meta:
        permissions = [
            ("decide_change_request", "Puede aprobar o rechazar cambios protegidos"),
        ]


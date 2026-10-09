from django.core.exceptions import ValidationError
from django.test import TestCase
from .models import AuditEvent


class AuditImmutabilityTests(TestCase):
    def test_saved_event_cannot_be_modified(self):
        event = AuditEvent.objects.create(
            action="test", object_type="test", object_id="1", event_hash="b" * 64,
        )
        event.action = "changed"
        with self.assertRaises(ValidationError):
            event.save()


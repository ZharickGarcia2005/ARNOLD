from django.core.exceptions import ValidationError
from django.test import TestCase
from apps.accounts.models import User
from apps.batches.models import Batch, Record
from .models import ChangeRequest


class DoubleControlTests(TestCase):
    def test_requester_cannot_decide_own_change(self):
        user = User.objects.create_user(username="validator")
        batch = Batch.objects.create(
            display_name="prueba.xlsx", sha256="a" * 64,
            source_type="cartera-mensual", uploaded_by=user,
        )
        record = Record.objects.create(
            batch=batch, source_row=2, data_ciphertext=b"encrypted",
        )
        request = ChangeRequest(
            record=record, field_name="monto", old_value_ciphertext=b"old",
            new_value_ciphertext=b"new", reason="Prueba", requested_by=user,
            decided_by=user,
        )
        with self.assertRaises(ValidationError):
            request.full_clean()


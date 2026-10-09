from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        VALIDATOR = "validator", "Validador"
        SUPERVISOR = "supervisor", "Jefe de área"
        AUDITOR = "auditor", "Auditor"
        ADMIN = "admin", "Administrador"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.VALIDATOR)
    area = models.CharField(max_length=120, blank=True)
    must_use_mfa = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.role in {self.Role.SUPERVISOR, self.Role.ADMIN}:
            self.must_use_mfa = True
        super().save(*args, **kwargs)


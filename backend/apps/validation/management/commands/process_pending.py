"""Trabajador de desarrollo para Windows sin dependencias de Redis."""

import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.db.models import Q
from django.utils import timezone

from apps.validation.models import ValidationRun
from apps.validation.tasks import validate_batch


class Command(BaseCommand):
    help = "Procesa lotes pendientes de desarrollo; use --watch para seguir esperando."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true")

    def handle(self, *args, **options):
        if not settings.DEBUG or not getattr(settings, "ARNOLD_LOCAL_QUEUE", False):
            raise CommandError("Este trabajador requiere DEBUG=True y ARNOLD_LOCAL_QUEUE=1.")
        self.stdout.write("Trabajador local de ARNOLD activo.")
        while True:
            close_old_connections()
            run = ValidationRun.objects.filter(
                Q(status=ValidationRun.Status.QUEUED)
                | Q(status=ValidationRun.Status.RUNNING, lease_expires_at__lt=timezone.now())
            ).order_by("created_at").first()
            if run:
                self.stdout.write(f"Procesando ejecución {run.id}")
                try:
                    result = validate_batch.apply(args=(str(run.id),), throw=True).get()
                    self.stdout.write(f"Resultado: {result.get('status')}")
                except Exception as exc:
                    self.stderr.write(f"La ejecución {run.id} terminó con {type(exc).__name__}.")
            elif not options["watch"]:
                return
            else:
                time.sleep(2)

from django.core.management.base import BaseCommand

from apps.batches.models import Batch
from apps.workflow.worksheet import prepare_worksheet, summary


class Command(BaseCommand):
    help = "Prepara las hojas de lotes ya validados sin modificar los Excel originales."

    def handle(self, *args, **options):
        for batch in Batch.objects.filter(validation_runs__status="succeeded", worksheet__isnull=True).distinct():
            sheet = prepare_worksheet(batch)
            result = summary(sheet)
            self.stdout.write(f"{batch.id}: {result['total']} filas, {result['clean']} limpias, {result['problem']} por revisar.")

import json
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from apps.workflow.order_import import import_order_book
from apps.workflow.order_projection import presentation_counts


class Command(BaseCommand):
    help = "Carga las 12 hojas operativas como una cartera nueva, sin reemplazar lotes existentes."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--username", required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        try:
            actor = get_user_model().objects.get(username=options["username"])
            batch, result = import_order_book(options["path"], actor=actor, dry_run=options["dry_run"])
            if batch:
                result.update(batch_id=str(batch.pk), status=batch.status,
                              tabs=dict(presentation_counts(batch.worksheet)))
            self.stdout.write(json.dumps(result, ensure_ascii=False))
        except (ValueError, OSError, get_user_model().DoesNotExist) as exc:
            raise CommandError(str(exc)) from exc

from uuid import UUID

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.encryption.write_fence import reopen


class Command(BaseCommand):
    help = "Reopen a closed persistent mapped-PII write fence operation."

    def add_arguments(self, parser):
        parser.add_argument("--operation", required=True)
        parser.add_argument("--actor-id", type=int, required=True)

    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(
            pk=options["actor_id"], is_active=True, is_superuser=True
        ).first()
        if actor is None:
            raise CommandError("--actor-id must reference an active superuser.")
        try:
            operation_id = UUID(options["operation"])
        except ValueError as exc:
            raise CommandError("--operation must be a UUID.") from exc
        try:
            reopen(operation_id, actor.id)
        except Exception as exc:
            raise CommandError("Could not reopen the PII write fence.") from exc
        self.stdout.write(str(operation_id))

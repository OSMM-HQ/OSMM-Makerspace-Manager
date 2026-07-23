"""Irreversibly minimize historical keyless platform email logs."""

from uuid import UUID

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.audit.services import record
from apps.encryption.models import PiiGlobalWriteFence
from apps.encryption.write_fence import fence_operation

_SUBJECT = "Platform email"
_BATCH_SIZE = 500


class Command(BaseCommand):
    help = "Redact historical platform EmailLog recipients and rendered content."

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--dry-run", action="store_true")
        mode.add_argument("--apply", action="store_true")
        parser.add_argument("--actor-id", type=int, required=True)
        parser.add_argument("--fence-operation")

    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(
            pk=options["actor_id"], is_active=True, is_superuser=True
        ).first()
        if actor is None:
            raise CommandError("--actor-id must reference an active superuser.")
        operation = self._operation(options)
        pending = self._pending_count()
        if options["dry_run"]:
            self.stdout.write(f"platform_rows={pending} redacted=0")
            return
        self._assert_fence(operation)
        redacted, checkpoint = 0, 0
        while True:
            with transaction.atomic(), fence_operation(operation):
                ids = self._pending_ids(checkpoint)
                if not ids:
                    break
                with connection.cursor() as cursor:
                    cursor.execute(
                        'UPDATE "integrations_emaillog" SET "to_email" = %s, "subject" = %s, '
                        '"text_body" = %s, "html_body" = %s WHERE "id" = ANY(%s)',
                        ["", _SUBJECT, "", "", ids],
                    )
                redacted += len(ids)
                checkpoint = ids[-1]
                record(actor, "encryption.platform_logs_redacted", meta={"count": len(ids), "checkpoint": checkpoint})
            self.stdout.write(f"checkpoint={checkpoint} redacted={redacted}")
        self.stdout.write(f"platform_rows={pending} redacted={redacted}")

    def _operation(self, options):
        if options["dry_run"]:
            return None
        if not options["fence_operation"]:
            raise CommandError("--fence-operation is required with --apply.")
        try:
            return UUID(options["fence_operation"])
        except ValueError as exc:
            raise CommandError("--fence-operation must be a UUID.") from exc

    def _assert_fence(self, operation):
        fence = PiiGlobalWriteFence.objects.filter(pk=1).first()
        if not fence or (fence.state, fence.operation_id, fence.operation_kind) != (
            fence.State.CLOSED, operation, fence.OperationKind.ENABLE_TRANSITION,
        ):
            raise CommandError("A matching closed enable-transition global fence is required.")

    def _pending_count(self):
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT count(*) FROM "integrations_emaillog" WHERE "makerspace_id" IS NULL '
                'AND ("to_email" <> %s OR "subject" <> %s OR "text_body" <> %s OR "html_body" <> %s)',
                ["", _SUBJECT, "", ""],
            )
            return cursor.fetchone()[0]

    def _pending_ids(self, checkpoint):
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT "id" FROM "integrations_emaillog" WHERE "id" > %s AND "makerspace_id" IS NULL '
                'AND ("to_email" <> %s OR "subject" <> %s OR "text_body" <> %s OR "html_body" <> %s) '
                'ORDER BY "id" LIMIT %s',
                [checkpoint, "", _SUBJECT, "", "", _BATCH_SIZE],
            )
            return [row[0] for row in cursor.fetchall()]

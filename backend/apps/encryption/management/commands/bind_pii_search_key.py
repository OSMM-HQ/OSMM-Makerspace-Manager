from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.audit.services import record
from apps.encryption.blind_index import search_key_fingerprint
from apps.encryption.models import PiiBlindIndex, SearchKeyGeneration


class Command(BaseCommand):
    help = "Bind the configured HMAC search key to its non-secret initial generation."

    def add_arguments(self, parser):
        parser.add_argument("--initial", action="store_true", required=True)
        parser.add_argument("--actor-id", type=int, required=True)

    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(
            pk=options["actor_id"], is_active=True, is_superuser=True
        ).first()
        if actor is None:
            raise CommandError("--actor-id must reference an active superuser.")
        fingerprint = search_key_fingerprint()
        with transaction.atomic():
            list(SearchKeyGeneration.objects.select_for_update().all())
            current = SearchKeyGeneration.objects.first()
            if current is not None:
                if SearchKeyGeneration.objects.count() != 1 or current.status != current.Status.ACTIVE or bytes(current.key_fingerprint) != fingerprint:
                    raise CommandError("Search key is already bound to a different generation.")
                record(actor, "encryption.search_key_verified", meta={"generation": current.generation})
                self.stdout.write("generation=1 verified")
                return
            if PiiBlindIndex.objects.exists():
                raise CommandError("Cannot bind a populated blind-index installation.")
            from apps.events.models import EventRegistration
            if EventRegistration.objects.filter(email_exact_hash__isnull=False).exists():
                raise CommandError("Cannot bind a populated event hash installation.")
            SearchKeyGeneration.objects.create(generation=1, key_fingerprint=fingerprint, status=SearchKeyGeneration.Status.ACTIVE, activated_at=timezone.now())
            record(actor, "encryption.search_key_bound", meta={"generation": 1})
        self.stdout.write("generation=1 bound")

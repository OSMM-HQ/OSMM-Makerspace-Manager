from django.core.management.base import BaseCommand, CommandError

from apps.updates import services
from apps.updates.models import PlatformUpdateSettings


class Command(BaseCommand):
    help = "Coordinate the privileged host updater with application update state."

    def add_arguments(self, parser):
        commands = parser.add_subparsers(dest="action", required=True)

        set_auto = commands.add_parser("set-auto")
        set_auto.add_argument("value", choices=("on", "off"))

        claim = commands.add_parser("claim")
        claim.add_argument("--current", default="")
        claim.add_argument("--available", required=True)
        claim.add_argument("--force", action="store_true")

        backup = commands.add_parser("record-backup")
        backup.add_argument("--name", required=True)

        complete = commands.add_parser("complete")
        complete.add_argument("--version", required=True)

        failed = commands.add_parser("fail")
        failed.add_argument("--message", required=True)

    def handle(self, *args, **options):
        action = options["action"]
        if action == "set-auto":
            settings = PlatformUpdateSettings.load()
            settings.automatic_updates_enabled = options["value"] == "on"
            settings.save(
                update_fields=("automatic_updates_enabled", "updated_at")
            )
            self.stdout.write("on" if settings.automatic_updates_enabled else "off")
            return
        if action == "claim":
            claimed = services.claim_update(
                current_version=options["current"].strip(),
                available_version=options["available"].strip(),
                force=options["force"],
            )
            self.stdout.write("run" if claimed else "skip")
            return
        if action == "record-backup":
            services.record_backup(options["name"])
            self.stdout.write("recorded")
            return
        if action == "complete":
            services.complete_update(options["version"].strip())
            self.stdout.write("complete")
            return
        if action == "fail":
            services.fail_update(options["message"])
            self.stdout.write("failed")
            return
        raise CommandError("Unknown update control action.")

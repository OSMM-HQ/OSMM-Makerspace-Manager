import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from apps.makerspaces.models import Makerspace


class Command(BaseCommand):
    help = "Create the first superadmin and makerspace for a self-hosted instance."

    def add_arguments(self, parser):
        parser.add_argument("--username", default=os.getenv("SETUP_SUPERADMIN_USERNAME", "admin"))
        parser.add_argument("--email", default=os.getenv("SETUP_SUPERADMIN_EMAIL", "admin@example.com"))
        parser.add_argument("--password", default=os.getenv("SETUP_SUPERADMIN_PASSWORD", ""))
        parser.add_argument("--makerspace-name", default=os.getenv("SETUP_MAKERSPACE_NAME", "My Makerspace"))
        parser.add_argument("--makerspace-slug", default=os.getenv("SETUP_MAKERSPACE_SLUG", ""))

    def handle(self, *args, **options):
        password = options["password"]
        if not password:
            raise CommandError("Provide --password or SETUP_SUPERADMIN_PASSWORD.")

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=options["username"],
            defaults={
                "email": options["email"],
                "role": User.Role.SUPERADMIN,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created:
            user.set_password(password)
            user.save()
        else:
            changed = False
            if not user.is_superuser:
                user.is_superuser = True
                changed = True
            if not user.is_staff:
                user.is_staff = True
                changed = True
            if user.role != User.Role.SUPERADMIN:
                user.role = User.Role.SUPERADMIN
                changed = True
            if changed:
                user.save(update_fields=["is_superuser", "is_staff", "role"])

        slug = options["makerspace_slug"] or slugify(options["makerspace_name"])
        makerspace, space_created = Makerspace.objects.get_or_create(
            slug=slug,
            defaults={"name": options["makerspace_name"], "created_by": user},
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{'Created' if created else 'Found'} superadmin {user.username}; "
                f"{'created' if space_created else 'found'} makerspace {makerspace.slug}."
            )
        )

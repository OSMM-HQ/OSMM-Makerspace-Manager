import pytest
from rest_framework.test import APIRequestFactory

from apps.accounts.models import User
from apps.admin_api.serializers_makerspaces import MakerspaceSerializer
from apps.makerspaces.models import Makerspace
from apps.makerspaces.platform import bootstrap_payload

pytestmark = pytest.mark.django_db


def make_space(slug="display-name-space", **overrides):
    defaults = {"name": "TinkerSpace Calicut", "slug": slug}
    defaults.update(overrides)
    return Makerspace.objects.create(**defaults)


def patch_display_name(makerspace, value):
    """Run a partial serializer update for the public_display_name field only."""
    request = APIRequestFactory().patch("/")
    request.user = User.objects.create_superuser(
        username=f"super-{makerspace.slug}", password="x"
    )
    serializer = MakerspaceSerializer(
        makerspace,
        data={"public_display_name": value},
        partial=True,
        context={"request": request},
    )
    assert serializer.is_valid(), serializer.errors
    return serializer.save()


def test_public_display_name_sets_only_the_nested_key_and_preserves_others():
    makerspace = make_space(
        branding_config={"display_name": "Calicut", "support_email": "help@x.org"}
    )

    patch_display_name(makerspace, "TinkerSpace Calicut")
    makerspace.refresh_from_db()

    assert makerspace.branding_config["display_name"] == "TinkerSpace Calicut"
    # The unrelated branding key is preserved (no whole-blob clobber).
    assert makerspace.branding_config["support_email"] == "help@x.org"


def test_bootstrap_shows_override_when_set():
    makerspace = make_space()
    patch_display_name(makerspace, "Calicut Makers")
    makerspace.refresh_from_db()

    payload = bootstrap_payload(makerspace)
    assert payload["branding"]["display_name"] == "Calicut Makers"


def test_blank_override_falls_back_to_registered_name():
    makerspace = make_space(branding_config={"display_name": "Calicut"})

    patch_display_name(makerspace, "")
    makerspace.refresh_from_db()

    # Stored value is blank...
    assert makerspace.branding_config["display_name"] == ""
    # ...so the public bootstrap falls back to the registered makerspace name.
    payload = bootstrap_payload(makerspace)
    assert payload["branding"]["display_name"] == "TinkerSpace Calicut"


def test_whitespace_is_trimmed():
    makerspace = make_space()
    patch_display_name(makerspace, "  Trimmed Name  ")
    makerspace.refresh_from_db()

    assert makerspace.branding_config["display_name"] == "Trimmed Name"


def test_overlong_display_name_is_rejected():
    makerspace = make_space()
    request = APIRequestFactory().patch("/")
    request.user = User.objects.create_superuser(username="super-long", password="x")
    serializer = MakerspaceSerializer(
        makerspace,
        data={"public_display_name": "x" * 201},
        partial=True,
        context={"request": request},
    )

    assert serializer.is_valid() is False
    assert "public_display_name" in serializer.errors


def test_create_with_public_display_name_folds_into_branding():
    request = APIRequestFactory().post("/")
    request.user = User.objects.create_superuser(username="super-create", password="x")
    serializer = MakerspaceSerializer(
        data={
            "name": "TinkerSpace Calicut",
            "slug": "created-space",
            "public_code": "CR8T",
            "public_display_name": "Calicut Makers",
        },
        context={"request": request},
    )
    assert serializer.is_valid(), serializer.errors
    makerspace = serializer.save()

    assert makerspace.branding_config["display_name"] == "Calicut Makers"


def test_create_without_public_display_name_defaults_blank():
    request = APIRequestFactory().post("/")
    request.user = User.objects.create_superuser(username="super-create2", password="x")
    serializer = MakerspaceSerializer(
        data={"name": "Plain Space", "slug": "plain-space", "public_code": "PL8N"},
        context={"request": request},
    )
    assert serializer.is_valid(), serializer.errors
    makerspace = serializer.save()

    assert makerspace.branding_config.get("display_name", "") == ""


def test_branding_config_is_read_only_over_the_api():
    makerspace = make_space(branding_config={"display_name": "Original"})
    request = APIRequestFactory().patch("/")
    request.user = User.objects.create_superuser(username="super-ro", password="x")
    serializer = MakerspaceSerializer(
        makerspace,
        data={"branding_config": {"display_name": "Hacked", "support_url": "evil"}},
        partial=True,
        context={"request": request},
    )
    assert serializer.is_valid(), serializer.errors
    serializer.save()
    makerspace.refresh_from_db()

    # The whole-blob write is ignored; the override is unchanged.
    assert makerspace.branding_config["display_name"] == "Original"
    assert "support_url" not in makerspace.branding_config

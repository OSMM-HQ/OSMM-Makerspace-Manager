import pytest
from django.core.exceptions import ValidationError

from apps.admin_api.serializers_makerspaces import MakerspaceSerializer
from apps.inventory.serializers import PublicMakerspaceSerializer
from apps.makerspaces.models import Makerspace
from apps.makerspaces.platform import bootstrap_payload
from apps.makerspaces.validators import validate_google_maps_url


pytestmark = pytest.mark.django_db


def make_space(slug="map-url-space", **overrides):
    defaults = {
        "name": slug,
        "slug": slug,
    }
    defaults.update(overrides)
    return Makerspace.objects.create(**defaults)


@pytest.mark.parametrize(
    "url",
    [
        "https://maps.app.goo.gl/abc",
        "https://www.google.com/maps/place/x",
        "https://maps.google.com/?q=x",
        "https://goo.gl/maps/x",
        "https://g.co/kgs/x",
        "",
    ],
)
def test_validate_google_maps_url_accepts_allowed_links(url):
    validate_google_maps_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://maps.google.com/x",
        "https://google.com.evil.com/maps",
        "https://evil-google.com/maps",
        "https://google.com@evil.com/maps",
        "https://evil.com/maps",
        "javascript:alert(1)",
        "https://google.com/search",
    ],
)
def test_validate_google_maps_url_rejects_invalid_links(url):
    with pytest.raises(ValidationError):
        validate_google_maps_url(url)


def test_makerspace_serializer_rejects_invalid_map_url():
    serializer = MakerspaceSerializer(
        data={
            "name": "Map URL",
            "slug": "map-url",
            "public_code": "MAP1",
            "map_url": "https://evil.com/maps",
        }
    )

    assert serializer.is_valid() is False
    assert "map_url" in serializer.errors


def test_bootstrap_payload_includes_map_url():
    makerspace = make_space(map_url="https://maps.app.goo.gl/abc")

    payload = bootstrap_payload(makerspace)

    assert payload["makerspace"]["map_url"] == "https://maps.app.goo.gl/abc"


def test_public_makerspace_serializer_includes_map_url():
    makerspace = make_space(
        slug="public-map-url",
        map_url="https://www.google.com/maps/place/x",
    )

    assert PublicMakerspaceSerializer(makerspace).data["map_url"] == (
        "https://www.google.com/maps/place/x"
    )

from datetime import timedelta
import json

import pytest
from django.contrib.auth import get_user_model
from django.urls import Resolver404, resolve, reverse
from django.utils import timezone
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient

from apps.roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

PUBLIC_FIELDS = {
    "title",
    "description",
    "status",
    "category",
    "published_at",
}
FORBIDDEN_KEYS = {
    "id",
    "pk",
    "order",
    "is_public",
    "created_at",
    "updated_at",
    "makerspace",
    "makerspace_id",
    "storage",
    "storage_key",
    "object_key",
    "qr",
    "qr_code",
    "scan",
    "evidence",
    "photo",
}


def make_item(title, **kwargs):
    return RoadmapItem.objects.create(
        title=title,
        description=kwargs.pop("description", "Plain text"),
        **kwargs,
    )


def assert_no_forbidden_keys(value):
    if isinstance(value, dict):
        assert FORBIDDEN_KEYS.isdisjoint(value)
        for nested in value.values():
            assert_no_forbidden_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            assert_no_forbidden_keys(nested)


def test_anonymous_and_authenticated_callers_can_list_roadmap():
    make_item("Visible")
    anonymous = APIClient()
    authenticated = APIClient()
    authenticated.force_authenticate(
        get_user_model().objects.create_user(username="roadmap-reader")
    )

    assert anonymous.get(reverse("public-roadmap")).status_code == 200
    assert authenticated.get(reverse("public-roadmap")).status_code == 200


def test_public_rows_are_unpaginated_ordered_and_date_is_not_a_visibility_gate():
    now = timezone.now()
    make_item("Private shipped", status="shipped", is_public=False, published_at=now)
    pinned = make_item("Pinned", order=-2, published_at=None)
    future = make_item("Future", order=0, published_at=now + timedelta(days=30))
    recent = make_item("Recent", order=0, published_at=now)
    same_first = make_item("Same first", order=0, published_at=now - timedelta(days=1))
    same_second = make_item("Same second", order=0, published_at=now - timedelta(days=1))
    undated = make_item("Undated", order=0, published_at=None)
    make_item("Private planned", is_public=False, published_at=None)

    response = APIClient().get(reverse("public-roadmap"))

    assert response.status_code == 200
    assert isinstance(response.data, list)
    assert [row["title"] for row in response.data] == [
        pinned.title,
        undated.title,
        future.title,
        recent.title,
        same_first.title,
        same_second.title,
    ]


def test_serializer_is_an_exact_allowlist_with_recursive_leak_protection():
    hidden_sentinel = "PRIVATE-ROADMAP-SENTINEL"
    make_item(hidden_sentinel, description=hidden_sentinel, is_public=False)
    public = make_item(
        "Safe title",
        description="Description without internal data",
        category="Platform",
        order=-99,
    )

    response = APIClient().get(reverse("public-roadmap"))
    serialized = json.dumps(response.data)

    assert response.status_code == 200
    assert len(response.data) == 1
    assert set(response.data[0]) == PUBLIC_FIELDS
    assert response.data[0]["title"] == public.title
    assert_no_forbidden_keys(response.data)
    assert hidden_sentinel not in serialized


def test_description_is_returned_unchanged_as_plain_text():
    description = "<script>alert('x')</script>\n**not bold**"
    make_item("Plain text", description=description)

    response = APIClient().get(reverse("public-roadmap"))

    assert response.data[0]["description"] == description


def test_only_canonical_no_trailing_slash_route_is_registered():
    path = reverse("public-roadmap")

    assert path == "/api/v1/public/roadmap"
    assert resolve(path).url_name == "public-roadmap"
    with pytest.raises(Resolver404):
        resolve(f"{path}/")
    assert APIClient().get(f"{path}/").status_code == 404


def test_openapi_has_exact_public_roadmap_contract():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    operation = schema["paths"]["/api/v1/public/roadmap"]["get"]
    component = schema["components"]["schemas"]["PublicRoadmap"]

    assert operation["tags"] == ["Public roadmap"]
    assert operation["summary"] == "List public roadmap items"
    assert operation.get("security", []) == []
    assert "requestBody" not in operation
    assert set(operation["responses"]) == {"200"}
    response_schema = operation["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    assert response_schema["type"] == "array"
    assert response_schema["items"]["$ref"].endswith("/PublicRoadmap")
    assert set(component["properties"]) == PUBLIC_FIELDS
    assert set(component["required"]) == PUBLIC_FIELDS

    status_ref = component["properties"]["status"]["allOf"][0]["$ref"]
    status_schema = schema["components"]["schemas"][status_ref.rsplit("/", 1)[-1]]
    assert status_schema["enum"] == ["shipped", "in_progress", "planned"]
    assert component["properties"]["published_at"] == {
        "type": "string",
        "format": "date-time",
        "readOnly": True,
        "nullable": True,
    }

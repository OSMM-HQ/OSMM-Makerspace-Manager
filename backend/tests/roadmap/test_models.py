from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.makerspaces.models import Makerspace
from apps.roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db


def test_defaults_and_string_representation():
    item = RoadmapItem.objects.create(title="Public roadmap", description="Details")

    assert item.status == RoadmapItem.Status.PLANNED
    assert item.category == ""
    assert item.order == 0
    assert item.is_public is True
    assert item.published_at is None
    assert str(item) == item.title


def test_status_values_round_trip_with_expected_labels():
    expected = {
        RoadmapItem.Status.SHIPPED: "Shipped",
        RoadmapItem.Status.IN_PROGRESS: "In progress",
        RoadmapItem.Status.PLANNED: "Planned",
    }

    for index, (status, label) in enumerate(expected.items()):
        item = RoadmapItem.objects.create(
            title=f"Status {index}",
            description="Details",
            status=status,
        )
        item.refresh_from_db()
        assert item.status == status
        assert RoadmapItem.Status(item.status).label == label


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", ""),
        ("description", ""),
        ("title", "x" * 201),
        ("category", "x" * 101),
        ("status", "x" * 21),
    ],
)
def test_required_fields_and_declared_maximum_lengths_are_validated(field, value):
    item = RoadmapItem(title="Valid", description="Details")
    setattr(item, field, value)

    with pytest.raises(ValidationError) as exc_info:
        item.full_clean()

    assert field in exc_info.value.message_dict


def test_default_queryset_ordering_is_editorial_order_date_then_id():
    now = timezone.now()
    pinned = RoadmapItem.objects.create(
        title="Pinned", description="Details", order=-1
    )
    recent = RoadmapItem.objects.create(
        title="Recent", description="Details", published_at=now
    )
    same_time_first = RoadmapItem.objects.create(
        title="Same first",
        description="Details",
        published_at=now - timedelta(days=1),
    )
    same_time_second = RoadmapItem.objects.create(
        title="Same second",
        description="Details",
        published_at=now - timedelta(days=1),
    )
    older = RoadmapItem.objects.create(
        title="Older",
        description="Details",
        published_at=now - timedelta(days=2),
    )
    undated = RoadmapItem.objects.create(title="Undated", description="Details")

    assert list(RoadmapItem.objects.all()) == [
        pinned,
        undated,
        recent,
        same_time_first,
        same_time_second,
        older,
    ]
    assert RoadmapItem._meta.ordering == ["order", "-published_at", "id"]


def test_creation_and_update_timestamps_behave_independently(monkeypatch):
    item = RoadmapItem.objects.create(title="Timestamped", description="Details")
    created_at = item.created_at
    updated_at = item.updated_at
    later = updated_at + timedelta(seconds=1)

    monkeypatch.setattr("django.db.models.fields.timezone.now", lambda: later)
    item.title = "Updated"
    item.save()
    item.refresh_from_db()

    assert item.created_at == created_at
    assert item.updated_at > updated_at


def test_model_is_platform_scoped_without_a_makerspace_relation():
    fields = RoadmapItem._meta.get_fields()

    assert all(field.name != "makerspace" for field in fields)
    assert all(getattr(field, "related_model", None) is not Makerspace for field in fields)

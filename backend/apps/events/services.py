"""Audited mutation boundary for Events and their registrations."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.audit import services as audit
from apps.events.capacity import CONFIRMED_STATUSES, fresh_registration_status
from apps.events.exceptions import (
    CapacityConflict,
    DuplicateRegistration,
    EventInvalidTransition,
)
from apps.events.models import Event, EventRegistration
from apps.makerspaces import limits
from apps.makerspaces.models import Makerspace

EVENT_FIELDS = frozenset(
    {"title", "description", "starts_at", "ends_at", "location", "capacity", "is_public"}
)


def _locked_event(event_id):
    return Event.objects.select_for_update().select_related("makerspace").get(
        pk=event_id
    )


def _validate(instance):
    try:
        instance.full_clean(validate_unique=False, validate_constraints=False)
    except DjangoValidationError as exc:
        detail = exc.message_dict if hasattr(exc, "message_dict") else exc.messages
        raise serializers.ValidationError(detail) from exc
    if isinstance(instance, Event) and instance.ends_at < instance.starts_at:
        detail = {"ends_at": "End time must be at or after start time."}
        raise serializers.ValidationError(detail)


def _audit(event, actor, action, target, meta=None):
    kwargs = {"makerspace": event.makerspace, "target": target, "meta": meta or {}}
    return audit.record(actor, action, **kwargs)


def _refresh(instance):
    instance.refresh_from_db()
    return instance


def _may_promote(event, now):
    return event.status == Event.Status.PUBLISHED and event.ends_at >= now


def _lock_waiters(event):
    return list(
        EventRegistration.objects.select_for_update()
        .filter(event=event, status=EventRegistration.Status.WAITLISTED)
        .order_by("created_at", "id")
    )


def _promote(event, actor, waiters, count=None):
    selected = waiters if count is None else waiters[:count]
    for registration in selected:
        registration.status = EventRegistration.Status.REGISTERED
        registration.save(update_fields=["status"])
        meta = {"registration_id": registration.pk}
        _audit(event, actor, "event.registration_promoted", registration, meta)
    return selected


@transaction.atomic
def create_event(
    *, makerspace, actor, title, description, starts_at, ends_at, location,
    capacity, is_public
):
    locked_space = Makerspace.objects.select_for_update().get(pk=makerspace.pk)
    event = Event(
        makerspace=locked_space,
        created_by=actor,
        title=title,
        description=description,
        starts_at=starts_at,
        ends_at=ends_at,
        location=location,
        capacity=capacity,
        is_public=is_public,
    )
    _validate(event)
    event.save()
    _audit(event, actor, "event.created", event)
    return _refresh(event)


@transaction.atomic
def update_event(event, *, actor, **changes):
    locked = _locked_event(event.pk)
    if locked.status not in (Event.Status.DRAFT, Event.Status.PUBLISHED):
        raise EventInvalidTransition("Terminal events cannot be updated.")
    unknown = set(changes) - EVENT_FIELDS
    if unknown:
        raise serializers.ValidationError(
            {field: "This field cannot be updated." for field in sorted(unknown)}
        )

    now = timezone.now()
    old_capacity, old_ends_at = locked.capacity, locked.ends_at
    for field, value in changes.items():
        setattr(locked, field, value)
    _validate(locked)

    confirmed = EventRegistration.objects.filter(
        event=locked, status__in=CONFIRMED_STATUSES
    ).count()
    if locked.capacity > 0 and confirmed > locked.capacity:
        raise CapacityConflict("Capacity cannot be below confirmed occupancy.")
    if (
        locked.status == Event.Status.PUBLISHED
        and old_ends_at < now <= locked.ends_at
    ):
        limits.check_quota(locked.makerspace, "events", adding=1)

    promoted = []
    capacity_changed = "capacity" in changes and locked.capacity != old_capacity
    if capacity_changed and _may_promote(locked, now):
        waiters = _lock_waiters(locked)
        if locked.capacity == 0:
            promoted = _promote(locked, actor, waiters)
        elif locked.capacity > old_capacity:
            promoted = _promote(
                locked, actor, waiters, locked.capacity - confirmed
            )

    if changes:
        locked.save(update_fields=[*sorted(changes), "updated_at"])
    meta = {"changed_fields": sorted(changes)}
    if capacity_changed:
        meta.update(
            old_capacity=old_capacity,
            new_capacity=locked.capacity,
            promoted_registration_ids=[row.pk for row in promoted],
        )
    _audit(locked, actor, "event.updated", locked, meta)
    return _refresh(locked)


def _transition(event, actor, expected, new_status, action):
    locked = _locked_event(event.pk)
    if locked.status != expected:
        raise EventInvalidTransition(
            f"Cannot transition event from {locked.status} to {new_status}."
        )
    locked.status = new_status
    locked.save(update_fields=["status", "updated_at"])
    meta = {"old_status": expected, "new_status": new_status}
    _audit(locked, actor, action, locked, meta)
    return _refresh(locked)


@transaction.atomic
def publish(event, *, actor):
    locked = _locked_event(event.pk)
    if locked.status != Event.Status.DRAFT:
        raise EventInvalidTransition("Only draft events can be published.")
    _validate(locked)
    if locked.ends_at < timezone.now():
        raise EventInvalidTransition("Ended events cannot be published.")
    limits.check_quota(locked.makerspace, "events", adding=1)
    locked.status = Event.Status.PUBLISHED
    locked.save(update_fields=["status", "updated_at"])
    meta = {"old_status": Event.Status.DRAFT, "new_status": Event.Status.PUBLISHED}
    _audit(locked, actor, "event.published", locked, meta)
    return _refresh(locked)


@transaction.atomic
def cancel(event, *, actor):
    return _transition(
        event, actor, Event.Status.PUBLISHED, Event.Status.CANCELLED,
        "event.cancelled",
    )


@transaction.atomic
def complete(event, *, actor):
    return _transition(
        event, actor, Event.Status.PUBLISHED, Event.Status.COMPLETED,
        "event.completed",
    )


@transaction.atomic
def register(event, *, name, email, phone, actor=None):
    locked = _locked_event(event.pk)
    if (
        not locked.is_public
        or locked.status != Event.Status.PUBLISHED
        or locked.ends_at < timezone.now()
    ):
        raise EventInvalidTransition("This event is not open for registration.")
    normalized_email = (email or "").strip().lower()
    status = fresh_registration_status(locked)
    if EventRegistration.objects.filter(
        event=locked, email=normalized_email
    ).exists():
        raise DuplicateRegistration(
            "A registration already exists for this email.",
            fresh_status=status,
        )
    registration = EventRegistration(
        event=locked,
        name=(name or "").strip(),
        email=normalized_email,
        phone=(phone or "").strip(),
        status=status,
    )
    _validate(registration)
    registration.save()
    meta = {"registration_id": registration.pk, "status": status}
    _audit(locked, actor, "event.registration_created", registration, meta)
    return _refresh(registration)


@transaction.atomic
def cancel_registration(registration, *, actor=None):
    event = _locked_event(registration.event_id)
    locked = EventRegistration.objects.select_for_update().get(pk=registration.pk)
    if locked.event_id != event.pk or locked.status not in (
        EventRegistration.Status.REGISTERED,
        EventRegistration.Status.WAITLISTED,
    ):
        raise EventInvalidTransition("This registration cannot be cancelled.")
    old_status = locked.status
    locked.status = EventRegistration.Status.CANCELLED
    locked.save(update_fields=["status"])
    meta = {"registration_id": locked.pk, "old_status": old_status}
    _audit(event, actor, "event.registration_cancelled", locked, meta)
    if (
        old_status == EventRegistration.Status.REGISTERED
        and event.capacity > 0
        and _may_promote(event, timezone.now())
    ):
        waiters = _lock_waiters(event)
        if waiters:
            _promote(event, actor, waiters, 1)
    return _refresh(locked)


@transaction.atomic
def mark_attended(registration, *, actor):
    event = _locked_event(registration.event_id)
    locked = EventRegistration.objects.select_for_update().get(pk=registration.pk)
    if (
        locked.event_id != event.pk
        or locked.status != EventRegistration.Status.REGISTERED
        or event.status not in (Event.Status.PUBLISHED, Event.Status.COMPLETED)
    ):
        raise EventInvalidTransition("This registration cannot be marked attended.")
    locked.status = EventRegistration.Status.ATTENDED
    locked.save(update_fields=["status"])
    _audit(
        event, actor, "event.registration_attended", locked,
        {"registration_id": locked.pk},
    )
    return _refresh(locked)

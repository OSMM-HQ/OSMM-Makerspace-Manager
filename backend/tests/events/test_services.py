from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from django.db import close_old_connections
from django.test import override_settings
from django.utils import timezone
from rest_framework.serializers import ValidationError

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.events import services
from apps.events.exceptions import (
    CapacityConflict,
    DuplicateRegistration,
    EventInvalidTransition,
)
from apps.events.models import Event, EventRegistration
from apps.hardware_requests.exceptions import workflow_exception_handler
from apps.makerspaces import limits
from apps.makerspaces.models import Makerspace

pytestmark = pytest.mark.django_db


def make_space(slug="events-services"):
    return Makerspace.objects.create(name=slug, slug=slug)


def make_actor(name="events-manager"):
    return User.objects.create_user(username=name)


def make_event(space, **overrides):
    start = timezone.now() + timedelta(hours=1)
    values = dict(
        makerspace=space, title="Workshop", starts_at=start,
        ends_at=start + timedelta(hours=2), is_public=True,
        status=Event.Status.PUBLISHED,
    )
    values.update(overrides)
    return Event.objects.create(**values)


def make_registration(event, email, status=EventRegistration.Status.REGISTERED):
    return EventRegistration.objects.create(
        event=event, name="Guest", email=email, phone="123", status=status
    )


def register(event, email):
    return services.register(event, name="Guest", email=email, phone="123")


def test_create_makes_draft_and_audits_without_quota(monkeypatch):
    space, actor = make_space(), make_actor()
    start = timezone.now() + timedelta(hours=1)
    quota_calls = []
    monkeypatch.setattr(
        services.limits, "check_quota",
        lambda *args, **kwargs: quota_calls.append((args, kwargs)),
    )
    event = services.create_event(
        makerspace=space, actor=actor, title=" New event ",
        description="", starts_at=start, ends_at=start + timedelta(hours=1),
        location="", capacity=0, is_public=True,
    )
    assert (event.status, event.title, event.created_by) == (
        Event.Status.DRAFT, "New event", actor
    )
    assert quota_calls == []
    assert AuditLog.objects.get().action == "event.created"


def test_event_state_machine_temporal_rules_and_audits():
    space, actor = make_space(), make_actor()
    cancelled = services.cancel(services.publish(
        make_event(space, status=Event.Status.DRAFT), actor=actor
    ), actor=actor)
    early = services.complete(make_event(space, title="Early"), actor=actor)
    ended = make_event(
        space, title="Ended", starts_at=timezone.now() - timedelta(hours=2),
        ends_at=timezone.now() - timedelta(hours=1),
    )
    assert services.complete(ended, actor=actor).status == Event.Status.COMPLETED
    assert cancelled.status == Event.Status.CANCELLED
    assert early.status == Event.Status.COMPLETED
    draft = make_event(
        space, title="Past draft", status=Event.Status.DRAFT,
        starts_at=timezone.now() - timedelta(hours=2),
        ends_at=timezone.now() - timedelta(hours=1),
    )
    with pytest.raises(EventInvalidTransition):
        services.publish(draft, actor=actor)
    draft.refresh_from_db()
    assert draft.status == Event.Status.DRAFT
    assert set(AuditLog.objects.values_list("action", flat=True)) >= {
        "event.published", "event.cancelled", "event.completed"
    }


@pytest.mark.parametrize(
    ("operation", "state"),
    [
        (services.publish, Event.Status.PUBLISHED),
        (services.publish, Event.Status.CANCELLED),
        (services.complete, Event.Status.DRAFT),
        (services.complete, Event.Status.COMPLETED),
        (services.cancel, Event.Status.DRAFT),
        (services.cancel, Event.Status.CANCELLED),
    ],
)
def test_other_event_transitions_are_conflicts_without_mutation(operation, state):
    event, actor = make_event(make_space(), status=state), make_actor()
    with pytest.raises(EventInvalidTransition):
        operation(event, actor=actor)
    event.refresh_from_db()
    assert event.status == state
    assert not AuditLog.objects.exists()


def test_update_rejects_forbidden_invalid_and_terminal_changes():
    space, actor = make_space(), make_actor()
    event = make_event(space, status=Event.Status.DRAFT)
    for changes in (
        {"status": Event.Status.PUBLISHED}, {"makerspace": make_space("other")},
        {"created_by": actor}, {"unknown": "value"},
    ):
        with pytest.raises(ValidationError):
            services.update_event(event, actor=actor, **changes)
    with pytest.raises(ValidationError):
        services.update_event(
            event, actor=actor, ends_at=event.starts_at - timedelta(seconds=1)
        )
    event.status = Event.Status.COMPLETED
    event.save(update_fields=["status"])
    with pytest.raises(EventInvalidTransition):
        services.update_event(event, actor=actor, title="No")
    assert not AuditLog.objects.exists()


def test_managed_limit_blocks_publish_and_self_host_ignores_cap():
    space, actor = make_space(), make_actor()
    space.resource_limit_overrides = {"events": 0}
    space.save(update_fields=["resource_limit_overrides"])
    with override_settings(PLATFORM_DOMAIN_SUFFIX=".osmm.me"):
        with pytest.raises(ValidationError) as caught:
            services.publish(make_event(space, status=Event.Status.DRAFT), actor=actor)
        assert caught.value.get_codes() == {"limit": "limit_reached"}
    with override_settings(PLATFORM_DOMAIN_SUFFIX=""):
        published = services.publish(
            make_event(space, title="Self hosted", status=Event.Status.DRAFT),
            actor=actor,
        )
    assert published.status == Event.Status.PUBLISHED


def test_event_quota_counter_has_exact_scope_and_temporal_set():
    now = timezone.now()
    space, other = make_space(), make_space("other-space")
    make_event(space, title="Included", ends_at=now + timedelta(hours=2))
    for title, values in (
        ("Draft", {"status": Event.Status.DRAFT}),
        ("Cancelled", {"status": Event.Status.CANCELLED}),
        ("Completed", {"status": Event.Status.COMPLETED}),
        ("Ended", {
            "starts_at": now - timedelta(hours=2),
            "ends_at": now - timedelta(seconds=1),
        }),
    ):
        make_event(space, title=title, **values)
    make_event(other, title="Other")
    assert limits._events(space) == 1


def test_only_ended_to_upcoming_published_edit_checks_quota(monkeypatch):
    space, actor = make_space(), make_actor()
    past = timezone.now() - timedelta(hours=1)
    event = make_event(
        space, starts_at=past - timedelta(hours=1), ends_at=past
    )
    calls = []
    monkeypatch.setattr(
        services.limits, "check_quota",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    services.update_event(
        event, actor=actor, starts_at=timezone.now(),
        ends_at=timezone.now() + timedelta(hours=1),
    )
    services.update_event(event, actor=actor, title="Still upcoming")
    services.update_event(
        event, actor=actor, starts_at=timezone.now() - timedelta(hours=2),
        ends_at=timezone.now() - timedelta(seconds=1),
    )
    assert len(calls) == 1
    assert calls[0][0][0].pk == event.makerspace_id
    assert calls[0][0][1:] == ("events",)
    assert calls[0][1] == {"adding": 1}


def test_capacity_zero_registers_and_positive_capacity_waitlists():
    space = make_space()
    unlimited = make_event(space, capacity=0)
    assert {register(unlimited, f"u{i}@x.test").status for i in range(3)} == {
        EventRegistration.Status.REGISTERED
    }
    limited = make_event(space, title="Limited", capacity=2)
    statuses = [register(limited, f"l{i}@x.test").status for i in range(3)]
    assert statuses == ["registered", "registered", "waitlisted"]


@pytest.mark.django_db(transaction=True)
def test_concurrent_mutations_serialize_without_oversubscription_or_deadlock():
    space, actor = make_space(), make_actor()
    event = make_event(space, capacity=1)
    from apps.encryption.models import PiiMakerspaceWriteFence

    barrier = Barrier(2)
    def concurrent_register(index):
        close_old_connections(); barrier.wait()
        try:
            # The test's worker connections do not share its uncommitted setup
            # transaction, unlike production provisioning. Seed the required
            # persistent row on each worker before exercising registration.
            PiiMakerspaceWriteFence.objects.get_or_create(makerspace_id=event.makerspace_id)
            return register(Event.objects.get(pk=event.pk), f"c{index}@x.test").status
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(concurrent_register, range(2)))
    assert sorted(results) == ["registered", "waitlisted"]
    assert event.registrations.filter(status__in=services.CONFIRMED_STATUSES).count() == 1

    confirmed = event.registrations.get(status="registered")
    barrier = Barrier(2)
    def reconcile(operation):
        close_old_connections(); barrier.wait()
        try:
            if operation == "cancel":
                services.cancel_registration(
                    EventRegistration.objects.get(pk=confirmed.pk), actor=actor
                )
            else:
                services.update_event(
                    Event.objects.get(pk=event.pk), actor=actor, capacity=2
                )
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(reconcile, op) for op in ("cancel", "capacity")]
        [future.result(timeout=10) for future in futures]
    assert event.registrations.filter(status="registered").count() == 1

    attendee = event.registrations.get(status="registered")
    barrier = Barrier(2)
    def attend():
        close_old_connections(); barrier.wait()
        try:
            services.mark_attended(
                EventRegistration.objects.get(pk=attendee.pk), actor=actor
            )
            return "attended"
        except EventInvalidTransition:
            return "conflict"
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: attend(), range(2)))
    assert sorted(outcomes) == ["attended", "conflict"]


def test_duplicate_normalized_email_creates_no_row_or_audit():
    event = make_event(make_space())
    register(event, "  ADA@Example.COM ")
    before = AuditLog.objects.count()
    with pytest.raises(DuplicateRegistration):
        register(event, "ada@example.com")
    assert event.registrations.count() == 1
    assert AuditLog.objects.count() == before


@pytest.mark.parametrize(
    "changes",
    [
        {"is_public": False}, {"status": Event.Status.DRAFT},
        {"status": Event.Status.CANCELLED}, {"status": Event.Status.COMPLETED},
        {
            "starts_at": timezone.now() - timedelta(hours=2),
            "ends_at": timezone.now() - timedelta(hours=1),
        },
    ],
)
def test_register_rejects_events_that_are_not_open(changes):
    event = make_event(make_space(), **changes)
    with pytest.raises(EventInvalidTransition):
        register(event, "closed@example.com")
    assert not event.registrations.exists()
    assert not AuditLog.objects.exists()


def test_cancellation_promotion_is_fifo_and_only_when_allowed():
    space = make_space()
    event = make_event(space, capacity=1)
    confirmed = make_registration(event, "confirmed@x.test")
    oldest = make_registration(event, "old@x.test", "waitlisted")
    newest = make_registration(event, "new@x.test", "waitlisted")
    EventRegistration.objects.filter(pk=oldest.pk).update(
        created_at=timezone.now() - timedelta(hours=1)
    )
    services.cancel_registration(confirmed)
    oldest.refresh_from_db(); newest.refresh_from_db()
    assert (oldest.status, newest.status) == ("registered", "waitlisted")
    services.cancel_registration(newest)
    assert AuditLog.objects.filter(action="event.registration_promoted").count() == 1
    for suffix, event_changes in (
        ("ended", {
            "starts_at": timezone.now() - timedelta(hours=2),
            "ends_at": timezone.now() - timedelta(hours=1),
        }),
        ("completed", {"status": Event.Status.COMPLETED}),
    ):
        closed = make_event(space, title=suffix, capacity=1, **event_changes)
        held = make_registration(closed, f"{suffix}1@x.test")
        waiter = make_registration(closed, f"{suffix}2@x.test", "waitlisted")
        services.cancel_registration(held)
        waiter.refresh_from_db()
        assert waiter.status == "waitlisted"


def test_capacity_edits_promote_fifo_and_conflicts_roll_back():
    space, actor = make_space(), make_actor()
    event = make_event(space, capacity=1)
    make_registration(event, "held@x.test")
    waiters = [
        make_registration(event, f"w{i}@x.test", "waitlisted") for i in range(3)
    ]
    services.update_event(event, actor=actor, capacity=3)
    assert [EventRegistration.objects.get(pk=row.pk).status for row in waiters] == [
        "registered", "registered", "waitlisted"
    ]
    services.update_event(event, actor=actor, capacity=0)
    assert EventRegistration.objects.get(pk=waiters[-1].pk).status == "registered"
    audit_count = AuditLog.objects.count()
    with pytest.raises(CapacityConflict):
        services.update_event(event, actor=actor, capacity=3)
    event.refresh_from_db()
    assert event.capacity == 0 and AuditLog.objects.count() == audit_count

    ended = make_event(
        space, title="Ended", capacity=1,
        starts_at=timezone.now() - timedelta(hours=2),
        ends_at=timezone.now() - timedelta(hours=1),
    )
    make_registration(ended, "e1@x.test")
    waiter = make_registration(ended, "e2@x.test", "waitlisted")
    services.update_event(ended, actor=actor, capacity=2)
    waiter.refresh_from_db()
    assert waiter.status == "waitlisted"


def test_reopening_ended_event_promotes_waiter_into_freed_slot_fifo():
    space, actor = make_space(), make_actor()
    ended = make_event(
        space,
        capacity=2,
        starts_at=timezone.now() - timedelta(hours=2),
        ends_at=timezone.now() - timedelta(hours=1),
    )
    cancelled = make_registration(ended, "cancelled@x.test")
    make_registration(ended, "held@x.test")
    oldest = make_registration(ended, "oldest@x.test", "waitlisted")
    newest = make_registration(ended, "newest@x.test", "waitlisted")
    EventRegistration.objects.filter(pk=oldest.pk).update(
        created_at=timezone.now() - timedelta(hours=1)
    )
    services.cancel_registration(cancelled, actor=actor)

    services.update_event(
        ended,
        actor=actor,
        ends_at=timezone.now() + timedelta(hours=1),
    )

    oldest.refresh_from_db()
    newest.refresh_from_db()
    assert (oldest.status, newest.status) == ("registered", "waitlisted")
    updated = AuditLog.objects.filter(action="event.updated").latest("created_at")
    assert updated.meta["promoted_registration_ids"] == [oldest.pk]


def test_attendance_state_machine():
    space, actor = make_space(), make_actor()
    for state in (Event.Status.PUBLISHED, Event.Status.COMPLETED):
        row = make_registration(make_event(space, title=state, status=state), f"{state}@x.test")
        assert services.mark_attended(row, actor=actor).status == "attended"
    for state, reg_state in (
        (Event.Status.DRAFT, "registered"), (Event.Status.CANCELLED, "registered"),
        (Event.Status.PUBLISHED, "waitlisted"),
    ):
        row = make_registration(
            make_event(space, title=f"{state}-{reg_state}", status=state),
            f"{state}-{reg_state}@x.test", reg_state,
        )
        with pytest.raises(EventInvalidTransition):
            services.mark_attended(row, actor=actor)


def test_audit_targets_metadata_and_audit_failure_rollback(monkeypatch):
    event = make_event(make_space(), capacity=1)
    registration = register(event, "private@example.com")
    log = AuditLog.objects.get(action="event.registration_created")
    assert (log.target_type, log.makerspace) == (
        "events.eventregistration", event.makerspace
    )
    assert "private@example.com" not in str(log.meta)
    services.update_event(event, actor=None, title="Changed")
    assert AuditLog.objects.get(action="event.updated").target_type == "events.event"

    failing = make_event(event.makerspace, title="Rollback")
    monkeypatch.setattr(services.audit, "record", lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    with pytest.raises(RuntimeError):
        register(failing, "rollback@example.com")
    assert not failing.registrations.exists()


@pytest.mark.parametrize(
    ("exc", "status_code", "code"),
    [
        (EventInvalidTransition("bad state"), 409, "invalid_transition"),
        (CapacityConflict("bad capacity"), 409, "capacity_conflict"),
        (DuplicateRegistration("duplicate"), 400, "duplicate_registration"),
    ],
)
def test_workflow_exceptions_have_exact_response_shape(exc, status_code, code):
    response = workflow_exception_handler(exc, {})
    assert response.status_code == status_code
    assert response.data == {"detail": str(exc), "code": code}

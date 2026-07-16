from datetime import timedelta
from uuid import uuid4

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.events.models import Event, EventRegistration
from apps.events.views_public import PublicEventListView, PublicEventRegistrationView
from apps.makerspaces.models import Makerspace


pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clear_throttles():
    cache.clear()
    yield
    cache.clear()


def make_space(slug='public-events', **values):
    return Makerspace.objects.create(name=slug, slug=slug, **values)


def make_event(space, title='Workshop', **values):
    start = values.pop('starts_at', timezone.now() + timedelta(days=1))
    end = values.pop('ends_at', start + timedelta(hours=2))
    defaults = {
        'starts_at': start,
        'ends_at': end,
        'is_public': True,
        'status': Event.Status.PUBLISHED,
    }
    defaults.update(values)
    return Event.objects.create(makerspace=space, title=title, **defaults)


def make_registration(event, email, status=EventRegistration.Status.REGISTERED):
    return EventRegistration.objects.create(
        event=event,
        name='Guest',
        email=email,
        phone='1234567890',
        status=status,
    )


def list_url(identifier):
    return reverse('public-event-list', kwargs={'makerspace_slug': identifier})


def register_url(identifier, event):
    return reverse(
        'public-event-register',
        kwargs={
            'makerspace_slug': identifier,
            'public_token': event.public_token,
        },
    )


def identity(email='guest@example.com', **values):
    data = {'name': 'Guest', 'email': email, 'phone': '1234567890'}
    data.update(values)
    return data


def test_public_views_are_allow_any_and_module_gate_is_exact():
    assert PublicEventListView.permission_classes == [AllowAny]
    assert PublicEventRegistrationView.permission_classes == [AllowAny]
    space = make_space()
    space.enabled_modules = [key for key in space.enabled_modules if key != 'events']
    space.save(update_fields=['enabled_modules'])

    response = APIClient().get(list_url(space.slug))

    assert response.status_code == 400
    assert response.data == {'module': 'events is disabled for this makerspace.'}
    assert APIClient().get(list_url('unknown-space')).status_code == 404


def test_list_filters_by_tenant_slug_or_code_and_orders_without_n_plus_one(
    django_assert_num_queries,
):
    space = make_space()
    other = make_space('other-public-events')
    same_start = timezone.now() + timedelta(days=2)
    first = make_event(space, 'First', starts_at=same_start)
    second = make_event(space, 'Second', starts_at=same_start)
    earlier = make_event(
        space,
        'Earlier',
        starts_at=same_start - timedelta(hours=1),
        ends_at=same_start + timedelta(hours=1),
    )
    make_event(space, 'Private', is_public=False)
    make_event(space, 'Draft', status=Event.Status.DRAFT)
    make_event(
        space,
        'Ended',
        starts_at=timezone.now() - timedelta(hours=2),
        ends_at=timezone.now() - timedelta(seconds=1),
    )
    make_event(space, 'Cancelled', status=Event.Status.CANCELLED)
    make_event(other, 'Other tenant')

    with django_assert_num_queries(2):
        response = APIClient().get(list_url(space.slug))

    assert response.status_code == 200
    assert [row['public_token'] for row in response.data] == [
        str(earlier.public_token),
        str(first.public_token),
        str(second.public_token),
    ]
    by_code = APIClient().get(list_url(space.public_code))
    assert by_code.status_code == 200
    assert by_code.data == response.data


def test_spots_left_uses_only_confirmed_statuses_floors_and_handles_unlimited():
    space = make_space()
    limited = make_event(space, 'Limited', capacity=3)
    overfull = make_event(space, 'Overfull', capacity=1)
    unlimited = make_event(space, 'Unlimited', capacity=0)
    for status, email in (
        (EventRegistration.Status.REGISTERED, 'registered@example.com'),
        (EventRegistration.Status.ATTENDED, 'attended@example.com'),
        (EventRegistration.Status.WAITLISTED, 'waitlisted@example.com'),
        (EventRegistration.Status.CANCELLED, 'cancelled@example.com'),
    ):
        make_registration(limited, email, status)
    make_registration(overfull, 'one@example.com')
    make_registration(overfull, 'two@example.com')

    rows = {
        row['title']: row for row in APIClient().get(list_url(space.slug)).data
    }

    assert rows['Limited']['spots_left'] == 1
    assert rows['Overfull']['spots_left'] == 0
    assert rows['Unlimited']['spots_left'] is None


def test_registration_by_list_token_returns_status_only_and_waitlists_when_full():
    space = make_space()
    event = make_event(space, capacity=1)
    public_token = APIClient().get(list_url(space.slug)).data[0]['public_token']
    assert public_token == str(event.public_token)
    url = reverse(
        'public-event-register',
        kwargs={'makerspace_slug': space.slug, 'public_token': public_token},
    )

    registered = APIClient().post(url, identity(), format='json')
    waitlisted = APIClient().post(
        url,
        identity('second@example.com'),
        format='json',
    )

    assert registered.status_code == waitlisted.status_code == 201
    assert registered.data == {'status': EventRegistration.Status.REGISTERED}
    assert waitlisted.data == {'status': EventRegistration.Status.WAITLISTED}


def test_honeypot_precedes_identity_validation_and_blank_value_proceeds():
    space = make_space()
    event = make_event(space)
    url = register_url(space.slug, event)

    decoy = APIClient().post(url, {'website': ' bot.example '}, format='json')

    assert decoy.status_code == 201
    assert decoy.data == {'status': EventRegistration.Status.REGISTERED}
    assert not event.registrations.exists()
    assert not AuditLog.objects.filter(action='event.registration_created').exists()

    blank = APIClient().post(
        url,
        identity(website='   '),
        format='json',
    )
    assert blank.status_code == 201
    assert event.registrations.count() == 1


def test_missing_identity_is_rejected_when_honeypot_is_blank():
    space = make_space()
    response = APIClient().post(
        register_url(space.slug, make_event(space)),
        {'website': ''},
        format='json',
    )
    assert response.status_code == 400
    assert set(response.data) == {'name', 'email', 'phone'}


def test_registration_targets_are_slug_scoped_and_public_open_only():
    space = make_space()
    other = make_space('other-registration-space')
    now = timezone.now()
    private = make_event(space, 'Private', is_public=False)
    draft = make_event(space, 'Draft', status=Event.Status.DRAFT)
    cancelled = make_event(space, 'Cancelled', status=Event.Status.CANCELLED)
    completed = make_event(space, 'Completed', status=Event.Status.COMPLETED)
    ended = make_event(
        space,
        'Ended',
        starts_at=now - timedelta(hours=2),
        ends_at=now - timedelta(seconds=1),
    )
    open_event = make_event(space, 'Open')

    client = APIClient()
    for target in (private, draft, cancelled, completed, ended):
        assert client.post(
            register_url(space.slug, target), identity(), format='json'
        ).status_code == 404
    assert client.post(
        register_url(other.slug, open_event), identity(), format='json'
    ).status_code == 404
    assert client.post(
        register_url(other.public_code, open_event), identity(), format='json'
    ).status_code == 404
    missing_url = reverse(
        'public-event-register',
        kwargs={'makerspace_slug': space.slug, 'public_token': uuid4()},
    )
    assert client.post(missing_url, identity(), format='json').status_code == 404


def test_duplicate_normalized_email_matches_generic_new_registration_response():
    space = make_space()
    event = make_event(space, capacity=3)
    make_registration(event, 'guest@example.com')

    client = APIClient()
    fresh = client.post(
        register_url(space.slug, event),
        identity('new@example.com'),
        format='json',
    )
    duplicate = client.post(
        register_url(space.slug, event),
        identity(' Guest@Example.com '),
        format='json',
    )

    assert duplicate.status_code == fresh.status_code == 201
    assert duplicate.data == fresh.data == {
        'status': EventRegistration.Status.REGISTERED,
    }
    assert set(duplicate.data) == {'status'}
    assert 'guest@example.com' not in str(duplicate.data).lower()


def test_duplicate_on_full_event_matches_fresh_waitlisted_response():
    space = make_space()
    event = make_event(space, capacity=1)
    make_registration(event, 'guest@example.com')

    client = APIClient()
    fresh = client.post(
        register_url(space.slug, event),
        identity('new@example.com'),
        format='json',
    )
    duplicate = client.post(
        register_url(space.slug, event),
        identity(' Guest@Example.com '),
        format='json',
    )

    assert duplicate.status_code == fresh.status_code == 201
    assert duplicate.data == fresh.data == {
        'status': EventRegistration.Status.WAITLISTED,
    }
    assert set(duplicate.data) == {'status'}
    assert 'guest@example.com' not in str(duplicate.data).lower()


def test_public_registration_audit_is_actorless_and_pii_free():
    space = make_space()
    event = make_event(space)
    payload = identity(
        'private-audit@example.com',
        name='Private Audit Name',
        phone='9988776655',
    )

    response = APIClient().post(
        register_url(space.slug, event), payload, format='json'
    )

    assert response.status_code == 201
    log = AuditLog.objects.get(action='event.registration_created')
    assert log.actor is None
    assert log.makerspace == space
    audit_text = str(log.meta).lower()
    for pii in ('private-audit@example.com', 'private audit name', '9988776655'):
        assert pii not in audit_text


def test_eleventh_hourly_registration_is_throttled_but_listing_is_unaffected():
    space = make_space()
    event = make_event(space, capacity=0)
    url = register_url(space.slug, event)
    client = APIClient()

    for index in range(10):
        response = client.post(
            url,
            identity(f'guest-{index}@example.com'),
            format='json',
        )
        assert response.status_code == 201

    assert client.post(
        url, identity('guest-11@example.com'), format='json'
    ).status_code == 429
    assert client.get(list_url(space.slug)).status_code == 200

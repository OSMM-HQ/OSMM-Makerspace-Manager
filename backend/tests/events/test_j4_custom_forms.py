from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import serializers
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.events import services
from apps.events.models import Event, EventRegistration
from apps.makerspaces.models import Makerspace, MakerspaceMembership


pytestmark = pytest.mark.django_db


FORM = [
    {
        'id': 'purpose',
        'label': 'Purpose',
        'type': 'short_text',
        'options': [],
        'required': True,
    }
]


def make_space(slug):
    return Makerspace.objects.create(name=slug, slug=slug)


def make_manager(space):
    user = User.objects.create_user(
        username=f'{space.slug}-manager',
        access_status=User.AccessStatus.ACTIVE,
    )
    MakerspaceMembership.objects.create(
        user=user,
        makerspace=space,
        role=MakerspaceMembership.Role.SPACE_MANAGER,
    )
    client = APIClient()
    client.force_authenticate(user)
    return client


def event_times():
    starts_at = timezone.now() + timedelta(days=1)
    return starts_at, starts_at + timedelta(hours=2)


def make_public_event(space, **values):
    starts_at, ends_at = event_times()
    defaults = {
        'title': 'Workshop',
        'starts_at': starts_at,
        'ends_at': ends_at,
        'is_public': True,
        'status': Event.Status.PUBLISHED,
    }
    defaults.update(values)
    return Event.objects.create(makerspace=space, **defaults)


def registration_url(space, event):
    return reverse(
        'public-event-register',
        kwargs={
            'makerspace_slug': space.slug,
            'public_token': event.public_token,
        },
    )


def registration_payload(email='guest@example.com', **values):
    payload = {
        'name': 'Guest',
        'email': email,
        'phone': '1234567890',
    }
    payload.update(values)
    return payload


def test_staff_event_form_and_structured_location_create_update_round_trip():
    space = make_space('j4-staff-event')
    client = make_manager(space)
    starts_at, ends_at = event_times()
    list_url = reverse(
        'admin-event-list-create', kwargs={'makerspace_id': space.pk}
    )

    created = client.post(
        list_url,
        {
            'title': 'First aid',
            'starts_at': starts_at.isoformat(),
            'ends_at': ends_at.isoformat(),
            'location': ' Main hall ',
            'location_kind': Event.LocationKind.INDOOR,
            'custom_form': [{**FORM[0], 'label': ' Purpose '}],
        },
        format='json',
    )

    assert created.status_code == 201
    assert created.data['location'] == 'Main hall'
    assert created.data['location_kind'] == Event.LocationKind.INDOOR
    assert created.data['custom_form'] == FORM

    detail_url = reverse('admin-event-detail', kwargs={'pk': created.data['id']})
    updated = client.patch(
        detail_url,
        {
            'location': 'Courtyard',
            'location_kind': Event.LocationKind.OUTDOOR,
            'custom_form': [],
        },
        format='json',
    )

    assert updated.status_code == 200
    assert updated.data['location'] == 'Courtyard'
    assert updated.data['location_kind'] == Event.LocationKind.OUTDOOR
    assert updated.data['custom_form'] is None
    assert client.get(detail_url).data['custom_form'] is None


def test_staff_rejects_invalid_event_form_without_mutating_event():
    space = make_space('j4-invalid-staff-form')
    client = make_manager(space)
    event = make_public_event(space, status=Event.Status.DRAFT, custom_form=FORM)
    url = reverse('admin-event-detail', kwargs={'pk': event.pk})

    response = client.patch(
        url,
        {'custom_form': [{**FORM[0], 'required': 1}]},
        format='json',
    )

    assert response.status_code == 400
    event.refresh_from_db()
    assert event.custom_form == FORM


def test_public_event_exposes_form_and_location_and_snapshots_valid_answers():
    space = make_space('j4-public-form')
    event = make_public_event(
        space,
        location='Workshop bay',
        location_kind=Event.LocationKind.INDOOR,
        custom_form=FORM,
    )
    client = APIClient()

    listed = client.get(
        reverse('public-event-list', kwargs={'makerspace_slug': space.slug})
    )
    registered = client.post(
        registration_url(space, event),
        registration_payload(custom_answers={'purpose': '  Build a robot  '}),
        format='json',
    )

    assert listed.status_code == 200
    assert listed.data[0]['location'] == 'Workshop bay'
    assert listed.data[0]['location_kind'] == Event.LocationKind.INDOOR
    assert listed.data[0]['custom_form'] == FORM
    assert registered.status_code == 201
    assert registered.data == {'status': EventRegistration.Status.REGISTERED}
    registration = event.registrations.get()
    assert registration.custom_answers == {
        'version': 1,
        'answers': [
            {
                'id': 'purpose',
                'label': 'Purpose',
                'type': 'short_text',
                'value': 'Build a robot',
            }
        ],
    }


def test_public_registration_rejects_invalid_answers_before_creation():
    space = make_space('j4-invalid-public-answer')
    event = make_public_event(space, custom_form=FORM)

    response = APIClient().post(
        registration_url(space, event),
        registration_payload(custom_answers={}),
        format='json',
    )

    assert response.status_code == 400
    assert response.data['custom_answers']['purpose'] == (
        'This question is required.'
    )
    assert not event.registrations.exists()


def test_registration_service_revalidates_against_freshly_locked_form():
    space = make_space('j4-locked-form')
    stale_event = make_public_event(space)
    Event.objects.filter(pk=stale_event.pk).update(custom_form=FORM)

    with pytest.raises(serializers.ValidationError) as exc_info:
        services.register(
            stale_event,
            name='Guest',
            email='guest@example.com',
            phone='1234567890',
        )

    assert exc_info.value.detail['custom_answers']['purpose'] == (
        'This question is required.'
    )
    assert not stale_event.registrations.exists()


def test_staff_registration_view_includes_private_answer_snapshot():
    space = make_space('j4-staff-answers')
    event = make_public_event(space, custom_form=FORM)
    APIClient().post(
        registration_url(space, event),
        registration_payload(custom_answers={'purpose': 'Training'}),
        format='json',
    )

    response = make_manager(space).get(
        reverse('admin-event-registration-list', kwargs={'pk': event.pk})
    )

    assert response.status_code == 200
    assert response.data['results'][0]['custom_answers']['answers'][0] == {
        'id': 'purpose',
        'label': 'Purpose',
        'type': 'short_text',
        'value': 'Training',
    }


def test_cancelled_reregistration_replaces_contact_and_answers():
    space = make_space('j4-reregister')
    event = make_public_event(space, custom_form=FORM)
    registration = EventRegistration.objects.create(
        event=event,
        name='Old name',
        email='guest@example.com',
        phone='old-phone',
        custom_answers={'version': 1, 'answers': []},
        status=EventRegistration.Status.CANCELLED,
    )

    response = APIClient().post(
        registration_url(space, event),
        registration_payload(
            ' Guest@Example.com ',
            name='New name',
            phone='new-phone',
            custom_answers={'purpose': 'New answer'},
        ),
        format='json',
    )

    assert response.status_code == 201
    registration.refresh_from_db()
    assert (registration.name, registration.email, registration.phone) == (
        'New name',
        'guest@example.com',
        'new-phone',
    )
    assert registration.custom_answers['answers'][0]['value'] == 'New answer'

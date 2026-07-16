from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.events.models import Event, EventRegistration
from apps.events.serializers_public import PUBLIC_EVENT_FIELDS, PublicEventSerializer
from apps.makerspaces.models import Makerspace


pytestmark = pytest.mark.django_db

EXPECTED_FIELDS = {
    'public_token',
    'title',
    'description',
    'starts_at',
    'ends_at',
    'location',
    'capacity',
    'spots_left',
    'status',
}
FORBIDDEN_KEYS = {
    'id',
    'pk',
    'makerspace',
    'makerspace_id',
    'created_by',
    'created_by_id',
    'created_at',
    'updated_at',
    'is_public',
    'registrations',
    'registration_counts',
    'email',
    'phone',
    'name',
    'organizer',
    'waitlisted',
}


def assert_no_public_leak(value, sentinels):
    if isinstance(value, dict):
        for key, nested in value.items():
            assert key.lower() not in FORBIDDEN_KEYS
            assert_no_public_leak(nested, sentinels)
    elif isinstance(value, list):
        for nested in value:
            assert_no_public_leak(nested, sentinels)
    elif isinstance(value, str):
        lowered = value.lower()
        for sentinel in sentinels:
            assert sentinel.lower() not in lowered


def test_public_event_exact_allowlist_and_recursive_sentinel_leak_sweep():
    sentinels = {
        'sentinel-creator',
        'creator-sentinel@example.com',
        'Sentinel Registration Name',
        'registration-sentinel@example.com',
        '+919999999999',
    }
    creator = User.objects.create_user(
        username='sentinel-creator',
        email='creator-sentinel@example.com',
    )
    space = Makerspace.objects.create(name='Leak Space', slug='event-leak-space')
    start = timezone.now() + timedelta(days=1)
    event = Event.objects.create(
        makerspace=space,
        created_by=creator,
        title='Safe public workshop',
        description='<script>alert(1)</script>',
        starts_at=start,
        ends_at=start + timedelta(hours=2),
        location='Main hall',
        capacity=10,
        is_public=True,
        status=Event.Status.PUBLISHED,
    )
    EventRegistration.objects.create(
        event=event,
        name='Sentinel Registration Name',
        email='registration-sentinel@example.com',
        phone='+919999999999',
        status=EventRegistration.Status.WAITLISTED,
    )

    response = APIClient().get(
        reverse(
            'public-event-list',
            kwargs={'makerspace_slug': space.slug},
        )
    )

    assert response.status_code == 200
    assert len(response.data) == 1
    row = response.data[0]
    assert set(PUBLIC_EVENT_FIELDS) == EXPECTED_FIELDS
    assert set(PublicEventSerializer().fields) == EXPECTED_FIELDS
    assert set(row) == EXPECTED_FIELDS
    assert row['public_token'] == str(event.public_token)
    assert row['description'] == '<script>alert(1)</script>'
    assert_no_public_leak(response.data, sentinels)


def test_openapi_has_exact_public_contracts_and_documented_errors():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    components = schema['components']['schemas']
    event_schema = components['PublicEvent']
    input_schema = components['PublicEventRegistrationInput']
    response_schema = components['PublicEventRegistrationResponse']

    assert set(event_schema['properties']) == set(PUBLIC_EVENT_FIELDS)
    assert {'id', 'pk', 'makerspace', 'created_by'} & set(
        event_schema['properties']
    ) == set()
    assert set(input_schema['properties']) == {'name', 'email', 'phone'}
    assert set(input_schema['required']) == {'name', 'email', 'phone'}
    assert all(
        field['writeOnly'] for field in input_schema['properties'].values()
    )
    assert set(response_schema['properties']) == {'status'}

    list_operation = schema['paths'][
        '/api/v1/public/{makerspace_slug}/events/'
    ]['get']
    register_operation = schema['paths'][
        '/api/v1/public/{makerspace_slug}/events/{public_token}/register/'
    ]['post']
    assert list_operation.get('security', []) == []
    assert register_operation.get('security', []) == []
    assert {'201', '400', '404', '409', '429'} <= set(
        register_operation['responses']
    )
    assert register_operation['responses']['201']['content'][
        'application/json'
    ]['schema']['$ref'].endswith('/PublicEventRegistrationResponse')
    assert register_operation['responses']['409']['content'][
        'application/json'
    ]['schema']['$ref'].endswith('/HardwareRequestError')
    for code in ('400', '404', '429'):
        error_schema = register_operation['responses'][code]['content'][
            'application/json'
        ]['schema']
        assert error_schema == {'type': 'object', 'additionalProperties': {}}
    assert '409' not in list_operation['responses']

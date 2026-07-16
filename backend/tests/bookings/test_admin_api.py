from datetime import timedelta

import pytest
from django.urls import resolve, reverse
from django.utils import timezone
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient, APIRequestFactory

from apps.accounts import rbac
from apps.accounts.models import User
from apps.bookings.models import BookableSpace, Booking
from apps.makerspaces import origin_scope
from apps.makerspaces.models import Makerspace, MakerspaceMembership

pytestmark = pytest.mark.django_db


def tenant(slug='booking-admin', **values):
    return Makerspace.objects.create(name=slug, slug=slug, **values)


def user(name, role=User.Role.REQUESTER, **values):
    values.setdefault('access_status', User.AccessStatus.ACTIVE)
    return User.objects.create_user(username=name, role=role, **values)


def grant(actor, makerspace, role=MakerspaceMembership.Role.SPACE_MANAGER):
    return MakerspaceMembership.objects.create(
        user=actor,
        makerspace=makerspace,
        role=role,
    )


def space(makerspace, **values):
    defaults = {'name': 'Development Room', 'is_public': True}
    defaults.update(values)
    return BookableSpace.objects.create(makerspace=makerspace, **defaults)


def booking(bookable_space, **values):
    start = values.pop('starts_at', timezone.now() - timedelta(hours=2))
    defaults = {
        'name': 'Ada',
        'email': 'ada@example.com',
        'phone': '123',
        'starts_at': start,
        'ends_at': start + timedelta(hours=1),
    }
    defaults.update(values)
    return Booking.objects.create(space=bookable_space, **defaults)


def client_for(actor):
    client = APIClient()
    client.force_authenticate(actor)
    return client


def urls(makerspace, bookable_space, row):
    return [
        ('get', reverse('admin-bookable-space-list-create', kwargs={'makerspace_id': makerspace.pk}), None),
        ('post', reverse('admin-bookable-space-list-create', kwargs={'makerspace_id': makerspace.pk}), {'name': 'New'}),
        ('get', reverse('admin-bookable-space-detail', kwargs={'pk': bookable_space.pk}), None),
        ('patch', reverse('admin-bookable-space-detail', kwargs={'pk': bookable_space.pk}), {'name': 'Edit'}),
        ('post', reverse('admin-bookable-space-deactivate', kwargs={'pk': bookable_space.pk}), {}),
        ('post', reverse('admin-bookable-space-image-presign', kwargs={'pk': bookable_space.pk}), {'filename': 'x.png', 'content_type': 'image/png'}),
        ('post', reverse('admin-bookable-space-image-finalize', kwargs={'pk': bookable_space.pk}), {'object_key': 'x'}),
        ('delete', reverse('admin-bookable-space-image-delete', kwargs={'pk': bookable_space.pk}), None),
        ('get', reverse('admin-space-booking-list', kwargs={'pk': bookable_space.pk}), None),
        ('post', reverse('admin-booking-cancel', kwargs={'pk': row.pk}), {}),
        ('post', reverse('admin-booking-complete', kwargs={'pk': row.pk}), {}),
        ('post', reverse('admin-booking-no-show', kwargs={'pk': row.pk}), {}),
    ]


def call(client, method, url, data):
    return getattr(client, method)(url, data=data, format='json')


def test_manage_bookings_grant_delta_is_exact():
    makerspace = tenant()
    allowed = set()
    for role, _label in MakerspaceMembership.Role.choices:
        actor = user(f'booking-{role}')
        grant(actor, makerspace, role)
        if rbac.can(actor, rbac.Action.MANAGE_BOOKINGS, makerspace.pk):
            allowed.add(role)
    root = user('booking-root', role=User.Role.SUPERADMIN, is_superuser=True)
    assert allowed == {MakerspaceMembership.Role.SPACE_MANAGER}
    assert rbac.can(root, rbac.Action.MANAGE_BOOKINGS, makerspace.pk)


def test_every_endpoint_enforces_active_staff_module_and_404_before_403():
    makerspace = tenant('booking-guards')
    bookable_space, row = space(makerspace), None
    row = booking(bookable_space)
    for actor in (
        None,
        user('booking-inactive', is_active=False),
        user('booking-suspended', access_status=User.AccessStatus.SUSPENDED),
        user('booking-outsider'),
    ):
        client = APIClient() if actor is None else client_for(actor)
        assert all(
            call(client, method, url, data).status_code in {401, 403, 404}
            for method, url, data in urls(makerspace, bookable_space, row)
        )
    manager = user('booking-module-manager')
    grant(manager, makerspace)
    makerspace.enabled_modules.remove('bookings')
    makerspace.save(update_fields=['enabled_modules'])
    assert all(
        call(client_for(manager), method, url, data).status_code == 400
        for method, url, data in urls(makerspace, bookable_space, row)
    )


@pytest.mark.parametrize(
    'role',
    [
        MakerspaceMembership.Role.GUEST_ADMIN,
        MakerspaceMembership.Role.INVENTORY_MANAGER,
        MakerspaceMembership.Role.PRINT_MANAGER,
    ],
)
def test_visible_underprivileged_roles_get_403(role):
    makerspace = tenant(f'booking-denied-{role}')
    actor = user(f'booking-denied-user-{role}')
    grant(actor, makerspace, role)
    target = space(makerspace)
    assert client_for(actor).get(
        reverse('admin-bookable-space-detail', kwargs={'pk': target.pk})
    ).status_code == 403


def test_space_crud_allowlist_flags_and_validation():
    makerspace, actor = tenant('booking-write'), user('booking-manager')
    grant(actor, makerspace)
    client = client_for(actor)
    created = client.post(
        reverse('admin-bookable-space-list-create', kwargs={'makerspace_id': makerspace.pk}),
        {
            'name': 'Studio',
            'show_public_availability': True,
            'show_public_booker_names': True,
            'image_key': 'secret',
            'is_active': False,
        },
        format='json',
    )
    assert created.status_code == 201
    assert set(created.data) == {
        'id', 'public_token', 'makerspace_id', 'name', 'kind', 'description',
        'capacity', 'location', 'image_url', 'is_public',
        'show_public_availability', 'show_public_booker_names', 'is_active',
        'created_by_id', 'created_at', 'updated_at',
    }
    assert 'image_key' not in created.data and created.data['is_active'] is True
    invalid = client.patch(
        reverse('admin-bookable-space-detail', kwargs={'pk': created.data['id']}),
        {'show_public_availability': False},
        format='json',
    )
    assert invalid.status_code == 400
    assert invalid.data['code'] == 'booker_names_requires_availability'


def test_booking_list_is_space_scoped_and_lifecycle_is_typed():
    own, other = tenant('booking-own'), tenant('booking-other')
    actor = user('booking-list-manager')
    grant(actor, own)
    own_space, other_space = space(own), space(other)
    own_row, secret = booking(own_space), booking(other_space, email='secret@example.com')
    client = client_for(actor)
    response = client.get(
        reverse('admin-space-booking-list', kwargs={'pk': own_space.pk})
    )
    assert [item['id'] for item in response.data['results']] == [own_row.pk]
    assert response.data['results'][0]['email'] == 'ada@example.com'
    assert secret.email not in str(response.data)
    cancelled = client.post(
        reverse('admin-booking-cancel', kwargs={'pk': own_row.pk}),
        {},
        format='json',
    )
    conflict = client.post(
        reverse('admin-booking-cancel', kwargs={'pk': own_row.pk}),
        {},
        format='json',
    )
    assert cancelled.data['status'] == Booking.Status.CANCELLED
    assert conflict.status_code == 409 and conflict.data['code'] == 'invalid_transition'


def test_staff_urls_origin_registry_and_openapi():
    makerspace = tenant('booking-origin')
    target, row = space(makerspace), None
    row = booking(target)
    factory = APIRequestFactory()
    for _method, url, _data in urls(makerspace, target, row):
        match = resolve(url)
        request = factory.get(url)
        request.resolver_match = match
        view = match.func.view_class(**match.func.view_initkwargs)
        view.kwargs = match.kwargs
        assert origin_scope._target_makerspace_id(request, view) == makerspace.pk
    schema = SchemaGenerator().get_schema(request=None, public=True)
    expected = {
        '/api/v1/admin/makerspaces/{makerspace_id}/spaces/': {'get', 'post'},
        '/api/v1/admin/spaces/{id}/': {'get', 'patch'},
        '/api/v1/admin/spaces/{id}/deactivate/': {'post'},
        '/api/v1/admin/spaces/{id}/image/presign/': {'post'},
        '/api/v1/admin/spaces/{id}/image/finalize/': {'post'},
        '/api/v1/admin/spaces/{id}/image/': {'delete'},
        '/api/v1/admin/spaces/{id}/bookings/': {'get'},
        '/api/v1/admin/bookings/{id}/cancel/': {'post'},
        '/api/v1/admin/bookings/{id}/complete/': {'post'},
        '/api/v1/admin/bookings/{id}/no-show/': {'post'},
    }
    assert all(methods <= schema['paths'][path].keys() for path, methods in expected.items())
    fields = schema['components']['schemas']['BookableSpaceAdmin']['properties']
    assert 'image_key' not in fields
    assert {'show_public_availability', 'show_public_booker_names'} <= fields.keys()

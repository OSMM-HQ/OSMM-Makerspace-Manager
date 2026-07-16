'''Audited mutation boundary for bookable spaces.'''

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from apps.bookings.exceptions import (
    BookerNamesRequiresAvailability,
    BookingInvalidTransition,
)
from apps.bookings.models import BookableSpace
from apps.forms_schema.validation import validate_form_schema
from apps.makerspaces.models import Makerspace


SPACE_FIELDS = frozenset(
    {
        'name', 'kind', 'description', 'capacity', 'location', 'is_public',
        'show_public_availability', 'show_public_booker_names',
        'approval_mode', 'custom_form', 'requester_notifications_enabled',
    }
)


def _canonical_form(value):
    try:
        return validate_form_schema(value)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({'custom_form': exc.messages}) from exc


def _validate(instance):
    try:
        instance.full_clean(validate_unique=False, validate_constraints=False)
    except DjangoValidationError as exc:
        detail = exc.message_dict if hasattr(exc, 'message_dict') else exc.messages
        raise serializers.ValidationError(detail) from exc


def _validate_public_visibility(instance):
    if (
        instance.show_public_booker_names
        and not instance.show_public_availability
    ):
        raise BookerNamesRequiresAvailability()


def _audit(space, actor, action, target, audit_service, meta=None):
    return audit_service.record(
        actor,
        action,
        makerspace=space.makerspace,
        target=target,
        meta=meta or {},
    )


@transaction.atomic
def create_space(
    *, makerspace, actor, name, kind, description, capacity, location, is_public,
    audit_service, show_public_availability=False,
    show_public_booker_names=False,
    approval_mode=BookableSpace.ApprovalMode.INSTANT, custom_form=None,
    requester_notifications_enabled=None,
):
    locked_makerspace = Makerspace.objects.select_for_update().get(pk=makerspace.pk)
    space = BookableSpace(
        makerspace=locked_makerspace,
        created_by=actor,
        name=name,
        kind=kind,
        description=description,
        capacity=capacity,
        location=location,
        is_public=is_public,
        show_public_availability=show_public_availability,
        show_public_booker_names=show_public_booker_names,
        approval_mode=approval_mode,
        custom_form=_canonical_form(custom_form),
        requester_notifications_enabled=requester_notifications_enabled,
        is_active=True,
    )
    _validate_public_visibility(space)
    _validate(space)
    space.save()
    _audit(space, actor, 'booking.space_created', space, audit_service)
    space.refresh_from_db()
    return space


@transaction.atomic
def update_space(space, *, actor, audit_service, **changes):
    locked = (
        BookableSpace.objects.select_for_update()
        .select_related('makerspace')
        .get(pk=space.pk)
    )
    if not locked.is_active:
        raise BookingInvalidTransition('Inactive spaces cannot be updated.')
    unknown = set(changes) - SPACE_FIELDS
    if unknown:
        raise serializers.ValidationError(
            {field: 'This field cannot be updated.' for field in sorted(unknown)}
        )
    if 'custom_form' in changes:
        changes['custom_form'] = _canonical_form(changes['custom_form'])
    for field, value in changes.items():
        setattr(locked, field, value)
    _validate_public_visibility(locked)
    _validate(locked)
    if changes:
        locked.save(update_fields=[*sorted(changes), 'updated_at'])
    _audit(
        locked,
        actor,
        'booking.space_updated',
        locked,
        audit_service,
        {'changed_fields': sorted(changes)},
    )
    locked.refresh_from_db()
    return locked


@transaction.atomic
def deactivate_space(space, *, actor, audit_service):
    locked = (
        BookableSpace.objects.select_for_update()
        .select_related('makerspace')
        .get(pk=space.pk)
    )
    if not locked.is_active:
        raise BookingInvalidTransition('Space is already inactive.')
    locked.is_active = False
    locked.save(update_fields=['is_active', 'updated_at'])
    _audit(
        locked,
        actor,
        'booking.space_deactivated',
        locked,
        audit_service,
        {'old_status': 'active', 'new_status': 'inactive'},
    )
    locked.refresh_from_db()
    return locked

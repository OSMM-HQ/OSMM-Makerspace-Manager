"""Batch resolution of human-readable payment subjects."""

from apps.payments.models import Payment


def resolve_subject_labels(payments):
    rows = list(payments)
    labels = {}
    by_type = {
        subject_type: {
            payment.subject_id
            for payment in rows
            if payment.subject_type == subject_type
        }
        for subject_type in Payment.SubjectType.values
    }

    if ids := by_type[Payment.SubjectType.MACHINE_SERVICE_REQUEST]:
        from apps.machines.models import MachineServiceRequest

        for subject_id, title in MachineServiceRequest.objects.filter(
            pk__in=ids
        ).values_list("pk", "title"):
            labels[(Payment.SubjectType.MACHINE_SERVICE_REQUEST, subject_id)] = (
                title or "Machine service"
            )
    if ids := by_type[Payment.SubjectType.BOOKING]:
        from apps.bookings.models import Booking

        for subject_id, name in Booking.objects.filter(pk__in=ids).values_list(
            "pk", "space__name"
        ):
            labels[(Payment.SubjectType.BOOKING, subject_id)] = name
    if ids := by_type[Payment.SubjectType.EVENT_REGISTRATION]:
        from apps.events.models import EventRegistration

        for subject_id, title in EventRegistration.objects.filter(
            pk__in=ids
        ).values_list("pk", "event__title"):
            labels[(Payment.SubjectType.EVENT_REGISTRATION, subject_id)] = title
    for subject_id in by_type[Payment.SubjectType.MAKERSPACE_MEMBERSHIP]:
        labels[(Payment.SubjectType.MAKERSPACE_MEMBERSHIP, subject_id)] = (
            "Membership dues"
        )
    return labels


def subject_label(payment, labels):
    return labels.get(
        (payment.subject_type, payment.subject_id),
        payment.get_subject_type_display(),
    )

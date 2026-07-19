"""The sole state-transition authority for machine service requests."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.makerspaces import limits
from apps.makerspaces.platform import module_enabled
from apps.machines.models import (
    Machine,
    MachineServiceRequest,
    ServiceBucket,
    get_or_create_default_bucket,
)
from apps.machines.service_consumption import debit_consumptions
from apps.machines.service_emails import notify_service_status
from apps.machines.service_errors import (
    ServiceConsumptionInvalid,
    ServiceInvalidTransition,
    ServiceMachineUnavailable,
)


_ALLOWED = {
    MachineServiceRequest.Status.PENDING: {
        MachineServiceRequest.Status.ACCEPTED,
        MachineServiceRequest.Status.REJECTED,
    },
    MachineServiceRequest.Status.ACCEPTED: {MachineServiceRequest.Status.IN_PROGRESS},
    MachineServiceRequest.Status.IN_PROGRESS: {
        MachineServiceRequest.Status.COMPLETED,
        MachineServiceRequest.Status.FAILED,
    },
    MachineServiceRequest.Status.COMPLETED: {MachineServiceRequest.Status.COLLECTED},
}


def submit(
    bucket_or_machine, requester, *, requester_name, contact_email, contact_phone,
    title, description="", source_link="", actor=None, member=None,
):
    """Create a pending request for an available target machine."""
    with transaction.atomic():
        machine = _locked_submission_machine(bucket_or_machine)
        _require_module(machine.makerspace)
        _require_available(machine)
        limits.check_quota(machine.makerspace, "machine_service_open", adding=1)
        limits.check_quota(machine.makerspace, "machine_service_submit", adding=1)
        bucket = get_or_create_default_bucket(machine, makerspace=machine.makerspace)
        service_request = MachineServiceRequest.objects.create(
            bucket=bucket,
            requester=requester,
            member=member,
            requester_name=(requester_name or "").strip(),
            contact_email=(contact_email or "").strip(),
            contact_phone=(contact_phone or "").strip(),
            title=(title or "").strip(),
            description=(description or "").strip(),
            source_link=(source_link or "").strip(),
            assigned_machine=machine,
        )
        audit.record(
            actor, "machine_service.submitted", makerspace=machine.makerspace,
            target=service_request, meta={"request_id": service_request.pk, "status": service_request.status},
        )
        _notify_after_commit(service_request, "submitted")
        return service_request


def accept(service_request, actor, *, estimated_minutes=None, note=""):
    with transaction.atomic():
        locked = _locked_request(service_request)
        _require_module(locked.bucket.machine.makerspace)
        _require_edge(locked, MachineServiceRequest.Status.ACCEPTED)
        if estimated_minutes is not None:
            locked.estimated_minutes = _minutes(estimated_minutes, "estimated_minutes")
        if note:
            locked.reason = str(note).strip()
        now = timezone.now()
        locked.status = MachineServiceRequest.Status.ACCEPTED
        locked.handled_by = actor
        locked.accepted_by = actor
        locked.accepted_at = now
        locked.save(update_fields=[
            "status", "handled_by", "accepted_by", "accepted_at", "estimated_minutes", "reason", "updated_at",
        ])
        _audit_transition(actor, locked, "accepted")
        _notify_after_commit(locked, "accepted")
        return locked


def reject(service_request, actor, *, reason):
    with transaction.atomic():
        if not str(reason or "").strip():
            raise ServiceConsumptionInvalid("A rejection reason is required.")
        locked = _locked_request(service_request)
        _require_module(locked.bucket.machine.makerspace)
        _require_edge(locked, MachineServiceRequest.Status.REJECTED)
        locked.status = MachineServiceRequest.Status.REJECTED
        locked.handled_by = actor
        locked.reason = str(reason).strip()
        locked.save(update_fields=["status", "handled_by", "reason", "updated_at"])
        _audit_transition(actor, locked, "rejected")
        _notify_after_commit(locked, "rejected")
        return locked


def start(service_request, actor, *, machine_id, estimated_minutes=None):
    with transaction.atomic():
        if machine_id is None:
            raise ServiceMachineUnavailable("A machine is required to start service.")
        locked = _locked_request(service_request)
        _require_module(locked.bucket.machine.makerspace)
        _require_edge(locked, MachineServiceRequest.Status.IN_PROGRESS)
        machine = Machine.objects.select_for_update().select_related("makerspace").filter(pk=machine_id).first()
        if machine is None or machine.makerspace_id != locked.bucket.machine.makerspace_id:
            raise ServiceMachineUnavailable("Machine is not available for this service request.")
        _require_available(machine)
        if estimated_minutes is not None:
            locked.estimated_minutes = _minutes(estimated_minutes, "estimated_minutes")
        locked.assigned_machine = machine
        locked.status = MachineServiceRequest.Status.IN_PROGRESS
        locked.handled_by = actor
        locked.started_at = timezone.now()
        locked.save(update_fields=[
            "assigned_machine", "status", "handled_by", "started_at", "estimated_minutes", "updated_at",
        ])
        _audit_transition(actor, locked, "assigned", extra={"machine_id": machine.pk})
        _audit_transition(actor, locked, "started")
        _notify_after_commit(locked, "started")
        return locked


def complete(service_request, actor, *, actual_minutes, consumptions):
    with transaction.atomic():
        locked = _locked_request(service_request)
        _require_module(locked.bucket.machine.makerspace)
        _require_edge(locked, MachineServiceRequest.Status.COMPLETED)
        _lock_assigned_machine(locked)
        locked.actual_minutes = _minutes(actual_minutes, "actual_minutes")
        debit_consumptions(locked, actor, consumptions, outcome="completed")
        locked.status = MachineServiceRequest.Status.COMPLETED
        locked.handled_by = actor
        locked.completed_at = timezone.now()
        locked.save(update_fields=["status", "handled_by", "actual_minutes", "completed_at", "updated_at"])
        _audit_transition(actor, locked, "completed")
        _notify_after_commit(locked, "completed")
        return locked


def fail(service_request, actor, *, reason, percent_complete, actual_minutes, consumptions):
    with transaction.atomic():
        if not str(reason or "").strip():
            raise ServiceConsumptionInvalid("A failure reason is required.")
        locked = _locked_request(service_request)
        _require_module(locked.bucket.machine.makerspace)
        _require_edge(locked, MachineServiceRequest.Status.FAILED)
        _lock_assigned_machine(locked)
        locked.actual_minutes = _minutes(actual_minutes, "actual_minutes")
        locked.fail_percent_complete = _percent(percent_complete)
        locked.reason = str(reason).strip()
        locked.failed_at = timezone.now()
        debit_consumptions(locked, actor, consumptions, outcome="failed")
        locked.status = MachineServiceRequest.Status.FAILED
        locked.handled_by = actor
        locked.save(update_fields=[
            "status", "handled_by", "actual_minutes", "fail_percent_complete", "reason", "failed_at", "updated_at",
        ])
        _audit_transition(actor, locked, "failed")
        _notify_after_commit(locked, "failed")
        return locked


def collect(service_request, actor):
    with transaction.atomic():
        locked = _locked_request(service_request)
        _require_module(locked.bucket.machine.makerspace)
        _require_edge(locked, MachineServiceRequest.Status.COLLECTED)
        locked.status = MachineServiceRequest.Status.COLLECTED
        locked.handled_by = actor
        locked.collected_by = actor
        locked.collected_at = timezone.now()
        locked.save(update_fields=["status", "handled_by", "collected_by", "collected_at", "updated_at"])
        _audit_transition(actor, locked, "collected")
        _notify_after_commit(locked, "collected")
        return locked


def _locked_submission_machine(bucket_or_machine):
    if isinstance(bucket_or_machine, ServiceBucket):
        bucket = ServiceBucket.objects.select_related("machine__makerspace").get(pk=bucket_or_machine.pk)
        return Machine.objects.select_for_update().select_related("makerspace").get(pk=bucket.machine_id)
    return Machine.objects.select_for_update().select_related("makerspace").get(pk=bucket_or_machine.pk)


def _locked_request(service_request):
    return MachineServiceRequest.objects.select_for_update(of=("self",)).select_related(
        "bucket__machine__makerspace", "requester", "assigned_machine"
    ).get(pk=service_request.pk)


def _lock_assigned_machine(service_request):
    if not service_request.assigned_machine_id:
        raise ServiceMachineUnavailable("No machine is assigned to this service request.")
    return Machine.objects.select_for_update().get(pk=service_request.assigned_machine_id)


def _require_available(machine):
    if not machine.is_active or machine.status != Machine.Status.IDLE:
        raise ServiceMachineUnavailable("Machine is not available for service requests.")


def _require_module(makerspace):
    if not module_enabled(makerspace, "machine_service"):
        raise ValidationError("Machine service is disabled for this makerspace.")


def _require_edge(service_request, next_status):
    if next_status not in _ALLOWED.get(service_request.status, set()):
        raise ServiceInvalidTransition(
            f"Cannot transition machine service request from {service_request.status} to {next_status}."
        )


def _minutes(value, field):
    if isinstance(value, bool):
        raise ServiceConsumptionInvalid(f"{field} must be a non-negative whole number.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ServiceConsumptionInvalid(f"{field} must be a non-negative whole number.") from exc
    if parsed < 0 or str(value).strip() not in {str(parsed), f"{parsed}.0"}:
        raise ServiceConsumptionInvalid(f"{field} must be a non-negative whole number.")
    return parsed


def _percent(value):
    parsed = _minutes(value, "percent_complete")
    if parsed > 100:
        raise ServiceConsumptionInvalid("percent_complete must be between 0 and 100.")
    return parsed


def _audit_transition(actor, service_request, event, extra=None):
    meta = {
        "request_id": service_request.pk,
        "status": service_request.status,
        "estimated_minutes": service_request.estimated_minutes,
        "actual_minutes": service_request.actual_minutes,
    }
    if extra:
        meta.update(extra)
    audit.record(
        actor, f"machine_service.{event}",
        makerspace=service_request.bucket.machine.makerspace,
        target=service_request, meta=meta,
    )


def _notify_after_commit(service_request, event):
    request_id = service_request.pk
    transaction.on_commit(lambda: notify_service_status(
        MachineServiceRequest.objects.select_related("bucket__machine__makerspace").get(pk=request_id), event
    ))

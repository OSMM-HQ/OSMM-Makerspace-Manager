"""Purge hooks for private machine-service request data."""


def collect_private_object_keys(makerspace, add):
    from apps.machines.models import ServiceRequestFile

    for key in ServiceRequestFile.objects.filter(
        machine__makerspace=makerspace
    ).values_list("object_key", flat=True):
        add(key)


def delete_for_makerspace(makerspace, cursor):
    """Clear N1 rows in dependency order inside the authorized purge context."""
    from apps.machines.models import (
        MachineServiceRequest,
        ServiceBucket,
        ServiceRequestFile,
    )

    # The ledger has both ORM and DB append-only guards; raw SQL is intentional
    # here because lifecycle.purge has enabled its transaction-scoped bypass.
    cursor.execute(
        "DELETE FROM machines_servicerequestconsumption "
        "WHERE service_request_id IN ("
        "SELECT request.id FROM machines_machineservicerequest request "
        "JOIN machines_servicebucket bucket ON request.bucket_id = bucket.id "
        "JOIN machines_machine machine ON bucket.machine_id = machine.id "
        "WHERE machine.makerspace_id = %s)",
        [makerspace.id],
    )
    ServiceRequestFile.objects.filter(machine__makerspace=makerspace).delete()
    MachineServiceRequest.objects.filter(bucket__machine__makerspace=makerspace).delete()
    ServiceBucket.objects.filter(machine__makerspace=makerspace).delete()

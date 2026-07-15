from django.shortcuts import get_object_or_404

from apps.machines.access import scope_machines_for_actor
from apps.machines.models import Machine, MachineDocument


def resolve_machine(user, pk):
    return get_object_or_404(
        scope_machines_for_actor(
            user,
            Machine.objects.select_related('makerspace', 'machine_type').all(),
        ),
        pk=pk,
    )


def resolve_machine_document(user, pk):
    machines = scope_machines_for_actor(user, Machine.objects.all())
    return get_object_or_404(
        MachineDocument.objects.select_related(
            'machine',
            'machine__makerspace',
            'machine__machine_type',
        ).filter(machine__in=machines),
        pk=pk,
    )

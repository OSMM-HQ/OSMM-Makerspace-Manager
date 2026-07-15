from django.db.models import Sum

from apps.machines.models import MachineUsageEntry
from apps.makerspaces.platform import module_enabled


def build_public_machine_stats(makerspace):
    if not module_enabled(makerspace, 'machines'):
        return None
    total = MachineUsageEntry.objects.filter(
        machine__makerspace=makerspace,
        machine__is_public=True,
        machine__is_active=True,
    ).aggregate(total=Sum('hours'))['total']
    return {'usage_hours': round(float(total or 0), 2)}

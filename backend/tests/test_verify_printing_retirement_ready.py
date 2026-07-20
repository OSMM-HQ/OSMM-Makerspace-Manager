import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.machines.models import PrintingCutoverState
from apps.printing.models import PrintBucket
from tests.return_helpers import make_space


pytestmark = pytest.mark.django_db


def test_retirement_guard_is_ready_when_every_candidate_is_flipped():
    makerspace = make_space("printing-retirement-ready")
    makerspace.enabled_modules = ["printing", "machine_service"]
    makerspace.save(update_fields=["enabled_modules"])
    PrintingCutoverState.objects.create(
        makerspace=makerspace, kernel_authoritative_at=timezone.now(),
    )

    call_command("verify_printing_retirement_ready")


def test_retirement_guard_reports_unflipped_tenant_with_legacy_data():
    makerspace = make_space("printing-retirement-unflipped")
    PrintBucket.objects.create(makerspace=makerspace, name="Retained legacy queue")

    with pytest.raises(CommandError, match="printing-retirement-unflipped"):
        call_command("verify_printing_retirement_ready")


def test_no_runtime_module_imports_legacy_printing_package():
    from pathlib import Path

    apps_root = Path(__file__).resolve().parents[1] / "apps"
    allowed_legacy_imports = {"makerspaces/lifecycle.py"}
    offenders = []
    for path in apps_root.rglob("*.py"):
        relative = path.relative_to(apps_root)
        if relative.parts[0] == "printing" or "migrations" in relative.parts:
            continue
        if (
            "apps.printing" in path.read_text(encoding="utf-8")
            and relative.as_posix() not in allowed_legacy_imports
        ):
            offenders.append(str(relative))
    assert offenders == []
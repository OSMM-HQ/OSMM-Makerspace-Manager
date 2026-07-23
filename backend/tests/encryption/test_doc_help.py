"""Operator-facing command help and documented encryption settings stay usable."""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import get_commands, load_command_class


def test_every_encryption_command_builds_help_parser():
    commands = get_commands()
    names = sorted(name for name, app in commands.items() if app == "apps.encryption")
    assert names
    for name in names:
        command = load_command_class("apps.encryption", name)
        parser = command.create_parser("manage.py", name)
        assert "--help" in parser.format_help()


def test_runbook_pii_settings_are_real_django_settings():
    runbook = Path(__file__).resolve().parents[3] / "docs" / "scoped-pii-encryption.md"
    names = set(re.findall(r"\bPII_[A-Z0-9_]+\b", runbook.read_text(encoding="utf-8")))
    assert names
    missing = sorted(name for name in names if not hasattr(settings, name))
    assert not missing, f"runbook references unknown settings: {missing}"

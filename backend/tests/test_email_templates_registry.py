import importlib
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError
from django.template import Context, Template

from apps.hardware_requests.models import HardwareEmailTemplate
from apps.hardware_requests.notifications import DEFAULT_TEMPLATES
from apps.hardware_requests.staff_notifications import STAFF_TEMPLATES
from apps.integrations.email_templates_registry import (
    REGISTRY,
    all_send_keys,
    get_entry,
    iter_entries,
    validate_email_template_strings,
)
from apps.integrations.models import EmailTemplate
from apps.makerspaces.models import Makerspace
from apps.printing.emails import _STAFF_SUBJECTS, _SUBJECTS, _staff_print_body


def _key_value(key):
    return key.value if hasattr(key, "value") else key


def test_registry_declares_all_send_path_keys():
    expected = {
        *{
            ("hardware", "requester", _key_value(key))
            for key in DEFAULT_TEMPLATES.keys()
        },
        *{("hardware", "staff", key) for key in STAFF_TEMPLATES.keys()},
        *{("printing", "requester", key) for key in _SUBJECTS.keys()},
        *{("printing", "staff", key) for key in _STAFF_SUBJECTS.keys()},
    }

    assert len(REGISTRY) == 27
    assert all_send_keys() == expected


def test_registry_default_templates_render_against_sample_context():
    for key, entry in iter_entries():
        context = Context(entry.sample_context, autoescape=True)
        Template(entry.default_subject).render(context).strip()
        Template(entry.default_text).render(context)
        if entry.default_html:
            Template(entry.default_html).render(context)

        assert get_entry(*key) is entry


def test_registry_spot_checks_current_default_shapes():
    printing_html = get_entry("printing", "requester", "submitted").default_html
    hardware_staff_text = get_entry("hardware", "staff", "submitted").default_text

    assert printing_html.startswith('{% extends "email/base.html" %}')
    assert "{{ staff_summary }}" in hardware_staff_text


def test_printing_staff_default_text_matches_current_body_helper():
    requester = SimpleNamespace(username="alex", email="alex.account@example.com")
    print_request = SimpleNamespace(
        pk=73,
        id=73,
        status="accepted",
        title="Replacement gear",
        requester_name="Alex Maker",
        requester=requester,
        contact_email="alex@example.com",
        contact_phone="+15550101010",
        material="PLA",
        color="Black",
        quantity=2,
        reason="Prototype needs a tighter tolerance",
        reprint_of_id=64,
    )

    for event in _STAFF_SUBJECTS.keys():
        entry = get_entry("printing", "staff", event)
        context = Context({"print_request": print_request}, autoescape=True)
        assert Template(entry.default_text).render(context) == _staff_print_body(
            event,
            print_request,
        )


def test_validator_rejects_unknown_registry_key():
    with pytest.raises(ValidationError):
        validate_email_template_strings(
            "hardware",
            "requester",
            "not_real",
            "Subject",
            "Text",
            "",
        )


def test_validator_rejects_invalid_template_syntax():
    with pytest.raises(ValidationError, match="Email template has invalid syntax"):
        validate_email_template_strings(
            "hardware",
            "requester",
            "request_received",
            "Subject",
            "{{ broken syntax %}",
            "",
        )


@pytest.mark.django_db
def test_email_template_full_clean_rejects_invalid_subject_syntax():
    makerspace = Makerspace.objects.create(name="Template Lab", slug="template-lab")
    template = EmailTemplate(
        makerspace=makerspace,
        stream=EmailTemplate.Stream.HARDWARE,
        audience=EmailTemplate.Audience.REQUESTER,
        key="request_received",
        subject="{{ broken syntax %}",
        text_body="Text",
    )

    with pytest.raises(ValidationError, match="Email template has invalid syntax"):
        template.full_clean()


@pytest.mark.django_db
def test_hardware_email_template_data_migration_copies_rows():
    makerspace = Makerspace.objects.create(name="Migration Lab", slug="migration-lab")
    old_template = HardwareEmailTemplate.objects.create(
        makerspace=makerspace,
        key=HardwareEmailTemplate.Key.REQUEST_ACCEPTED,
        subject="Accepted {{ request.id }}",
        text_body="Accepted text",
        html_body="<p>Accepted</p>",
        is_active=False,
    )
    migration = importlib.import_module(
        "apps.integrations.migrations.0003_migrate_hardware_email_templates"
    )

    class Apps:
        @staticmethod
        def get_model(app_label, model_name):
            return {
                ("hardware_requests", "HardwareEmailTemplate"): HardwareEmailTemplate,
                ("integrations", "EmailTemplate"): EmailTemplate,
            }[(app_label, model_name)]

    migration.forwards(Apps, None)
    migration.forwards(Apps, None)

    copied = EmailTemplate.objects.get(
        makerspace=makerspace,
        stream="hardware",
        audience="requester",
        key=old_template.key,
    )
    assert copied.subject == old_template.subject
    assert copied.text_body == old_template.text_body
    assert copied.html_body == old_template.html_body
    assert copied.is_active is False
    assert (
        EmailTemplate.objects.filter(
            makerspace=makerspace,
            stream="hardware",
            audience="requester",
            key=old_template.key,
        ).count()
        == 1
    )

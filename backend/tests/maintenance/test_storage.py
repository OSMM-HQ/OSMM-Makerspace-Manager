from types import SimpleNamespace

import pytest
from rest_framework.exceptions import ValidationError

from apps.maintenance import storage


def test_log_key_has_exact_machine_prefix_and_validates_extensions(settings):
    settings.MACHINE_DOC_ALLOWED_MIME = [
        "application/pdf", "image/jpeg", "image/png", "image/webp",
    ]
    key = storage.log_document_object_key(4, 9, ".PDF")
    assert key.startswith("machines/4/9/logs/")
    assert key.endswith(".pdf")
    storage.assert_log_document_object_key(key, 4, 9)
    assert storage.ext_for("image/jpeg", "PHOTO.JPEG") == "jpeg"
    with pytest.raises(ValidationError):
        storage.log_document_object_key(4, 9, "exe")
    with pytest.raises(ValidationError):
        storage.assert_log_document_object_key(key, 4, 10)


def test_finalize_sniffs_bytes_and_rejects_extension_mismatch(monkeypatch, settings):
    settings.MACHINE_DOC_ALLOWED_MIME = [
        "application/pdf", "image/jpeg", "image/png", "image/webp",
    ]
    settings.MACHINE_DOC_MAX_BYTES = 1024
    monkeypatch.setattr(storage, "object_size", lambda key: 10)
    body = SimpleNamespace(read=lambda limit: b"%PDF-1.7")
    monkeypatch.setattr(
        storage, "_client",
        lambda: SimpleNamespace(get_object=lambda **kwargs: {"Body": body}),
    )
    result = storage.validate_log_document_object(
        "machines/1/2/logs/file.pdf",
    )
    assert result.size == 10
    with pytest.raises(ValidationError):
        storage.validate_log_document_object(
            "machines/1/2/logs/file.png",
        )

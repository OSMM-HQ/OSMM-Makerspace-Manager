from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image
from rest_framework.exceptions import ValidationError

from apps.maintenance import storage
from apps.maker_file_formats import ALLOWED_EXTENSIONS_BY_MIME


def image_bytes():
    stream = BytesIO()
    Image.new("RGB", (2, 2), "blue").save(stream, format="PNG")
    return stream.getvalue()


def mock_object(monkeypatch, settings, data, content_type, size=None):
    settings.MACHINE_DOC_MAX_BYTES = 1024 * 1024
    monkeypatch.setattr(storage, "object_size", lambda key: len(data) if size is None else size)
    monkeypatch.setattr(
        storage,
        "_client",
        lambda: SimpleNamespace(
            get_object=lambda **kwargs: {
                "Body": BytesIO(data),
                "ContentType": content_type,
            }
        ),
    )


ALL_CONFIGURED_PAIRS = [
    (ext, mime)
    for mime, extensions in ALLOWED_EXTENSIONS_BY_MIME.items()
    for ext in extensions
]


def test_log_key_has_exact_machine_prefix_and_validates_extensions():
    key = storage.log_document_object_key(4, 9, ".STL")
    assert key.startswith("machines/4/9/logs/")
    assert key.endswith(".stl")
    storage.assert_log_document_object_key(key, 4, 9)
    with pytest.raises(ValidationError):
        storage.log_document_object_key(4, 9, "exe")
    with pytest.raises(ValidationError):
        storage.assert_log_document_object_key(key, 4, 10)


@pytest.mark.parametrize(("ext", "content_type"), ALL_CONFIGURED_PAIRS)
def test_ext_for_accepts_every_configured_pair(ext, content_type):
    assert storage.ext_for(content_type, f"PART.{ext.upper()}") == ext


@pytest.mark.parametrize(
    ("content_type", "filename"),
    [
        ("application/x-msdownload", "part.exe"),
        ("model/stl", "part.dxf"),
        ("application/dxf", "part.stl"),
    ],
)
def test_ext_for_rejects_unknown_and_mismatched_pairs(content_type, filename):
    with pytest.raises(ValidationError):
        storage.ext_for(content_type, filename)


DOCUMENT_OBJECTS = [
    ("pdf", "application/pdf", b"%PDF-1.7"),
    ("png", "image/png", image_bytes()),
    ("stl", "model/stl", b"solid cube"),
    ("3mf", "model/3mf", b"PK\x03\x04archive"),
    ("step", "application/step", b"ISO-10303-21"),
    ("stp", "model/step", b"iso-10303-21"),
    ("obj", "model/obj", b"v 0 0 0"),
    ("amf", "model/amf", b"<amf/>"),
    ("ply", "model/ply", b"ply"),
    ("gcode", "text/x.gcode", b"G28"),
    ("gco", "application/x-gcode", b"G1 X1"),
    ("iges", "application/iges", b"IGES"),
    ("igs", "model/iges", b"IGES"),
    ("dxf", "application/x-dxf", b"SECTION"),
]


@pytest.mark.parametrize(("ext", "content_type", "data"), DOCUMENT_OBJECTS)
def test_validate_log_document_accepts_all_format_families(
    monkeypatch, settings, ext, content_type, data
):
    mock_object(monkeypatch, settings, data, content_type)
    result = storage.validate_log_document_object(f"machines/1/2/logs/file.{ext}")
    assert result.size == len(data)
    assert result.content_type == content_type


@pytest.mark.parametrize(
    ("ext", "content_type", "data"),
    [
        ("3mf", "model/3mf", b"not zip"),
        ("step", "application/step", b"not STEP"),
        ("stp", "model/step", b"not STEP"),
        ("pdf", "application/pdf", b"not PDF"),
        ("stl", "model/stl", b"%PDF-1.7"),
    ],
)
def test_validate_log_document_rejects_bad_signatures_and_disguised_files(
    monkeypatch, settings, ext, content_type, data
):
    mock_object(monkeypatch, settings, data, content_type)
    with pytest.raises(ValidationError):
        storage.validate_log_document_object(f"machines/1/2/logs/file.{ext}")


def test_validate_log_document_rejects_stored_mime_mismatch(monkeypatch, settings):
    mock_object(monkeypatch, settings, b"solid cube", "application/dxf")
    with pytest.raises(ValidationError):
        storage.validate_log_document_object("machines/1/2/logs/file.stl")


@pytest.mark.parametrize("size", [None, 0, 1025])
def test_validate_log_document_rejects_missing_empty_and_oversize(
    monkeypatch, settings, size
):
    settings.MACHINE_DOC_MAX_BYTES = 1024
    monkeypatch.setattr(storage, "object_size", lambda key: size)
    monkeypatch.setattr(storage, "_client", lambda: pytest.fail("object must not be read"))
    with pytest.raises(ValidationError):
        storage.validate_log_document_object("machines/1/2/logs/file.stl")

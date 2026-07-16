from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image
from rest_framework.exceptions import ValidationError

from apps.machines import storage
from apps.maker_file_formats import ALLOWED_EXTENSIONS_BY_MIME


def image_bytes(image_format):
    stream = BytesIO()
    Image.new("RGB", (2, 2), "red").save(stream, format=image_format)
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


@pytest.mark.parametrize(("ext", "content_type"), ALL_CONFIGURED_PAIRS)
def test_ext_for_accepts_every_configured_extension_mime_pair(ext, content_type):
    assert storage.ext_for(content_type, f"folder/part.{ext}") == ext


def test_ext_for_is_case_insensitive_for_extension():
    assert storage.ext_for("model/stl", "PART.STL") == "stl"


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


MAKER_OBJECTS = [
    ("stl", "model/stl", b"solid cube"),
    ("3mf", "model/3mf", b"PK\x03\x04archive"),
    ("step", "application/step", b"HEADER; FILE_SCHEMA; ISO-10303-21;"),
    ("stp", "model/step", b"iso-10303-21;"),
    ("obj", "model/obj", b"v 0 0 0\nf 1 1 1"),
    ("amf", "application/x-amf", b"<amf></amf>"),
    ("ply", "model/ply", b"ply\nformat ascii 1.0"),
    ("gcode", "text/x.gcode", b"G28\nG1 X10"),
    ("gco", "application/x-gcode", b"G1 X1 Y1"),
    ("iges", "application/iges", b"IGES data"),
    ("igs", "model/iges", b"IGES data"),
    ("dxf", "application/dxf", b"SECTION\nENTITIES"),
]


@pytest.mark.parametrize(("ext", "content_type", "data"), MAKER_OBJECTS)
def test_validate_machine_object_accepts_maker_formats(
    monkeypatch, settings, ext, content_type, data
):
    mock_object(monkeypatch, settings, data, content_type)

    result = storage.validate_machine_object(f"machines/1/file.{ext}")

    assert result.size == len(data)
    assert result.content_type == content_type


@pytest.mark.parametrize("ext", ["step", "stp"])
def test_validate_machine_object_rejects_missing_step_signature(monkeypatch, settings, ext):
    mock_object(monkeypatch, settings, b"not a STEP file", "application/octet-stream")
    with pytest.raises(ValidationError):
        storage.validate_machine_object(f"machines/1/file.{ext}")


def test_validate_machine_object_rejects_missing_3mf_zip_magic(monkeypatch, settings):
    mock_object(monkeypatch, settings, b"not a zip", "model/3mf")
    with pytest.raises(ValidationError):
        storage.validate_machine_object("machines/1/file.3mf")


STRICT_OBJECTS = [
    ("pdf", "application/pdf", b"%PDF-1.7\n"),
    ("jpg", "image/jpeg", image_bytes("JPEG")),
    ("jpeg", "image/jpeg", image_bytes("JPEG")),
    ("png", "image/png", image_bytes("PNG")),
    ("webp", "image/webp", image_bytes("WEBP")),
]


@pytest.mark.parametrize(("ext", "content_type", "data"), STRICT_OBJECTS)
def test_validate_machine_object_returns_sniffed_strict_mime(
    monkeypatch, settings, ext, content_type, data
):
    mock_object(monkeypatch, settings, data, content_type)
    result = storage.validate_machine_object(f"machines/1/file.{ext}")
    assert result.content_type == content_type


@pytest.mark.parametrize(
    ("ext", "content_type", "data"),
    [
        ("pdf", "application/pdf", b"random bytes"),
        ("png", "image/png", b"%PDF-1.7"),
        ("stl", "model/stl", b"%PDF-1.7"),
        ("stl", "model/stl", image_bytes("JPEG")),
    ],
)
def test_validate_machine_object_rejects_malformed_or_disguised_strict_files(
    monkeypatch, settings, ext, content_type, data
):
    mock_object(monkeypatch, settings, data, content_type)
    with pytest.raises(ValidationError):
        storage.validate_machine_object(f"machines/1/file.{ext}")


def test_validate_machine_object_rejects_stored_mime_mismatch(monkeypatch, settings):
    mock_object(monkeypatch, settings, b"solid cube", "application/dxf")
    with pytest.raises(ValidationError):
        storage.validate_machine_object("machines/1/file.stl")


@pytest.mark.parametrize("size", [None, 0, 1025])
def test_validate_machine_object_rejects_missing_empty_and_oversize(
    monkeypatch, settings, size
):
    settings.MACHINE_DOC_MAX_BYTES = 1024
    monkeypatch.setattr(storage, "object_size", lambda key: size)
    monkeypatch.setattr(storage, "_client", lambda: pytest.fail("object must not be read"))
    with pytest.raises(ValidationError):
        storage.validate_machine_object("machines/1/file.stl")


def test_public_and_evidence_upload_allowlists_remain_image_only(settings):
    image_mimes = {"image/jpeg", "image/png", "image/webp"}
    assert set(settings.EVIDENCE_ALLOWED_MIME) == image_mimes
    assert set(settings.PUBLIC_IMAGE_ALLOWED_MIME) == image_mimes

import re

import pytest

from apps.printing.models import PrintRequestFile
from apps.printing.storage import (
    presigned_print_upload,
    print_object_key,
    validate_print_model_object,
    validate_print_upload,
)
from tests.test_printing import make_bucket, make_request, make_space, make_user

pytestmark = pytest.mark.django_db


def test_print_object_key_returns_expected_shape():
    key = print_object_key(42, "stl")

    assert re.fullmatch(r"print/42/stl/[0-9a-f]{32}", key)


def test_validate_print_upload_accepts_allowed_model_and_screenshot():
    assert (
        validate_print_upload("stl", "part.stl", "application/octet-stream")
        == "application/octet-stream"
    )
    assert validate_print_upload("screenshot", "shot.png", "image/png") == "image/png"


@pytest.mark.parametrize(
    ("kind", "filename", "content_type"),
    [
        ("stl", "evil.exe", "application/octet-stream"),
        ("screenshot", "x.png", "application/pdf"),
        ("bogus", "a.stl", ""),
    ],
)
def test_validate_print_upload_rejects_bad_input(kind, filename, content_type):
    with pytest.raises(ValueError):
        validate_print_upload(kind, filename, content_type)


NEW_MODEL_PAIRS = [
    ("amf", "model/amf"),
    ("ply", "model/ply"),
    ("gcode", "text/x.gcode"),
    ("gco", "application/x-gcode"),
    ("iges", "application/iges"),
    ("igs", "model/iges"),
    ("dxf", "application/dxf"),
]


@pytest.mark.parametrize(
    ("ext", "content_type"),
    [pair for ext, mime in NEW_MODEL_PAIRS for pair in [(ext, mime), (ext, "application/octet-stream")]],
)
def test_validate_print_upload_accepts_new_formats_with_specific_and_fallback_mime(
    ext, content_type
):
    assert validate_print_upload("stl", f"part.{ext}", content_type) == content_type


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [("part.dxf", "model/stl"), ("part.stl", "application/dxf")],
)
def test_validate_print_upload_rejects_cross_format_mime_mismatch(filename, content_type):
    with pytest.raises(ValueError):
        validate_print_upload("stl", filename, content_type)


@pytest.mark.parametrize(("ext", "content_type"), NEW_MODEL_PAIRS)
def test_validate_print_model_object_accepts_new_formats(
    monkeypatch, ext, content_type
):
    monkeypatch.setattr("apps.printing.storage._print_object_prefix", lambda key: b"data")
    validate_print_model_object("object", f"part.{ext}", content_type, 100)


@pytest.mark.parametrize(
    ("ext", "content_type", "data", "size"),
    [
        ("stl", "model/stl", b"solid cube", 10),
        ("stl", "application/octet-stream", b"binary", 84),
        ("3mf", "model/3mf", b"PK\x03\x04archive", 20),
        ("step", "application/step", b"ISO-10303-21", 20),
        ("stp", "model/step", b"iso-10303-21", 20),
        ("obj", "model/obj", b"v 0 0 0\nf 1 1 1", 20),
    ],
)
def test_validate_print_model_object_preserves_signature_checks(
    monkeypatch, ext, content_type, data, size
):
    monkeypatch.setattr("apps.printing.storage._print_object_prefix", lambda key: data)
    validate_print_model_object("object", f"part.{ext}", content_type, size)


@pytest.mark.parametrize(
    ("ext", "content_type", "data"),
    [
        ("stl", "model/stl", b"not an STL"),
        ("3mf", "model/3mf", b"not a ZIP"),
        ("step", "application/step", b"not STEP"),
        ("obj", "model/obj", b"not OBJ"),
    ],
)
def test_validate_print_model_object_rejects_invalid_signatures(
    monkeypatch, ext, content_type, data
):
    monkeypatch.setattr("apps.printing.storage._print_object_prefix", lambda key: data)
    with pytest.raises(ValueError):
        validate_print_model_object("object", f"part.{ext}", content_type, 101)


def test_validate_print_model_object_rejects_unknown_extension_before_read(monkeypatch):
    monkeypatch.setattr(
        "apps.printing.storage._print_object_prefix",
        lambda key: pytest.fail("unknown extension must not be read"),
    )
    with pytest.raises(ValueError):
        validate_print_model_object("object", "part.exe", "application/octet-stream", 10)


def test_presigned_print_upload_put_mode_returns_method_and_headers(monkeypatch, settings):
    settings.STORAGE_PRESIGN_METHOD = "put"

    class FakePublicClient:
        def generate_presigned_url(self, operation, Params, ExpiresIn):
            assert operation == "put_object"
            # PUT mode signs the STAGING key; the final key is written server-side
            # at finalize (write-once), never handed to the client.
            assert Params == {
                "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
                "Key": "staging/print/1/stl/object",
                "ContentType": "application/octet-stream",
            }
            assert ExpiresIn == settings.PRINT_URL_TTL_SECONDS
            return "http://minio/print-put"

    monkeypatch.setattr(
        "apps.printing.storage._public_client",
        lambda: FakePublicClient(),
    )

    upload = presigned_print_upload("print/1/stl/object", "application/octet-stream")

    assert upload == {
        "url": "http://minio/print-put",
        "method": "PUT",
        "headers": {"Content-Type": "application/octet-stream"},
    }


def test_print_request_file_can_be_created_unattached():
    makerspace = make_space("printing-storage-files")
    bucket = make_bucket(makerspace)
    requester = make_user("printing-storage-requester")
    make_request(bucket, requester)

    upload = PrintRequestFile.objects.create(
        print_request=None,
        makerspace=makerspace,
        kind=PrintRequestFile.Kind.STL,
        object_key="print/1/stl/abc123",
        content_type="application/octet-stream",
        size_bytes=123,
        owner_checkin_user_id="checkin-user-1",
    )

    assert upload.print_request is None
    assert upload.attached_at is None
    assert upload.makerspace == makerspace

from botocore.exceptions import ClientError

from apps.evidence import storage as evidence_storage
from apps.evidence.responses import storage_unavailable_response
from apps.inventory import public_image_storage
from apps.machines import service_storage


def test_object_size_uses_one_head_call(settings, monkeypatch):
    settings.AWS_STORAGE_BUCKET_NAME = "evidence"
    settings.PUBLIC_IMAGE_BUCKET = "public"
    clients = {
        "evidence": _head_client(123),
        "public": _head_client(456),
        "machine_service": _head_client(789),
    }
    monkeypatch.setattr(evidence_storage, "_client", lambda: clients["evidence"])
    monkeypatch.setattr(public_image_storage, "_client", lambda: clients["public"])
    monkeypatch.setattr(service_storage, "_client", lambda: clients["machine_service"])

    assert evidence_storage.object_size("a") == 123
    assert public_image_storage.object_size("b") == 456
    assert service_storage.object_size("c") == 789
    assert clients["evidence"].calls == 1
    assert clients["public"].calls == 1
    assert clients["machine_service"].calls == 1


def test_object_size_missing_object_returns_none(settings, monkeypatch):
    settings.AWS_STORAGE_BUCKET_NAME = "evidence"
    client = _missing_head_client()
    monkeypatch.setattr(evidence_storage, "_client", lambda: client)

    assert evidence_storage.object_size("missing") is None
    assert client.calls == 1


def test_storage_unavailable_response_has_typed_body():
    response = storage_unavailable_response()

    assert response.status_code == 503
    assert response.data == {"detail": "Storage is unavailable.", "code": "storage_unavailable"}


class _head_client:
    def __init__(self, size):
        self.size = size
        self.calls = 0

    def head_object(self, **kwargs):
        self.calls += 1
        return {"ContentLength": self.size}


class _missing_head_client:
    calls = 0

    def head_object(self, **kwargs):
        self.calls += 1
        raise ClientError(
            {"ResponseMetadata": {"HTTPStatusCode": 404}, "Error": {"Code": "404"}},
            "HeadObject",
        )
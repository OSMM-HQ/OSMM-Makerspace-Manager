import pytest

from apps.evidence import storage as evidence_storage
from apps.printing import storage as printing_storage


@pytest.mark.parametrize(
    ("module", "finalize_name", "size_name"),
    [
        (evidence_storage, "finalize_upload", "object_size"),
        (printing_storage, "print_finalize_upload", "print_object_size"),
    ],
)
def test_put_finalize_promotes_valid_staging_upload(
    monkeypatch, settings, module, finalize_name, size_name
):
    settings.STORAGE_PRESIGN_METHOD = "put"
    final_key = "evidence/1/issue/object"
    staging_key = f"staging/{final_key}"
    copied = []
    deleted = []

    # Staging holds 123 bytes; after the copy the final key also reports 123
    # (no race) — finalize re-HEADs the final object as the authoritative check.
    monkeypatch.setattr(module, "object_exists", lambda key: key == staging_key)
    monkeypatch.setattr(module, size_name, lambda key: 123)
    monkeypatch.setattr(module, "copy_object", lambda source, dest: copied.append((source, dest)))
    monkeypatch.setattr(module, "delete_object", lambda key: deleted.append(key))

    size = getattr(module, finalize_name)(final_key, max_bytes=500)

    assert size == 123
    assert copied == [(staging_key, final_key)]
    assert deleted == [staging_key]


@pytest.mark.parametrize(
    ("module", "finalize_name", "size_name"),
    [
        (evidence_storage, "finalize_upload", "object_size"),
        (printing_storage, "print_finalize_upload", "print_object_size"),
    ],
)
def test_put_finalize_rejects_and_deletes_final_when_staging_raced_oversized(
    monkeypatch, settings, module, finalize_name, size_name
):
    # Codex Stage-4 P2 TOCTOU: staging passes the pre-copy size check (100), but a
    # racing oversized PUT lands before the copy, so the COPIED final object is 999.
    # finalize must re-validate the final, reject it, and delete the oversized object.
    settings.STORAGE_PRESIGN_METHOD = "put"
    final_key = "evidence/1/issue/object"
    staging_key = f"staging/{final_key}"
    copied = []
    deleted = []

    monkeypatch.setattr(module, "object_exists", lambda key: False)
    monkeypatch.setattr(module, size_name, lambda key: 100 if key == staging_key else 999)
    monkeypatch.setattr(module, "copy_object", lambda source, dest: copied.append((source, dest)))
    monkeypatch.setattr(module, "delete_object", lambda key: deleted.append(key))

    size = getattr(module, finalize_name)(final_key, max_bytes=500)

    # Returns the oversized final size so the caller's range check rejects it,
    # the staging key is cleaned up, and the oversized final is deleted (not kept).
    assert size == 999
    assert copied == [(staging_key, final_key)]
    assert staging_key in deleted
    assert final_key in deleted


@pytest.mark.parametrize(
    ("module", "finalize_name", "size_name"),
    [
        (evidence_storage, "finalize_upload", "object_size"),
        (printing_storage, "print_finalize_upload", "print_object_size"),
    ],
)
def test_put_finalize_is_write_once_when_final_exists(
    monkeypatch, settings, module, finalize_name, size_name
):
    settings.STORAGE_PRESIGN_METHOD = "put"
    final_key = "evidence/1/issue/object"
    staging_key = f"staging/{final_key}"
    copied = []
    deleted = []

    monkeypatch.setattr(module, "object_exists", lambda key: key == final_key)
    monkeypatch.setattr(module, size_name, lambda key: 456 if key == final_key else None)
    monkeypatch.setattr(module, "copy_object", lambda source, dest: copied.append((source, dest)))
    monkeypatch.setattr(module, "delete_object", lambda key: deleted.append(key))

    size = getattr(module, finalize_name)(final_key, max_bytes=500)

    assert size == 456
    assert copied == []
    assert deleted == [staging_key]


@pytest.mark.parametrize(
    ("module", "finalize_name", "size_name"),
    [
        (evidence_storage, "finalize_upload", "object_size"),
        (printing_storage, "print_finalize_upload", "print_object_size"),
    ],
)
def test_put_finalize_returns_oversized_staging_size_without_promoting(
    monkeypatch, settings, module, finalize_name, size_name
):
    settings.STORAGE_PRESIGN_METHOD = "put"
    final_key = "evidence/1/issue/object"
    staging_key = f"staging/{final_key}"
    copied = []

    monkeypatch.setattr(module, "object_exists", lambda key: False)
    monkeypatch.setattr(module, size_name, lambda key: 501 if key == staging_key else None)
    monkeypatch.setattr(module, "copy_object", lambda source, dest: copied.append((source, dest)))
    monkeypatch.setattr(module, "delete_object", lambda key: None)

    size = getattr(module, finalize_name)(final_key, max_bytes=500)

    assert size == 501
    assert copied == []


@pytest.mark.parametrize(
    ("module", "finalize_name", "size_name"),
    [
        (evidence_storage, "finalize_upload", "object_size"),
        (printing_storage, "print_finalize_upload", "print_object_size"),
    ],
)
def test_put_finalize_returns_none_for_missing_upload(
    monkeypatch, settings, module, finalize_name, size_name
):
    settings.STORAGE_PRESIGN_METHOD = "put"
    copied = []
    deleted = []

    monkeypatch.setattr(module, "object_exists", lambda key: False)
    monkeypatch.setattr(module, size_name, lambda key: None)
    monkeypatch.setattr(module, "copy_object", lambda source, dest: copied.append((source, dest)))
    monkeypatch.setattr(module, "delete_object", lambda key: deleted.append(key))

    size = getattr(module, finalize_name)("evidence/1/issue/object", max_bytes=500)

    assert size is None
    assert copied == []
    assert deleted == []


@pytest.mark.parametrize(
    ("module", "finalize_name", "size_name"),
    [
        (evidence_storage, "finalize_upload", "object_size"),
        (printing_storage, "print_finalize_upload", "print_object_size"),
    ],
)
def test_non_put_finalize_reads_final_object_only(
    monkeypatch, settings, module, finalize_name, size_name
):
    settings.STORAGE_PRESIGN_METHOD = "post"
    final_key = "evidence/1/issue/object"
    sized = []
    copied = []
    deleted = []

    monkeypatch.setattr(module, "object_exists", lambda key: pytest.fail("unexpected object_exists call"))
    monkeypatch.setattr(module, size_name, lambda key: sized.append(key) or 321)
    monkeypatch.setattr(module, "copy_object", lambda source, dest: copied.append((source, dest)))
    monkeypatch.setattr(module, "delete_object", lambda key: deleted.append(key))

    size = getattr(module, finalize_name)(final_key, max_bytes=500)

    assert size == 321
    assert sized == [final_key]
    assert copied == []
    assert deleted == []


def test_evidence_presigned_upload_put_mode_signs_staging_key(monkeypatch, settings):
    settings.STORAGE_PRESIGN_METHOD = "put"

    class FakePublicClient:
        def generate_presigned_url(self, operation, Params, ExpiresIn):
            assert operation == "put_object"
            assert Params == {
                "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
                "Key": "staging/evidence/1/issue/x",
                "ContentType": "image/jpeg",
            }
            assert ExpiresIn == settings.EVIDENCE_URL_TTL_SECONDS
            return "http://minio/evidence-put"

    monkeypatch.setattr(
        "apps.evidence.storage._public_client",
        lambda: FakePublicClient(),
    )

    upload = evidence_storage.presigned_upload("evidence/1/issue/x", "image/jpeg")

    assert upload == {
        "url": "http://minio/evidence-put",
        "method": "PUT",
        "headers": {"Content-Type": "image/jpeg"},
    }

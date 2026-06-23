import pytest

from apps.evidence import storage as evidence_storage
from apps.inventory import public_image_storage
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

    def fake_size(key):
        if key == final_key and not copied:
            return None
        return 123

    _block_object_exists(monkeypatch, module)
    monkeypatch.setattr(module, size_name, fake_size)
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
    settings.STORAGE_PRESIGN_METHOD = "put"
    final_key = "evidence/1/issue/object"
    staging_key = f"staging/{final_key}"
    copied = []
    deleted = []

    def fake_size(key):
        if key == final_key and not copied:
            return None
        return 100 if key == staging_key else 999

    _block_object_exists(monkeypatch, module)
    monkeypatch.setattr(module, size_name, fake_size)
    monkeypatch.setattr(module, "copy_object", lambda source, dest: copied.append((source, dest)))
    monkeypatch.setattr(module, "delete_object", lambda key: deleted.append(key))

    size = getattr(module, finalize_name)(final_key, max_bytes=500)

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

    _block_object_exists(monkeypatch, module)
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

    _block_object_exists(monkeypatch, module)
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

    _block_object_exists(monkeypatch, module)
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

    _block_object_exists(monkeypatch, module)
    monkeypatch.setattr(module, size_name, lambda key: sized.append(key) or 321)
    monkeypatch.setattr(module, "copy_object", lambda source, dest: copied.append((source, dest)))
    monkeypatch.setattr(module, "delete_object", lambda key: deleted.append(key))

    size = getattr(module, finalize_name)(final_key, max_bytes=500)

    assert size == 321
    assert sized == [final_key]
    assert copied == []
    assert deleted == []

def test_public_image_finalize_uses_size_not_exists(monkeypatch, settings):
    settings.STORAGE_PRESIGN_METHOD = "put"
    settings.PUBLIC_IMAGE_MAX_BYTES = 500
    final_key = "items/1/object.jpg"
    staging_key = f"staging/{final_key}"
    copied = []
    sized = []

    def fake_size(key):
        sized.append(key)
        if key == final_key and not copied:
            return None
        return 123

    _block_object_exists(monkeypatch, public_image_storage)
    monkeypatch.setattr(public_image_storage, "object_size", fake_size)
    monkeypatch.setattr(public_image_storage, "copy_object", lambda source, dest: copied.append((source, dest)))
    monkeypatch.setattr(public_image_storage, "delete_object", lambda key: None)

    size = public_image_storage.finalize_upload(final_key)

    assert size == 123
    assert sized == [final_key, staging_key, final_key]
    assert copied == [(staging_key, final_key)]

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

def _block_object_exists(monkeypatch, module):
    if hasattr(module, "object_exists"):
        monkeypatch.setattr(
            module,
            "object_exists",
            lambda key: pytest.fail("unexpected object_exists call"),
        )

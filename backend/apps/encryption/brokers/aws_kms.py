"""Optional AWS KMS DEK wrapper. boto3 remains an enabled-mode dependency only."""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.encryption.brokers.base import KeyBroker, WrappedDek, require_dek


class AwsKmsBroker(KeyBroker):
    backend = "aws_kms"

    def _client(self):
        if not settings.PII_AWS_KMS_KEY_ID:
            raise ImproperlyConfigured("AWS KMS PII broker is not configured.")
        try:
            import boto3
        except ImportError as exc:
            raise ImproperlyConfigured(
                "AWS KMS PII broker requires boto3; install requirements-kms.txt."
            ) from exc
        # Region is optional here: when unset, boto3 resolves it from the standard
        # shared config / AWS_DEFAULT_REGION chain and raises NoRegionError (mapped
        # to ImproperlyConfigured at the call site) only if none is available.
        kwargs = {}
        if settings.PII_AWS_KMS_REGION:
            kwargs["region_name"] = settings.PII_AWS_KMS_REGION
        if settings.PII_AWS_KMS_ENDPOINT_URL:
            kwargs["endpoint_url"] = settings.PII_AWS_KMS_ENDPOINT_URL
        return boto3.client("kms", **kwargs)

    @staticmethod
    def _context(makerspace_id, version):
        return {
            "application": "inventory-manager-pii",
            "makerspace_id": str(makerspace_id),
            "dek_version": str(version),
        }

    def create_dek(self, makerspace_id, version):
        try:
            response = self._client().generate_data_key(
                KeyId=settings.PII_AWS_KMS_KEY_ID,
                KeySpec="AES_256",
                EncryptionContext=self._context(makerspace_id, version),
            )
            return WrappedDek(
                dek=require_dek(response["Plaintext"]),
                wrapped_dek=bytes(response["CiphertextBlob"]),
                broker_key_id=response.get("KeyId", settings.PII_AWS_KMS_KEY_ID),
            )
        except ImproperlyConfigured:
            raise
        except Exception as exc:
            raise ImproperlyConfigured("AWS KMS PII broker is unavailable.") from exc

    def wrap_dek(self, dek, makerspace_id, version):
        try:
            response = self._client().encrypt(
                KeyId=settings.PII_AWS_KMS_KEY_ID,
                Plaintext=require_dek(dek),
                EncryptionContext=self._context(makerspace_id, version),
            )
            return WrappedDek(
                dek=dek,
                wrapped_dek=bytes(response["CiphertextBlob"]),
                broker_key_id=response.get("KeyId", settings.PII_AWS_KMS_KEY_ID),
            )
        except ImproperlyConfigured:
            raise
        except Exception as exc:
            raise ImproperlyConfigured("AWS KMS PII broker is unavailable.") from exc

    def unwrap_dek(self, wrapped_dek, makerspace_id, version, *, use_previous=False):
        if use_previous:
            raise ImproperlyConfigured("AWS KMS PII broker cannot use a previous local key.")
        try:
            response = self._client().decrypt(
                CiphertextBlob=bytes(wrapped_dek),
                EncryptionContext=self._context(makerspace_id, version),
            )
            return require_dek(response["Plaintext"])
        except ImproperlyConfigured:
            raise
        except Exception as exc:
            raise ImproperlyConfigured("AWS KMS PII broker is unavailable.") from exc

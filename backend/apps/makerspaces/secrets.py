from apps.apiclients.crypto import decrypt_secret, encrypt_secret

PREFIX = "fernet:"


def encrypt_value(raw):
    if not raw:
        return ""
    value = str(raw)
    if value.startswith(PREFIX):
        return value
    return PREFIX + encrypt_secret(value).decode()


def decrypt_value(stored):
    if not stored:
        return ""
    value = str(stored)
    if not value.startswith(PREFIX):
        # Backward-compatible for credentials saved before at-rest encryption.
        return value
    return decrypt_secret(value.removeprefix(PREFIX).encode())

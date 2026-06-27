from datetime import timedelta


STATUS_UNKNOWN = "unknown"
STATUS_EXPIRED = "expired"
STATUS_EXPIRING_SOON = "expiring_soon"
STATUS_ACTIVE = "active"

STATUS_CHOICES = (
    (STATUS_UNKNOWN, "Unknown"),
    (STATUS_EXPIRED, "Expired"),
    (STATUS_EXPIRING_SOON, "Expiring soon"),
    (STATUS_ACTIVE, "Active"),
)

WARRANTY_EXPIRY_SOON_DAYS = 30


def warranty_status(warranty, today):
    expires_on = warranty.warranty_expires_on
    if expires_on is None:
        return STATUS_UNKNOWN
    if expires_on < today:
        return STATUS_EXPIRED
    if expires_on <= today + timedelta(days=WARRANTY_EXPIRY_SOON_DAYS):
        return STATUS_EXPIRING_SOON
    return STATUS_ACTIVE

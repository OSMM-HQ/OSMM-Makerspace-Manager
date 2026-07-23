from apps.makerspaces.platform import feature_enabled
from apps.payments.resolution import resolve_payment_source


def online_payments_enabled(makerspace, domain):
    """Whether this makerspace may accept online payments for a domain."""
    return (
        feature_enabled(makerspace, f"payments.{domain}")
        and resolve_payment_source(makerspace) is not None
    )

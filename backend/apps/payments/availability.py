from apps.makerspaces.platform import feature_enabled
from apps.payments.models import MakerspacePaymentSettings


def online_payments_enabled(makerspace, domain):
    """Whether this makerspace may accept online payments for a domain."""
    return (
        feature_enabled(makerspace, f"payments.{domain}")
        and MakerspacePaymentSettings.for_makerspace(makerspace).is_configured
    )

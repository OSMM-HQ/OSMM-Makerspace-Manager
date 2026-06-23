def blacklist_outstanding_tokens(user):
    # Invalidate every refresh token issued before a password rotation so old
    # sessions cannot persist after the credential changes.
    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken,
        OutstandingToken,
    )

    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)
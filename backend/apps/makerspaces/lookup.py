from django.http import Http404

from apps.makerspaces.models import Makerspace


def get_public_makerspace(identifier):
    value = str(identifier or "").strip()
    if not value:
        raise Http404
    # Deterministic precedence: slug wins over public_code. Slugs are user-controlled
    # and could collide with another makerspace's 4-char code, so a single OR-query
    # could raise MultipleObjectsReturned (-> 500). Two scoped lookups avoid that.
    makerspace = (
        Makerspace.objects.filter(slug=value, archived_at__isnull=True).first()
        or Makerspace.objects.filter(
            public_code__iexact=value,
            archived_at__isnull=True,
        ).first()
    )
    if makerspace is None:
        raise Http404
    return makerspace

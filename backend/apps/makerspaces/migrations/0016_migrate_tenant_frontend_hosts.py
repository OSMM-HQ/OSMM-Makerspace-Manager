from urllib.parse import urlsplit

from django.db import migrations


def _host_from_origin(origin):
    if not isinstance(origin, str):
        raise RuntimeError("TenantFrontend.allowed_origins entries must be strings.")
    raw = origin.strip()
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise RuntimeError(f"Could not parse TenantFrontend.allowed_origins entry: {origin!r}")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise RuntimeError(f"Invalid TenantFrontend.allowed_origins entry: {origin!r}")
    return parts.hostname.strip().lower()


def migrate_tenant_frontend_hosts(apps, schema_editor):
    Makerspace = apps.get_model("makerspaces", "Makerspace")
    TenantFrontend = apps.get_model("makerspaces", "TenantFrontend")

    resolved_by_space = {}
    claimed_by_host = {}

    for makerspace in Makerspace.objects.order_by("id"):
        hosts = set()
        frontends = TenantFrontend.objects.filter(makerspace_id=makerspace.id).order_by("id")
        if not frontends.exists():
            continue

        for frontend in frontends:
            hostname = (frontend.hostname or "").strip().lower()
            if hostname:
                hosts.add(hostname)
            for origin in frontend.allowed_origins or []:
                hosts.add(_host_from_origin(origin))

        if len(hosts) > 1:
            raise RuntimeError(
                "Ambiguous TenantFrontend hosts for makerspace "
                f"{makerspace.id}: {sorted(hosts)}"
            )
        if not hosts:
            continue

        host = next(iter(hosts))
        other_space_id = claimed_by_host.get(host)
        if other_space_id is not None:
            raise RuntimeError(
                f"TenantFrontend host {host!r} is claimed by makerspaces "
                f"{other_space_id} and {makerspace.id}."
            )
        existing_domain_owner = (
            Makerspace.objects.filter(frontend_domain__iexact=host)
            .exclude(id=makerspace.id)
            .values_list("id", flat=True)
            .first()
        )
        if existing_domain_owner is not None:
            raise RuntimeError(
                f"TenantFrontend host {host!r} collides with frontend_domain "
                f"on makerspace {existing_domain_owner}."
            )
        claimed_by_host[host] = makerspace.id
        resolved_by_space[makerspace.id] = host

    for makerspace_id, host in resolved_by_space.items():
        Makerspace.objects.filter(
            id=makerspace_id,
            frontend_domain__isnull=True,
        ).update(frontend_domain=host)
        Makerspace.objects.filter(
            id=makerspace_id,
            frontend_domain="",
        ).update(frontend_domain=host)


class Migration(migrations.Migration):

    dependencies = [
        ("makerspaces", "0015_makerspace_frontend_domain_and_more"),
    ]

    operations = [
        migrations.RunPython(migrate_tenant_frontend_hosts, migrations.RunPython.noop),
    ]

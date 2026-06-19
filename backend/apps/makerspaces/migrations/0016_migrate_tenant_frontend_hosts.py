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


def _candidate_hosts(hostname, allowed_origins):
    hosts = set()
    normalized = (hostname or "").strip().lower()
    if normalized:
        hosts.add(normalized)
    for origin in allowed_origins or []:
        hosts.add(_host_from_origin(origin))
    return hosts


def resolve_frontend_domains(frontend_rows):
    """Resolve TenantFrontend rows to a single host per makerspace.

    frontend_rows: iterable of (makerspace_id, hostname, allowed_origins). Returns
    {makerspace_id: host}. Raises RuntimeError on ambiguity (>1 distinct host for a
    makerspace), a cross-makerspace host collision, or an unparseable origin. Pure
    (no ORM) so the fail-loud branches are unit-testable.
    """
    hosts_by_space = {}
    for makerspace_id, hostname, allowed_origins in frontend_rows:
        hosts_by_space.setdefault(makerspace_id, set()).update(
            _candidate_hosts(hostname, allowed_origins)
        )

    resolved = {}
    claimed = {}
    for makerspace_id in sorted(hosts_by_space):
        hosts = hosts_by_space[makerspace_id]
        if len(hosts) > 1:
            raise RuntimeError(
                f"Ambiguous TenantFrontend hosts for makerspace {makerspace_id}: {sorted(hosts)}"
            )
        if not hosts:
            continue
        host = next(iter(hosts))
        if host in claimed:
            raise RuntimeError(
                f"TenantFrontend host {host!r} is claimed by makerspaces "
                f"{claimed[host]} and {makerspace_id}."
            )
        claimed[host] = makerspace_id
        resolved[makerspace_id] = host
    return resolved


def migrate_tenant_frontend_hosts(apps, schema_editor):
    Makerspace = apps.get_model("makerspaces", "Makerspace")
    TenantFrontend = apps.get_model("makerspaces", "TenantFrontend")

    rows = [
        (frontend.makerspace_id, frontend.hostname, frontend.allowed_origins)
        for frontend in TenantFrontend.objects.all().order_by("makerspace_id", "id")
    ]
    resolved = resolve_frontend_domains(rows)

    for makerspace_id, host in resolved.items():
        existing_owner = (
            Makerspace.objects.filter(frontend_domain__iexact=host)
            .exclude(id=makerspace_id)
            .values_list("id", flat=True)
            .first()
        )
        if existing_owner is not None:
            raise RuntimeError(
                f"TenantFrontend host {host!r} collides with frontend_domain "
                f"on makerspace {existing_owner}."
            )
        Makerspace.objects.filter(
            id=makerspace_id, frontend_domain__isnull=True
        ).update(frontend_domain=host)
        Makerspace.objects.filter(
            id=makerspace_id, frontend_domain=""
        ).update(frontend_domain=host)


class Migration(migrations.Migration):

    dependencies = [
        ("makerspaces", "0015_makerspace_frontend_domain_and_more"),
    ]

    operations = [
        migrations.RunPython(migrate_tenant_frontend_hosts, migrations.RunPython.noop),
    ]

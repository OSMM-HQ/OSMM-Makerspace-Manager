import pytest
from django.test import override_settings
from django.urls import reverse

from apps.makerspaces.models import Makerspace, SubdomainRequest
from tests.return_helpers import authenticated_client, make_member, make_space


def subdomain_request_url(makerspace):
    return reverse(
        "admin-makerspace-subdomain-request",
        kwargs={"makerspace_id": makerspace.id},
    )


@override_settings(PLATFORM_DOMAIN_SUFFIX=".space-works.tech", INFRA_HOSTS={"testserver"})
@pytest.mark.django_db
def test_manager_can_create_managed_subdomain_request():
    makerspace = make_space("subdomain-create")
    manager = make_member("subdomain-create-manager", makerspace)

    response = authenticated_client(manager).post(
        subdomain_request_url(makerspace),
        {"requested_label": "create-lab"},
        format="json",
        HTTP_HOST="testserver",
    )

    assert response.status_code == 201
    request = SubdomainRequest.objects.get(makerspace=makerspace)
    assert request.status == "pending"
    assert request.requested_label == "create-lab"
    assert request.requested_by == manager


@override_settings(PLATFORM_DOMAIN_SUFFIX="")
@pytest.mark.django_db
def test_self_host_rejects_subdomain_request_without_creating_row():
    makerspace = make_space("subdomain-self-host")
    manager = make_member("subdomain-self-host-manager", makerspace)

    response = authenticated_client(manager).post(
        subdomain_request_url(makerspace),
        {"requested_label": "self-host-lab"},
        format="json",
    )

    assert response.status_code == 400
    assert "managed" in str(response.data).lower()
    assert not SubdomainRequest.objects.exists()


@override_settings(PLATFORM_DOMAIN_SUFFIX=".space-works.tech", INFRA_HOSTS={"testserver"})
@pytest.mark.django_db
def test_second_pending_request_for_same_makerspace_is_rejected():
    makerspace = make_space("subdomain-duplicate")
    manager = make_member("subdomain-duplicate-manager", makerspace)
    client = authenticated_client(manager)
    url = subdomain_request_url(makerspace)

    first = client.post(
        url,
        {"requested_label": "first-label"},
        format="json",
        HTTP_HOST="testserver",
    )
    second = client.post(
        url,
        {"requested_label": "different-label"},
        format="json",
        HTTP_HOST="testserver",
    )

    assert first.status_code == 201
    assert second.status_code == 400
    assert "pending" in str(second.data).lower()
    assert (
        SubdomainRequest.objects.filter(
            makerspace=makerspace,
            status=SubdomainRequest.Status.PENDING,
        ).count()
        == 1
    )


@override_settings(PLATFORM_DOMAIN_SUFFIX=".space-works.tech", INFRA_HOSTS={"testserver"})
@pytest.mark.django_db
def test_manager_cannot_request_subdomain_for_another_makerspace():
    own_space = make_space("subdomain-cross-tenant-own")
    other_space = make_space("subdomain-cross-tenant-other")
    manager = make_member("subdomain-cross-tenant-manager", own_space)

    response = authenticated_client(manager).post(
        subdomain_request_url(other_space),
        {"requested_label": "foreign-lab"},
        format="json",
        HTTP_HOST="testserver",
    )

    assert response.status_code == 404
    assert not SubdomainRequest.objects.exists()


@override_settings(PLATFORM_DOMAIN_SUFFIX=".space-works.tech", INFRA_HOSTS={"testserver"})
@pytest.mark.django_db
@pytest.mark.parametrize(
    ("requested_label", "message"),
    [
        ("api", "reserved"),
        ("bad.label", "valid"),
        ("Bad Label", "valid"),
    ],
)
def test_reserved_or_invalid_subdomain_label_is_rejected(requested_label, message):
    slug_part = requested_label.lower().replace(".", "-").replace(" ", "-")
    makerspace = make_space(f"subdomain-invalid-{slug_part}")
    manager = make_member(f"subdomain-invalid-manager-{slug_part}", makerspace)

    response = authenticated_client(manager).post(
        subdomain_request_url(makerspace),
        {"requested_label": requested_label},
        format="json",
        HTTP_HOST="testserver",
    )

    assert response.status_code == 400
    assert message in str(response.data).lower()
    assert not SubdomainRequest.objects.exists()


@override_settings(PLATFORM_DOMAIN_SUFFIX=".space-works.tech", INFRA_HOSTS={"testserver"})
@pytest.mark.django_db
def test_already_taken_verified_subdomain_label_is_rejected():
    makerspace = make_space("subdomain-collision-requester")
    manager = make_member("subdomain-collision-manager", makerspace)
    owner = make_space("subdomain-collision-owner")
    owner.frontend_domain = "claimed.space-works.tech"
    owner.frontend_domain_status = Makerspace.DomainStatus.VERIFIED
    owner.save()

    response = authenticated_client(manager).post(
        subdomain_request_url(makerspace),
        {"requested_label": "claimed"},
        format="json",
        HTTP_HOST="testserver",
    )

    assert owner.frontend_domain == "claimed.space-works.tech"
    assert owner.frontend_domain_status == Makerspace.DomainStatus.VERIFIED
    assert response.status_code == 400
    assert "already taken" in str(response.data).lower()
    assert not SubdomainRequest.objects.exists()


@override_settings(PLATFORM_DOMAIN_SUFFIX=".space-works.tech", INFRA_HOSTS={"testserver"})
@pytest.mark.django_db
def test_already_provisioned_makerspace_cannot_request_another_subdomain():
    makerspace = make_space("subdomain-already-provisioned")
    makerspace.frontend_domain = "existing.space-works.tech"
    makerspace.frontend_domain_status = Makerspace.DomainStatus.VERIFIED
    makerspace.save()
    manager = make_member("subdomain-already-provisioned-manager", makerspace)

    response = authenticated_client(manager).post(
        subdomain_request_url(makerspace),
        {"requested_label": "replacement"},
        format="json",
        HTTP_HOST="testserver",
    )

    assert response.status_code == 400
    assert "already has a subdomain" in str(response.data).lower()
    assert not SubdomainRequest.objects.exists()


@override_settings(PLATFORM_DOMAIN_SUFFIX=".space-works.tech", INFRA_HOSTS={"testserver"})
@pytest.mark.django_db
def test_requested_label_is_trimmed_and_lowercased():
    makerspace = make_space("subdomain-normalized")
    manager = make_member("subdomain-normalized-manager", makerspace)

    response = authenticated_client(manager).post(
        subdomain_request_url(makerspace),
        {"requested_label": "  MyLab  "},
        format="json",
        HTTP_HOST="testserver",
    )

    assert response.status_code == 201
    assert response.data["requested_label"] == "mylab"
    assert SubdomainRequest.objects.get(makerspace=makerspace).requested_label == "mylab"


@override_settings(PLATFORM_DOMAIN_SUFFIX=".space-works.tech", INFRA_HOSTS={"testserver"})
@pytest.mark.django_db
def test_get_lists_only_requests_for_managers_own_makerspace():
    own_space = make_space("subdomain-list-own")
    other_space = make_space("subdomain-list-other")
    manager = make_member("subdomain-list-manager", own_space)
    client = authenticated_client(manager)

    created = client.post(
        subdomain_request_url(own_space),
        {"requested_label": "own-label"},
        format="json",
        HTTP_HOST="testserver",
    )
    other_request = SubdomainRequest.objects.create(
        makerspace=other_space,
        requested_label="other-label",
    )
    response = client.get(
        subdomain_request_url(own_space),
        HTTP_HOST="testserver",
    )

    assert created.status_code == 201
    assert response.status_code == 200
    assert [item["id"] for item in response.data["results"]] == [created.data["id"]]
    assert other_request.id not in {item["id"] for item in response.data["results"]}

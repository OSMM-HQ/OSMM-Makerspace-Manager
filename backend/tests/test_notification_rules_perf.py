import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.integrations.models import (
    NotificationChannel,
    NotificationFeature,
    NotificationPreference,
)
from tests.test_notification_rules_api import (
    authenticated_client,
    make_member,
    make_space,
    rules_url,
)

pytestmark = pytest.mark.django_db


def test_matrix_get_query_count_is_constant():
    """The 20-cell matrix resolves from a single preference query, so adding an override
    row for every cell must not add any queries (guards against the per-cell N+1)."""
    makerspace = make_space("rules-nplus1")
    manager = make_member("rules-nplus1-mgr", makerspace)
    client = authenticated_client(manager)

    client.get(rules_url(makerspace))  # warm content-type / permission caches
    with CaptureQueriesContext(connection) as baseline:
        client.get(rules_url(makerspace))

    for feature in NotificationFeature:
        for channel in NotificationChannel:
            NotificationPreference.objects.create(
                makerspace=makerspace,
                feature=feature.value,
                channel=channel.value,
                enabled=False,
            )

    with CaptureQueriesContext(connection) as loaded:
        client.get(rules_url(makerspace))

    assert len(loaded) == len(baseline)

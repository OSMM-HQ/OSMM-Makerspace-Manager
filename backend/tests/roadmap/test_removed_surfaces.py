import pytest
from django.contrib import admin
from rest_framework.test import APIClient

from apps.roadmap.models import RoadmapItem


pytestmark = pytest.mark.django_db


def test_roadmap_is_not_exposed_by_the_production_application():
    response = APIClient().get("/api/v1/public/roadmap")

    assert response.status_code == 404
    assert RoadmapItem not in admin.site._registry


def test_openapi_does_not_advertise_the_removed_roadmap():
    response = APIClient().get("/schema/?format=json")

    assert response.status_code == 200
    assert b'"/api/v1/public/roadmap"' not in response.content

import pytest
from drf_spectacular.generators import SchemaGenerator
import json


pytestmark = pytest.mark.django_db


def test_maintenance_has_no_public_route_or_public_schema_fields():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    maintenance_paths = [
        path for path in schema["paths"] if "maintenance" in path
    ]
    assert maintenance_paths
    assert all("/api/v1/admin/" in path for path in maintenance_paths)
    public_paths = {
        path: operations
        for path, operations in schema["paths"].items()
        if "/public/" in path
    }
    serialized = json.dumps(public_paths)
    assert "MaintenanceSchedule" not in serialized
    assert "MaintenanceLog" not in serialized
    assert "MaintenanceLogDocument" not in serialized

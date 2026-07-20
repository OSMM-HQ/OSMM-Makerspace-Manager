import pytest
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder

import apps.printing.models as printing_models


pytestmark = pytest.mark.django_db


LEGACY_MODEL_NAMES = (
    "PrintBucket",
    "PrintPrinter",
    "FilamentSpool",
    "FilamentAdjustment",
    "ManualPrintLog",
    "PrintRequest",
    "PrintRequestFile",
)
LEGACY_TABLES = {
    "printing_printbucket",
    "printing_printprinter",
    "printing_filamentspool",
    "printing_filamentadjustment",
    "printing_manualprintlog",
    "printing_printrequest",
    "printing_printrequestfile",
}


def test_printing_models_module_exposes_no_legacy_models():
    assert all(not hasattr(printing_models, name) for name in LEGACY_MODEL_NAMES)


def test_tombstone_migration_applied_to_fresh_test_database():
    applied = MigrationRecorder(connection).applied_migrations()
    assert ("printing", "0022_retire_legacy_models") in applied
    assert LEGACY_TABLES.isdisjoint(connection.introspection.table_names())

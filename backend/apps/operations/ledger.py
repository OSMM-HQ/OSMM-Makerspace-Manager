from apps.operations.ledger_query import normalize_sort, normalize_source, ordered_queryset
from apps.operations.ledger_units import export_rows, materialize_rows


def ledger_rows(makerspace_id=None, *, filters=None):
    return materialize_rows(ordered_queryset(makerspace_id, filters=filters))


def ledger_page(makerspace_id=None, *, page=1, page_size=100, filters=None):
    offset = max(page - 1, 0) * page_size
    queryset = ordered_queryset(makerspace_id, filters=filters)
    count = queryset.count()
    rows = materialize_rows(queryset[offset : offset + page_size])
    return {"count": count, "results": rows}


def ledger_export_rows(makerspace_id=None, *, filters=None):
    return export_rows(ledger_rows(makerspace_id, filters=filters))

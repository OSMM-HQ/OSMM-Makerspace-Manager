from decimal import Decimal

from apps.operations.report_registry import (
    REPORT_KEYS,
    ReportResult,
    report_definition,
)
from apps.operations.reports_inventory import (
    _most_lent,
    _taken_items,
    _top_borrowers,
)
from apps.operations.reports_typed import typed_report_rows, typed_result_rows


DEFAULT_REPORT_LIMIT = 100
MAX_REPORT_LIMIT = 500


def report_data(report_key="summary", makerspace_id=None, *, limit=None, date_range=None):
    definition = report_definition(report_key)
    result = definition.builder()(
        makerspace_id,
        limit=_normalized_limit(limit),
        date_range=date_range,
    )
    if definition.summary:
        return result
    if not isinstance(result, ReportResult):
        return {"rows": result, "typed_rows": typed_report_rows(report_key, result)}
    rows = _matrix(result, json=True)
    return {"rows": rows, "typed_rows": typed_result_rows(result, json_value)}


def report_rows(report_key, makerspace_id=None, *, limit=None, date_range=None):
    definition = report_definition(report_key, for_export=True)
    result = definition.builder()(makerspace_id, limit=limit, date_range=date_range)
    if isinstance(result, ReportResult):
        return _matrix(result, json=False)
    return result


def required_modules(report_key):
    return report_definition(report_key).required_modules


def validate_report_key(report_key, *, for_export=False):
    return report_definition(report_key, for_export=for_export)


def _normalized_limit(limit):
    if limit is None:
        limit = DEFAULT_REPORT_LIMIT
    return max(0, min(int(limit), MAX_REPORT_LIMIT))


def _matrix(result, *, json):
    convert = json_value if json else (lambda value: value)
    return [
        list(result.field_order),
        *[
            [convert(record.get(field)) for field in result.field_order]
            for record in result.records
        ],
    ]


def json_value(value):
    if isinstance(value, Decimal):
        return format(value.quantize(Decimal("0.01")), ".2f")
    return value

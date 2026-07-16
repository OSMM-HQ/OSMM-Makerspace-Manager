import csv
from datetime import datetime
from io import BytesIO, StringIO

from django.http import HttpResponse
from openpyxl import Workbook


def _csv_response(rows, filename):
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerows([[_export_cell(value) for value in row] for row in rows])
    response = HttpResponse(buffer.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _xlsx_response(rows, filename):
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append([_xlsx_cell(value) for value in row])
    buffer = BytesIO()
    workbook.save(buffer)
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _xlsx_cell(value):
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.replace(tzinfo=None)
    return _export_cell(value)


def _export_cell(value):
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{value}"
    return value

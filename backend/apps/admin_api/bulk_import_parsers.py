import csv
import io
import json

MAX_IMPORT_ROWS = 5000
MAX_IMPORT_UPLOAD_BYTES = 5 * 1024 * 1024


class BulkImportLimitError(ValueError):
    pass


def rows_from_upload(uploaded_file):
    name = uploaded_file.name.lower()
    size = getattr(uploaded_file, "size", None)
    if size is not None and size > MAX_IMPORT_UPLOAD_BYTES:
        raise ValueError(
            f"Import file must be {MAX_IMPORT_UPLOAD_BYTES} bytes or smaller."
        )
    data = uploaded_file.read()
    if name.endswith(".json"):
        parsed = json.loads(data.decode("utf-8-sig"))
        if not isinstance(parsed, list):
            raise ValueError("JSON import must be a list of row objects.")
        validate_row_count(parsed)
        return parsed
    if name.endswith(".tsv"):
        return delimited_rows(data, "\t")
    if name.endswith(".xlsx"):
        return xlsx_rows(data)
    return delimited_rows(data, ",")


def delimited_rows(data, delimiter):
    text = data.decode("utf-8-sig")
    rows = []
    for row in csv.DictReader(io.StringIO(text), delimiter=delimiter):
        rows.append(row)
        if len(rows) > MAX_IMPORT_ROWS:
            raise BulkImportLimitError(
                f"Bulk import is limited to {MAX_IMPORT_ROWS} rows."
            )
    return rows


def xlsx_rows(data):
    try:
        import openpyxl
    except ImportError as exc:
        raise ValueError("XLSX import requires openpyxl to be installed.") from exc
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        sheet = workbook.active
        rows = sheet.iter_rows(values_only=True)
        header_row = next(rows, None)
        if not header_row:
            return []
        headers = [str(value or "").strip() for value in header_row]
        parsed_rows = []
        for row in rows:
            parsed_rows.append(
                {
                    headers[index]: value
                    for index, value in enumerate(row)
                    if index < len(headers)
                }
            )
            if len(parsed_rows) > MAX_IMPORT_ROWS:
                raise BulkImportLimitError(
                    f"Bulk import is limited to {MAX_IMPORT_ROWS} rows."
                )
        return parsed_rows
    except BulkImportLimitError:
        raise
    except Exception as exc:
        raise ValueError("XLSX file could not be read.") from exc


def validate_row_count(rows):
    if len(rows) > MAX_IMPORT_ROWS:
        raise BulkImportLimitError(f"Bulk import is limited to {MAX_IMPORT_ROWS} rows.")

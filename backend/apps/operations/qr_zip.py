import io
import zipfile

import segno
from django.utils.html import escape


def build_batch_zip(batch) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, item in enumerate(batch.items.select_related("qr_code"), start=1):
            label = item.label_text
            png_data_uri = segno.make(item.qr_code.payload).png_data_uri(scale=5)
            svg = (
                '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="360" viewBox="0 0 320 360">'
                '<rect width="320" height="360" fill="#ffffff"/>'
                f'<image href="{png_data_uri}" x="20" y="10" width="280" height="280"/>'
                f'<text x="160" y="330" text-anchor="middle" font-family="Arial,sans-serif" font-size="18" fill="#111827">{escape(label)}</text>'
                "</svg>"
            )
            archive.writestr(f"{index:02d}-{_sanitize_label(label)}.svg", svg)
    return buffer.getvalue()


def _sanitize_label(label):
    sanitized = "".join(char.lower() if char.isalnum() or char in "-_" else "-" for char in label)
    return sanitized or "qr"

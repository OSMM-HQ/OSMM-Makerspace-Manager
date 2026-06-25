from io import BytesIO

from PIL import Image, UnidentifiedImageError


IMAGE_MIME_BY_FORMAT = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


def image_mime_from_bytes(data):
    try:
        image = Image.open(BytesIO(data))
        detected = IMAGE_MIME_BY_FORMAT.get(image.format)
        image.verify()
    except (OSError, UnidentifiedImageError):
        return None
    return detected

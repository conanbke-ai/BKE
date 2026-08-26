from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

from PIL import Image

from config import SETTINGS


def compressed_data_url(path: Path) -> str:
    """전체 페이지 이미지를 API 입력 한도에 맞게 반복 압축한다."""
    with Image.open(path) as source:
        image = source.convert("RGB")

    scale = min(
        1.0,
        SETTINGS.max_image_width / image.width,
        SETTINGS.max_image_height / image.height,
    )
    if scale < 1:
        image = image.resize(
            (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
        )

    quality = SETTINGS.jpeg_quality
    for _ in range(5):
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=quality, optimize=True)
        data = buffer.getvalue()
        if len(data) <= SETTINGS.max_image_bytes:
            encoded = base64.b64encode(data).decode("ascii")
            return f"data:image/jpeg;base64,{encoded}"

        quality = max(45, quality - 10)
        image = image.resize(
            (max(1, int(image.width * 0.82)), max(1, int(image.height * 0.82)))
        )

    encoded = base64.b64encode(data).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"

from __future__ import annotations

import tempfile
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image

SUPPORTED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
}


def is_image_path(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def normalize_image_for_vision(
    source: Path,
    *,
    dest_dir: Path | None = None,
) -> Path:
    """
    Конвертирует изображение в PNG для Vision API.
    GIF — первый кадр. Возвращает путь к файлу (исходный или нормализованный).
    """
    source = source.resolve()
    if not source.exists():
        raise FileNotFoundError(f"Изображение не найдено: {source}")

    ext = source.suffix.lower()
    if ext in {".png", ".jpg", ".jpeg"}:
        return source

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Неподдерживаемый формат: {ext}. "
            f"Допустимо: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    img = Image.open(source)
    if getattr(img, "n_frames", 1) > 1:
        img.seek(0)
    img = img.convert("RGB")

    out_dir = dest_dir or source.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{source.stem}_normalized.png"
    img.save(dest, format="PNG")
    return dest.resolve()


def fetch_image_url(url: str, *, dest_dir: Path | None = None) -> Path:
    """Скачивает изображение по URL во временный или указанный каталог."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL должен начинаться с http:// или https://")

    try:
        import requests
    except ImportError as e:
        raise RuntimeError("Установите requests: pip install requests") from e

    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    content_type = (resp.headers.get("content-type") or "").lower()
    suffix = ".png"
    if "jpeg" in content_type or "jpg" in content_type:
        suffix = ".jpg"
    elif "webp" in content_type:
        suffix = ".webp"
    elif "gif" in content_type:
        suffix = ".gif"

    out_dir = dest_dir or Path(tempfile.gettempdir()) / "orgdiag_downloads"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"url_image{suffix}"
    dest.write_bytes(resp.content)
    return normalize_image_for_vision(dest, dest_dir=out_dir)


def resolve_image_input(
    *,
    image_path: Path | None = None,
    image_url: str | None = None,
    cache_dir: Path | None = None,
) -> Path:
    if image_url and image_url.strip():
        return fetch_image_url(
            image_url.strip(),
            dest_dir=cache_dir,
        )
    if image_path is None:
        raise ValueError("Укажите --image или --image-url")
    p = image_path.resolve()
    return normalize_image_for_vision(p, dest_dir=cache_dir or p.parent)

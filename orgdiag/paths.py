from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
MATRIX_FILE = DATA_DIR / "matrix_defects.txt"
ENV_FILE = PROJECT_ROOT / ".env"
FONT_FILE = DATA_DIR / "DejaVuSans.ttf"


def _load_env_for_paths() -> None:
    if ENV_FILE.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(ENV_FILE, override=False)
        except ImportError:
            pass


def _resolve_images_dir() -> Path:
    _load_env_for_paths()
    raw = os.environ.get("ORGDIAG_IMAGES_DIR", "").strip()
    if raw:
        return Path(raw).resolve()
    return (PROJECT_ROOT / "images").resolve()


IMAGES_DIR = _resolve_images_dir()
REPORTS_DIR = PROJECT_ROOT / "reports"
HTML_OUT_DIR = PROJECT_ROOT / "html_out"
CACHE_DIR = PROJECT_ROOT / "cache"
CASES_DIR = PROJECT_ROOT / "cases"
DOCS_DIR = PROJECT_ROOT / "docs"
REFERENCE_ORG_SCHEME_IMAGE = DOCS_DIR / "reference_org_scheme.png"


def resolve_path(path: str | Path, base: Path | None = None) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p.resolve()
    root = base or PROJECT_ROOT
    return (root / p).resolve()


def find_up(filename: str, start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    while True:
        candidate = current / filename
        if candidate.exists():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    raise FileNotFoundError(f"Файл не найден: {filename} (искали от {start})")

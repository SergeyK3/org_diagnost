from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

from orgdiag.paths import ENV_FILE

OutputFormat = Literal["html", "pdf", "both"]

DEFAULT_ORGDIAG_CONTACT = "@kimsergeiv"


@dataclass
class RunConfig:
    image: Path
    org_type: str
    pain: str
    org_name: str = ""
    contact: str = ""
    vision_model: str = "gpt-4o-mini"
    simplify_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-small"
    output: Path | None = None
    html_output: Path | None = None
    cache_dir: Path | None = None
    use_cache: bool = True
    skip_vision: bool = False
    with_llm_diagnosis: bool = False
    with_pain_matrix: bool = False
    output_format: OutputFormat = "html"
    image_url: str | None = None
    dry_run: bool = False
    save_visuals: bool = True

    @property
    def image_stem(self) -> str:
        return self.image.stem

    @property
    def display_org_name(self) -> str:
        return (self.org_name or self.org_type).strip() or self.image_stem


def load_env() -> None:
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE, override=True)
    else:
        load_dotenv(override=True)


def default_contact() -> str:
    load_env()
    return os.environ.get("ORGDIAG_CONTACT", "").strip() or DEFAULT_ORGDIAG_CONTACT


def require_api_key() -> str:
    load_env()
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key or key == "your_openai_api_key_here":
        raise RuntimeError(
            f"OPENAI_API_KEY не задан. Добавьте ключ в {ENV_FILE}"
        )
    return key

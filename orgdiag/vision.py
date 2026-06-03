from __future__ import annotations

import base64
import json
import re
from pathlib import Path

from openai import OpenAI

from orgdiag.config import require_api_key
from orgdiag.prompts import build_vision_system_prompt


def file_to_data_url(path: Path) -> str:
    p = str(path).lower()
    if p.endswith(".png"):
        mime = "image/png"
    elif p.endswith(".jpg") or p.endswith(".jpeg"):
        mime = "image/jpeg"
    else:
        mime = "application/octet-stream"
    b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def extract_org_json_from_image(
    image_path: Path,
    *,
    model: str = "gpt-4o-mini",
    system_prompt: str | None = None,
    client: OpenAI | None = None,
) -> dict:
    require_api_key()
    client = client or OpenAI()
    data_url = file_to_data_url(image_path)
    prompt = system_prompt or build_vision_system_prompt()

    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": [{"type": "input_text", "text": prompt}]},
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Извлеки оргструктуру с изображения по схеме JSON."},
                    {"type": "input_image", "image_url": data_url},
                ],
            },
        ],
        temperature=0,
    )
    text = getattr(resp, "output_text", "") or ""
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"Не найден JSON в ответе модели:\n{text[:500]}")
    return json.loads(match.group(0))


def save_org_json_cache(path: Path, org_json: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(org_json, ensure_ascii=False, indent=2), encoding="utf-8")


def load_org_json_cache(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

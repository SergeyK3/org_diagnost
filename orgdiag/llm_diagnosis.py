from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from orgdiag.config import require_api_key
from orgdiag.paths import MATRIX_FILE


def _chat(
    client: OpenAI,
    *,
    system_prompt: str,
    user_content: str,
    model: str,
    max_tokens: int = 1500,
) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


def run_step1_diagnosis(
    *,
    system_prompt: str,
    step1_prompt: str,
    org_type: str,
    pain: str,
    hierarchy_text: str,
    simple_structure: str,
    compare_text: str,
    pain_analysis_text: str,
    model: str = "gpt-4o",
    client: OpenAI | None = None,
) -> str:
    """Шаг 1 (legacy): структурированная диагностика по матрице боли."""
    require_api_key()
    client = client or OpenAI()

    matrix_excerpt = MATRIX_FILE.read_text(encoding="utf-8")[:4000]
    user_content = f"""{step1_prompt}

---
ВХОДНЫЕ ДАННЫЕ:

Тип предприятия: {org_type}
Управленческая боль: {pain}

Оргструктура (иерархия):
{hierarchy_text}

Упрощённая структура:
{simple_structure}

Сравнение с эталоном:
{compare_text}

Предварительный разбор боли (матрица):
{pain_analysis_text}

Фрагмент matrix_defects.txt:
{matrix_excerpt}
"""
    return _chat(
        client,
        system_prompt=system_prompt,
        user_content=user_content,
        model=model,
        max_tokens=2000,
    )


def run_pass1_block_analysis(
    *,
    system_prompt: str,
    pass1_prompt: str,
    org_type: str,
    pain: str,
    hierarchy_text: str,
    simple_structure: str,
    compare_text: str,
    pain_analysis_text: str = "",
    model: str = "gpt-4o",
    client: OpenAI | None = None,
) -> str:
    """Проход 1: выводы только по блочной структуре и потоку."""
    require_api_key()
    client = client or OpenAI()
    user_content = f"""{pass1_prompt}

---
Тип предприятия: {org_type}
Управленческая боль (контекст): {pain}

Иерархия (из изображения):
{hierarchy_text}

Упрощённая структура (факт):
{simple_structure}

Сравнение с эталоном:
{compare_text}
"""
    if pain_analysis_text.strip():
        user_content += f"\nКонтекст из матрицы боли:\n{pain_analysis_text}\n"

    return _chat(
        client,
        system_prompt=system_prompt,
        user_content=user_content,
        model=model,
    )


def run_pass2_admin_analysis(
    *,
    system_prompt: str,
    pass2_prompt: str,
    org_type: str,
    pain: str,
    hierarchy_text: str,
    simple_structure: str,
    block_roles: dict[str, list[dict[str, Any]]],
    org_json: dict,
    model: str = "gpt-4o",
    client: OpenAI | None = None,
) -> str:
    """Проход 2: выводы по административным должностям и руководителям."""
    require_api_key()
    client = client or OpenAI()
    roles_text = json.dumps(block_roles, ensure_ascii=False, indent=2)
    user_content = f"""{pass2_prompt}

---
Тип предприятия: {org_type}
Управленческая боль (контекст): {pain}

Иерархия:
{hierarchy_text}

Упрощённые блоки:
{simple_structure}

Сопоставление отделов с блоками и руководители:
{roles_text}

Фрагмент org_json:
{json.dumps(org_json, ensure_ascii=False, indent=2)[:6000]}
"""
    return _chat(
        client,
        system_prompt=system_prompt,
        user_content=user_content,
        model=model,
    )

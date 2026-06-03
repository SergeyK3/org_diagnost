from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from orgdiag.config import default_contact, load_env, require_api_key
from orgdiag.paths import PROMPTS_DIR
from orgdiag.pipeline import DiagnosisResult
from orgdiag.prompts import load_prompt

DEFAULT_MAX_FOLLOWUP = 3
GATE_MODEL = "gpt-4o-mini"
ANSWER_MODEL = "gpt-4o-mini"
MIN_QUESTION_LEN = 8
MAX_QUESTION_LEN = 800

# Явно нерелевантные темы — без вызова LLM
_OFF_TOPIC_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(python|javascript|java|sql|react|django|api\s+key)\b",
        r"\b(напиши|написать|сгенерируй).{0,40}\b(код|скрипт|программ)\b",
        r"\b(погод|рецепт|анекдот|стих|песн|фильм)\b",
        r"\b(переведи|translate).{0,30}\b(текст|стать|документ)\b",
        r"\b(домашн|эссе|курсов).{0,20}\b(работ)\b",
        r"\b(игнорир|забудь|jailbreak|DAN)\b",
        r"\b(openai|gpt-4|chatgpt)\b.{0,30}\b(ключ|key)\b",
    )
)


@dataclass(frozen=True)
class FollowupTurn:
    question: str
    answer: str
    allowed: bool = True


@dataclass
class FollowupReply:
    allowed: bool
    text: str
    gate_reason: str = ""


def max_followup_questions() -> int:
    load_env()
    raw = os.environ.get("ORGDIAG_FOLLOWUP_MAX", "").strip()
    if not raw:
        return DEFAULT_MAX_FOLLOWUP
    try:
        n = int(raw)
    except ValueError:
        return DEFAULT_MAX_FOLLOWUP
    return max(1, min(n, 10))


def _load_gate_prompt() -> str:
    return load_prompt("followup_gate_prompt.txt")


def _load_answer_prompt() -> str:
    return load_prompt("followup_system_prompt.txt")


def build_followup_context(result: DiagnosisResult, *, contact: str = "") -> str:
    contact_line = (contact or default_contact()).strip()
    org_json_excerpt = json.dumps(result.org_json, ensure_ascii=False, indent=2)
    if len(org_json_excerpt) > 5000:
        org_json_excerpt = org_json_excerpt[:5000] + "\n… (обрезано)"

    parts = [
        f"Тип предприятия: {result.org_type}",
        f"Управленческая боль: {result.pain}",
        f"Контакт консультанта: {contact_line}",
        "",
        "Иерархия (из схемы):",
        result.hierarchy_text.strip() or "—",
        "",
        "Упрощённая структура:",
        result.simple_structure.strip() or "—",
        "",
        "Сравнение с эталоном:",
        result.compare_text.strip() or "—",
    ]
    if result.pain_analysis_text.strip():
        parts.extend(["", "Матрица боли:", result.pain_analysis_text.strip()])
    if result.pass1_text.strip():
        parts.extend(["", "Выводы pass1 (блоки и поток):", result.pass1_text.strip()])
    if result.pass2_text.strip():
        parts.extend(["", "Выводы pass2 (руководители):", result.pass2_text.strip()])
    if result.block_roles:
        roles = json.dumps(result.block_roles, ensure_ascii=False, indent=2)
        if len(roles) > 4000:
            roles = roles[:4000] + "\n…"
        parts.extend(["", "Сопоставление блоков и ролей:", roles])
    parts.extend(["", "Фрагмент org_json:", org_json_excerpt])
    return "\n".join(parts)


def _rule_block(question: str) -> str | None:
    q = question.strip()
    if len(q) < MIN_QUESTION_LEN:
        return "Вопрос слишком короткий. Сформулируйте конкретнее (от 8 символов)."
    if len(q) > MAX_QUESTION_LEN:
        return "Вопрос слишком длинный. Сократите до 800 символов."
    for pat in _OFF_TOPIC_PATTERNS:
        if pat.search(q):
            return "Запрос не относится к оргструктуре и схеме из этого отчёта."
    return None


def _parse_gate_line(line: str) -> tuple[bool, str]:
    text = line.strip()
    upper = text.upper()
    if upper.startswith("ALLOW"):
        reason = text[5:].lstrip("—-: ").strip() or "в теме диагностики"
        return True, reason
    if upper.startswith("DENY"):
        reason = text[4:].lstrip("—-: ").strip() or "вне темы диагностики"
        return False, reason
    if "DENY" in upper:
        return False, text
    if "ALLOW" in upper:
        return True, text
    return False, "не удалось классифицировать запрос"


def check_question_allowed(
    question: str,
    *,
    result: DiagnosisResult,
    client: OpenAI | None = None,
    gate_model: str = GATE_MODEL,
) -> FollowupReply:
    """Проверка релевантности без полного ответа (экономия токенов)."""
    blocked = _rule_block(question)
    if blocked:
        return FollowupReply(allowed=False, text="", gate_reason=blocked)

    require_api_key()
    client = client or OpenAI()
    context_hint = (
        f"Тип: {result.org_type}. Боль: {result.pain[:200]}. "
        "Есть иерархия, упрощённые блоки и выводы pass1/pass2."
    )
    user_content = (
        f"{_load_gate_prompt()}\n\n"
        f"Контекст анализа: {context_hint}\n\n"
        f"Вопрос пользователя:\n{question.strip()}"
    )
    response = client.chat.completions.create(
        model=gate_model,
        messages=[
            {"role": "system", "content": "Отвечай только одной строкой ALLOW или DENY."},
            {"role": "user", "content": user_content},
        ],
        temperature=0,
        max_tokens=120,
    )
    line = response.choices[0].message.content.strip()
    allowed, reason = _parse_gate_line(line)
    return FollowupReply(allowed=allowed, text="", gate_reason=reason)


def answer_followup_question(
    question: str,
    *,
    result: DiagnosisResult,
    history: list[FollowupTurn],
    contact: str = "",
    client: OpenAI | None = None,
    gate_model: str = GATE_MODEL,
    answer_model: str = ANSWER_MODEL,
) -> FollowupReply:
    gate = check_question_allowed(
        question, result=result, client=client, gate_model=gate_model
    )
    if not gate.allowed:
        return FollowupReply(
            allowed=False,
            text=_rejection_message(gate.gate_reason, contact),
            gate_reason=gate.gate_reason,
        )

    require_api_key()
    client = client or OpenAI()
    context = build_followup_context(result, contact=contact)
    history_block = ""
    if history:
        lines = []
        for i, turn in enumerate(history, 1):
            if not turn.allowed:
                continue
            lines.append(f"Q{i}: {turn.question}\nA{i}: {turn.answer}")
        if lines:
            history_block = "\n\nПредыдущие уточнения в этой сессии:\n" + "\n\n".join(
                lines
            )

    user_content = f"""Контекст диагностики:
{context}
{history_block}

Вопрос пользователя:
{question.strip()}
"""
    response = client.chat.completions.create(
        model=answer_model,
        messages=[
            {"role": "system", "content": _load_answer_prompt()},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
        max_tokens=900,
    )
    answer = response.choices[0].message.content.strip()
    return FollowupReply(allowed=True, text=answer, gate_reason=gate.gate_reason)


def _rejection_message(reason: str, contact: str) -> str:
    c = (contact or default_contact()).strip()
    return (
        f"Этот вопрос нельзя обработать в рамках уточнений к отчёту: {reason}.\n\n"
        f"Доступны только вопросы по оргсхеме и выводам этой диагностики "
        f"(не более {max_followup_questions()} за сессию). "
        f"Для развёрнутой консультации обратитесь к консультанту: {c}."
    )


def limit_reached_message(*, contact: str = "") -> str:
    c = (contact or default_contact()).strip()
    n = max_followup_questions()
    return (
        f"Исчерпан лимит уточняющих вопросов ({n} за одну диагностику). "
        f"Чтобы не расходовать платный доступ на посторонние запросы, "
        f"дальнейшие обсуждения — через консультанта: {c}."
    )

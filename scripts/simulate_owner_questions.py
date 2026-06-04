"""
ВРЕМЕННЫЙ скрипт: смоделировать вопросы собственника и ответы follow-up.

Не подключён к Streamlit/пайплайну. После оценки сценариев можно не запускать.

  python scripts/simulate_owner_questions.py --stem medclinic3
  python scripts/simulate_owner_questions.py --stem medclinic3 --examples-only
  python scripts/simulate_owner_questions.py --stem medclinic3 --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openai import OpenAI

from orgdiag.config import default_contact, require_api_key
from orgdiag.followup_chat import FollowupTurn, answer_followup_question, build_followup_context
from orgdiag.paths import CACHE_DIR, PROMPTS_DIR
from orgdiag.pipeline import DiagnosisResult
from orgdiag.prompts import load_prompt

# Типичные вопросы для medclinic3 (очереди, порядок блоков, совмещение ролей)
EXAMPLE_QUESTIONS_MEDCLINIC3: tuple[str, ...] = (
    "Почему у нас маркетинг стоит после производства — это же противоречит эталону?",
    "Обязательно ли сейчас вводить отдельный блок «Кадры» или можно отложить?",
    "Как совмещение финдиректора и рекламы связано с перегрузом администраторов?",
    "Два директора наверху — это нормально или мешает управляемости?",
    "С чего начать выравнивание блоков, чтобы сократить очереди быстрее всего?",
    "Нужен ли отдельный руководитель маркетинга вместо отдела продаж?",
    "Почему в отчёте нет контроля качества — мы рискуем по сервису?",
    "Главный врач в блоке производства — не дублирует ли он управление клиникой?",
)

SIM_PROMPT = "owner_questions_sim_prompt.txt"


def load_from_cache(stem: str) -> DiagnosisResult:
    cache_dir = CACHE_DIR / stem
    summary_path = cache_dir / "summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"Нет {summary_path}")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    pass1_path = cache_dir / "pass1.txt"
    pass2_path = cache_dir / "pass2.txt"
    pass1 = pass1_path.read_text(encoding="utf-8") if pass1_path.exists() else ""
    pass2 = pass2_path.read_text(encoding="utf-8") if pass2_path.exists() else ""

    org_json_path = CACHE_DIR / f"{stem}_org.json"
    org_json = (
        json.loads(org_json_path.read_text(encoding="utf-8"))
        if org_json_path.exists()
        else {}
    )

    return DiagnosisResult(
        image=Path(summary.get("image", stem)),
        org_type=summary.get("org_type", ""),
        pain=summary.get("pain", ""),
        org_json=org_json,
        hierarchy_text=summary.get("hierarchy", ""),
        simple_structure=summary.get("simple_structure", ""),
        compare_text=summary.get("compare", ""),
        pain_analysis_text=summary.get("pain_analysis", ""),
        pass1_text=pass1 or summary.get("pass1", ""),
        pass2_text=pass2 or summary.get("pass2", ""),
    )


def generate_owner_questions(
    result: DiagnosisResult,
    *,
    count: int = 8,
    client: OpenAI | None = None,
) -> list[str]:
    require_api_key()
    client = client or OpenAI()
    template = load_prompt(SIM_PROMPT)
    prompt = template.replace("{count}", str(count))
    context = build_followup_context(result)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "Верни только список вопросов, по одному на строку.",
            },
            {
                "role": "user",
                "content": f"{prompt}\n\n---\nКонтекст:\n{context[:12000]}",
            },
        ],
        temperature=0.4,
        max_tokens=900,
    )
    raw = response.choices[0].message.content.strip()
    lines = []
    for line in raw.splitlines():
        line = re.sub(r"^\s*\d+[\.\)]\s*", "", line.strip())
        if len(line) >= 12:
            lines.append(line)
    return lines[:count]


def run_simulation(
    stem: str,
    *,
    count: int,
    examples_only: bool,
    dry_run: bool,
    output: Path | None,
) -> Path:
    result = load_from_cache(stem)
    if examples_only:
        questions = list(EXAMPLE_QUESTIONS_MEDCLINIC3[:count])
    else:
        questions = generate_owner_questions(result, count=count)

    out_path = output or (CACHE_DIR / stem / "owner_qa_simulation.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Симуляция вопросов собственника — {stem}",
        f"Дата: {datetime.now().isoformat(timespec='seconds')}",
        f"Боль: {result.pain}",
        "",
        "## Сгенерированные вопросы",
        "",
    ]
    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. {q}")
    lines.append("")

    if dry_run:
        lines.append("*(режим --dry-run: ответы не запрашивались)*")
        out_path.write_text("\n".join(lines), encoding="utf-8")
        return out_path

    contact = default_contact()
    history: list[FollowupTurn] = []
    lines.append("## Ответы (follow-up, как в UI)")
    lines.append("")

    for i, question in enumerate(questions, 1):
        reply = answer_followup_question(
            question,
            result=result,
            history=[t for t in history if t.allowed],
            contact=contact,
        )
        history.append(FollowupTurn(question=question, answer=reply.text, allowed=reply.allowed))
        lines.extend(
            [
                f"### Вопрос {i}",
                "",
                question,
                "",
                f"**Разрешён gate:** {'да' if reply.allowed else 'нет'}",
                "",
                reply.text,
                "",
                "---",
                "",
            ]
        )

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Симуляция вопросов собственника")
    parser.add_argument("--stem", default="medclinic3")
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument(
        "--examples-only",
        action="store_true",
        help="Взять встроенный список (без LLM для генерации вопросов)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только список вопросов, без ответов API",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    out = run_simulation(
        args.stem,
        count=args.count,
        examples_only=args.examples_only,
        dry_run=args.dry_run,
        output=args.output,
    )
    print(out)


if __name__ == "__main__":
    main()

"""
Пересборка коллекции: анализ схем (при необходимости) + боли + вопросы LLM.

  python scripts/build_questions_collection.py
  python scripts/build_questions_collection.py --skip-analysis
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from batch_gallery_pipeline import (
    EXTRA_CASES,
    GALLERY_CASES,
    _analysis_ready,
    _image_stem,
    _load_result,
    _run_analysis,
)
from orgdiag.owner_questions import (
    build_master_questions_markdown,
    default_questions_html_path,
    default_questions_text_path,
    generate_owner_questions,
    write_master_questions_html,
    write_questions_html,
    write_questions_text,
)
from orgdiag.paths import CACHE_DIR, HTML_OUT_DIR

COLLECTION_MD = ROOT / "docs" / "collection_owner_questions.md"
MASTER_COLLECTION_MD = ROOT / "docs" / "collection_all_owner_questions.md"
MASTER_COLLECTION_HTML = HTML_OUT_DIR / "collection_all_owner_questions.html"
PAINS_JSON = ROOT / "data" / "gallery_case_pains.json"


def _build_collection_md(rows: list[dict]) -> str:
    lines = [
        "# Коллекция: условные боли и дополнительные вопросы",
        "",
        f"Дата сборки: {date.today().isoformat()}",
        "",
        "Для каждой схемы из `images/`: условное название, тип предприятия, "
        "управленческая боль (ввод для анализа) и 8 вероятных вопросов собственника "
        "после заключения (LLM по результатам pass1/pass2).",
        "",
        "HTML вопросов: `html_out/questions_<alias>_<дата>.html`",
        "",
        "## Сводная таблица болей",
        "",
        "| Условное имя | Файл схемы | Тип | Управленческая боль |",
        "|---|---|---|---|",
    ]
    for row in rows:
        pain = row["pain"].replace("|", "\\|")
        lines.append(
            f"| {row['alias']} | `{row['image']}` | {row['org_type']} | {pain} |"
        )
    lines.append("")

    for row in rows:
        lines.extend(
            [
                f"## {row['alias']}",
                "",
                f"**Файл схемы:** `{row['image']}`  ",
                f"**Тип предприятия:** {row['org_type']}  ",
                f"**Условная боль:** {row['pain']}  ",
                f"**Отчёт HTML:** `{row.get('report_html') or '—'}`  ",
                f"**Вопросы (текст):** `{row['txt']}`  ",
                f"**Вопросы (HTML):** `{row['html']}`  ",
                "",
                "### Дополнительные вопросы",
                "",
            ]
        )
        for i, q in enumerate(row["questions"], 1):
            lines.append(f"{i}. {q}")
        lines.append("")
    return "\n".join(lines)


def _process_case(case: dict[str, str], *, run_analysis: bool, question_count: int) -> dict | None:
    alias = case["alias"]
    stem = case.get("cache_stem") or _image_stem(case["image"])

    if run_analysis and not _analysis_ready(stem):
        print(f"[analysis] {case['image']} -> {alias}", flush=True)
        result = _run_analysis(case)
    else:
        if not _analysis_ready(stem):
            print(f"SKIP {alias}: нет анализа", file=sys.stderr, flush=True)
            return None
        print(f"[questions] {stem} ({alias})", flush=True)
        result = _load_result(stem, case)

    questions = generate_owner_questions(result, count=question_count)

    txt_path = default_questions_text_path(stem, CACHE_DIR)
    write_questions_text(
        txt_path,
        alias=alias,
        image_file=case["image"],
        org_type=case["org_type"],
        pain=case["pain"],
        questions=questions,
        pass1_excerpt=result.pass1_text[:600],
        pass2_excerpt=result.pass2_text[:600],
    )
    html_path = default_questions_html_path(alias, HTML_OUT_DIR)
    write_questions_html(
        html_path,
        alias=alias,
        image_file=case["image"],
        org_type=case["org_type"],
        pain=case["pain"],
        questions=questions,
    )
    return {
        "alias": alias,
        "stem": stem,
        "image": case["image"],
        "org_type": case["org_type"],
        "pain": case["pain"],
        "questions": questions,
        "txt": str(txt_path),
        "html": str(html_path),
        "report_html": str(result.html_path) if result.html_path else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Пересборка коллекции болей и вопросов")
    parser.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Не запускать Vision/LLM-анализ, только вопросы по кэшу",
    )
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--case", help="Один кейс по alias или имени файла")
    args = parser.parse_args()

    all_cases = list(GALLERY_CASES) + list(EXTRA_CASES)
    if args.case:
        key = args.case.lower()
        all_cases = [
            c
            for c in all_cases
            if key in c["alias"].lower()
            or key in c["image"].lower()
            or key == _image_stem(c["image"]).lower()
        ]

    PAINS_JSON.write_text(
        json.dumps(
            [
                {
                    "alias": c["alias"],
                    "image": c["image"],
                    "org_type": c["org_type"],
                    "pain": c["pain"],
                }
                for c in all_cases
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    rows: list[dict] = []
    for case in all_cases:
        try:
            row = _process_case(
                case,
                run_analysis=not args.skip_analysis,
                question_count=args.count,
            )
            if row:
                rows.append(row)
        except Exception as e:
            print(f"ERROR {case.get('alias')}: {e}", file=sys.stderr, flush=True)

    COLLECTION_MD.write_text(_build_collection_md(rows), encoding="utf-8")
    MASTER_COLLECTION_MD.write_text(
        build_master_questions_markdown(rows), encoding="utf-8"
    )
    write_master_questions_html(MASTER_COLLECTION_HTML, rows)
    print(f"\n{COLLECTION_MD}", flush=True)
    print(f"Сводный файл (MD): {MASTER_COLLECTION_MD}", flush=True)
    print(f"Сводный файл (HTML): {MASTER_COLLECTION_HTML}", flush=True)
    print(f"Кейсов: {len(rows)}/{len(all_cases)}", flush=True)
    print(f"Боли: {PAINS_JSON}", flush=True)


if __name__ == "__main__":
    main()

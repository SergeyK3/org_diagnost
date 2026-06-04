"""
Пакет: анализ схем из images/, генерация вероятных вопросов, HTML и сводная коллекция.

  python scripts/batch_gallery_pipeline.py
  python scripts/batch_gallery_pipeline.py --only-questions   # только вопросы по готовому кэшу
  python scripts/batch_gallery_pipeline.py --case medclinic3  # один кейс
  python scripts/batch_gallery_pipeline.py --regen-html      # только HTML из кэша
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orgdiag.config import RunConfig
from orgdiag.owner_questions import (
    default_questions_html_path,
    default_questions_text_path,
    generate_owner_questions,
    write_questions_html,
    write_questions_text,
)
from orgdiag.paths import CACHE_DIR, HTML_OUT_DIR, IMAGES_DIR
from orgdiag.pipeline import DiagnosisResult, run_diagnosis

# Пересборка HTML без LLM
from scripts.regen_html_from_cache import regen_one as regen_html_for_stem  # noqa: E402

# Исходные схемы (без *result*, служебных medclinic3_*)
GALLERY_CASES: tuple[dict[str, str], ...] = (
    {
        "image": "bd12 transport new.png",
        "alias": "transport_12",
        "org_type": "транспортная компания",
        "pain": "Срывы сроков доставки, диспетчеры вручную закрывают сбои, собственник в операционке",
    },
    {
        "image": "bd12new.png",
        "alias": "proizvodstvo_12b",
        "org_type": "производственная компания",
        "pain": "Падает рентабельность, между подразделениями «стены», нет единого потока решений",
    },
    {
        "image": "bd13 autoservice2.png",
        "alias": "autoservice_s2",
        "org_type": "автосервис",
        "pain": "Ручное управление, хаос, собственник устал, жалобы на качество, кассовые разрывы",
    },
    {
        "image": "bd14 internetshop new.png",
        "alias": "shop_gamma",
        "org_type": "интернет-магазин",
        "pain": "Просели продажи, маркетплейс давит на маржу, склад и продажи не согласованы",
    },
    {
        "image": "bd15 zakupki.png",
        "alias": "zakup_office",
        "org_type": "отдел закупок / дистрибуция",
        "pain": "Срывы поставок, закупки не успевают за спросом, зависимость от ключевых поставщиков",
    },
    {
        "image": "medclinic.png",
        "alias": "klinika_a",
        "org_type": "медицинская клиника",
        "pain": "Низкая загрузка врачей, ручная запись, собственник решает всё сам",
    },
    {
        "image": "medclinic2.png",
        "alias": "klinika_b",
        "org_type": "медицинская клиника",
        "pain": "Простаивает оборудование, текучка среднего медперсонала, нет прозрачности по загрузке",
    },
    {
        "image": "medclinic3.png",
        "alias": "klinika_g",
        "org_type": "медицинская клиника",
        "pain": "Перегруз администраторов, очереди, жалобы на сервис",
    },
    {
        "image": "мебельная.png",
        "alias": "mebel_x",
        "org_type": "мебельное производство",
        "pain": "Срывы сроков по заказам, брак на отгрузке, план продаж не сходится с мощностями",
    },
)

EXTRA_CASES: tuple[dict[str, str], ...] = (
    {
        "image": "(загрузка UI)",
        "alias": "autoservice_upload",
        "org_type": "автосервис",
        "pain": "Ручное управление, хаос, собственник устал, жалобы на качество, кассовые разрывы",
        "cache_stem": "orgdiag_upload",
    },
)


def _image_stem(image_name: str) -> str:
    return Path(image_name).stem


def _analysis_ready(stem: str) -> bool:
    d = CACHE_DIR / stem
    return (d / "pass1.txt").exists() and (d / "pass2.txt").exists()


def _load_result(stem: str, case: dict[str, str]) -> DiagnosisResult:
    cache_dir = CACHE_DIR / stem
    summary_path = cache_dir / "summary.json"
    org_json_path = CACHE_DIR / f"{stem}_org.json"
    org_json = (
        json.loads(org_json_path.read_text(encoding="utf-8"))
        if org_json_path.exists()
        else {}
    )
    summary = (
        json.loads(summary_path.read_text(encoding="utf-8"))
        if summary_path.exists()
        else {}
    )
    pass1 = (cache_dir / "pass1.txt").read_text(encoding="utf-8") if (cache_dir / "pass1.txt").exists() else ""
    pass2 = (cache_dir / "pass2.txt").read_text(encoding="utf-8") if (cache_dir / "pass2.txt").exists() else ""
    return DiagnosisResult(
        image=IMAGES_DIR / case["image"],
        org_type=case["org_type"],
        pain=case["pain"],
        org_json=org_json,
        hierarchy_text=summary.get("hierarchy", ""),
        simple_structure=summary.get("simple_structure", ""),
        compare_text=summary.get("compare", ""),
        pain_analysis_text=summary.get("pain_analysis", ""),
        pass1_text=pass1,
        pass2_text=pass2,
    )


def _run_analysis(case: dict[str, str]) -> DiagnosisResult:
    image_path = IMAGES_DIR / case["image"]
    if not image_path.exists():
        raise FileNotFoundError(image_path)
    cfg = RunConfig(
        image=image_path,
        org_type=case["org_type"],
        org_name=case["alias"],
        pain=case["pain"],
        output_format="html",
    )
    return run_diagnosis(cfg)


def _case_stem(case: dict[str, str]) -> str:
    return case.get("cache_stem") or _image_stem(case["image"])


def _process_case(
    case: dict[str, str],
    *,
    only_questions: bool,
    regen_html: bool,
    question_count: int,
) -> dict:
    stem = _case_stem(case)
    alias = case["alias"]

    if regen_html:
        if not _analysis_ready(stem):
            raise FileNotFoundError(f"Нет кэша анализа для {stem}")
        print(f"[regen-html] {stem} ({alias})")
        report_path = regen_html_for_stem(
            stem,
            pain_fallback=case.get("pain", ""),
            with_qa=True,
        )
        return {
            "alias": alias,
            "stem": stem,
            "image": case["image"],
            "org_type": case["org_type"],
            "pain": case["pain"],
            "questions": [],
            "report_html": report_path,
        }

    if only_questions or _analysis_ready(stem):
        if not _analysis_ready(stem):
            raise FileNotFoundError(f"Нет кэша анализа для {stem}")
        if _analysis_ready(stem) and not only_questions:
            print(f"[кэш] анализ есть, только вопросы: {stem} ({alias})")
        else:
            print(f"[questions] {stem} ({alias})")
        result = _load_result(stem, case)
    else:
        print(f"[run] {case['image']} -> {alias}")
        result = _run_analysis(case)

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
        "txt": txt_path,
        "html": html_path,
        "report_html": result.html_path,
    }


def _build_collection_md(rows: list[dict]) -> str:
    lines = [
        "# Коллекция вероятных вопросов собственника",
        "",
        f"Дата сборки: {date.today().isoformat()}",
        "",
        "Вопросы сгенерированы по результатам оргдиагностики (LLM), для обучения сценария уточнений в UI.",
        "",
    ]
    for row in rows:
        lines.extend(
            [
                f"## {row['alias']}",
                "",
                f"- **Файл схемы:** `{row['image']}`",
                f"- **Профиль:** {row['org_type']}",
                f"- **Условная боль:** {row['pain']}",
                f"- **Текст вопросов:** `{row['txt']}`",
                f"- **HTML:** `{row['html']}`",
                "",
            ]
        )
        for i, q in enumerate(row["questions"], 1):
            lines.append(f"{i}. {q}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only-questions", action="store_true")
    parser.add_argument(
        "--regen-html",
        action="store_true",
        help="Пересобрать HTML-отчёты из кэша (новый шаблон, без LLM)",
    )
    parser.add_argument("--case", help="Фильтр по alias или имени файла")
    parser.add_argument("--count", type=int, default=8)
    args = parser.parse_args()

    cases = list(GALLERY_CASES)
    if args.case:
        key = args.case.lower()
        cases = [
            c
            for c in cases
            if key in c["alias"].lower()
            or key in c["image"].lower()
            or key == _image_stem(c["image"]).lower()
        ]
        if not cases:
            raise SystemExit(f"Кейс не найден: {args.case}")

    rows: list[dict] = []
    for case in cases:
        try:
            rows.append(
                _process_case(
                    case,
                    only_questions=args.only_questions,
                    regen_html=args.regen_html,
                    question_count=args.count,
                )
            )
        except Exception as e:
            print(f"ОШИБКА {case['image']}: {e}", file=sys.stderr)

    if args.regen_html:
        print(f"\nHTML пересобран: {len(rows)}/{len(cases)} кейсов")
        return

    coll_path = ROOT / "docs" / "collection_owner_questions.md"
    coll_path.write_text(_build_collection_md(rows), encoding="utf-8")
    print(f"\nКоллекция: {coll_path}")
    print(f"Кейсов обработано: {len(rows)}/{len(cases)}")


if __name__ == "__main__":
    main()

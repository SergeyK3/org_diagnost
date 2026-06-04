"""
Пересобрать HTML-отчёты из cache/<stem>/ без повторного Vision/LLM.

  python scripts/regen_html_from_cache.py --stem medclinic3
  python scripts/regen_html_from_cache.py --all
  python scripts/regen_html_from_cache.py --all --with-qa
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

from orgdiag.config import default_contact
from orgdiag.owner_questions import resolve_owner_qa_for_report
from orgdiag.paths import CACHE_DIR, HTML_OUT_DIR, REFERENCE_ORG_SCHEME_IMAGE
from orgdiag.pipeline import DiagnosisResult
from orgdiag.report_html import default_html_path, generate_html_report

def _load_gallery_cases() -> list[dict[str, str]]:
    path = ROOT / "data" / "gallery_case_pains.json"
    cases: list[dict[str, str]] = json.loads(path.read_text(encoding="utf-8"))
    for c in cases:
        if c.get("alias") == "autoservice_upload":
            c["cache_stem"] = "orgdiag_upload"
    return cases


def _image_stem(image_name: str) -> str:
    return Path(image_name).stem


def _case_stem(case: dict[str, str]) -> str:
    return case.get("cache_stem") or _image_stem(case["image"])


def _visual_paths(stem: str) -> dict[str, Path]:
    out_dir = CACHE_DIR / stem
    keys = ("block_source", "block_analyzed", "block_reference", "admin_roles")
    paths: dict[str, Path] = {}
    for key in keys:
        p = out_dir / f"{stem}_{key}.png"
        if p.exists():
            paths[key] = p
    if "block_reference" not in paths and REFERENCE_ORG_SCHEME_IMAGE.exists():
        paths["block_reference"] = REFERENCE_ORG_SCHEME_IMAGE
    return paths


def load_from_cache(stem: str, *, pain_fallback: str = "") -> tuple[DiagnosisResult, str, str, str]:
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

    image_stem = Path(summary.get("image", stem)).stem
    pain = summary.get("pain") or pain_fallback
    result = DiagnosisResult(
        image=Path(summary.get("image", stem)),
        org_type=summary.get("org_type", ""),
        pain=pain,
        org_json=org_json,
        hierarchy_text=summary.get("hierarchy", ""),
        simple_structure=summary.get("simple_structure", ""),
        compare_text=summary.get("compare", ""),
        pain_analysis_text=summary.get("pain_analysis", ""),
        pass1_text=pass1 or summary.get("pass1", ""),
        pass2_text=pass2 or summary.get("pass2", ""),
    )
    org_name = summary.get("org_name") or image_stem
    return result, org_name, summary.get("org_type", result.org_type), pain


def regen_one(
    stem: str,
    *,
    pain_fallback: str = "",
    contact: str = "",
    with_qa: bool = False,
    refresh_qa: bool = False,
) -> Path:
    result, org_name, org_type, pain = load_from_cache(stem, pain_fallback=pain_fallback)
    dest = default_html_path(HTML_OUT_DIR, org_name, date.today())
    owner_qa = None
    if with_qa:
        owner_qa = resolve_owner_qa_for_report(
            result,
            stem,
            CACHE_DIR,
            contact=contact or default_contact(),
            refresh=refresh_qa,
        )
    generate_html_report(
        dest,
        org_name=org_name,
        org_type=org_type,
        pain=pain,
        visual_paths=_visual_paths(stem),
        pass1_text=result.pass1_text,
        pass2_text=result.pass2_text,
        contact=contact,
        owner_qa=owner_qa,
    )
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="Пересобрать HTML из кэша")
    parser.add_argument("--stem", help="Имя каталога в cache/")
    parser.add_argument("--all", action="store_true", help="Все кейсы из images/ (галерея)")
    parser.add_argument("--contact", default="")
    parser.add_argument(
        "--with-qa",
        action="store_true",
        help="Добавить 3 вопроса собственника и ответы LLM (кэш owner_qa_report.json)",
    )
    parser.add_argument(
        "--refresh-qa",
        action="store_true",
        help="Перегенерировать Q&A даже при наличии кэша",
    )
    args = parser.parse_args()

    if not args.all and not args.stem:
        parser.error("Укажите --stem или --all")

    if args.all:
        cases = _load_gallery_cases()
        ok, fail = 0, 0
        for case in cases:
            stem = _case_stem(case)
            try:
                dest = regen_one(
                    stem,
                    pain_fallback=case.get("pain", ""),
                    contact=args.contact,
                    with_qa=args.with_qa,
                    refresh_qa=args.refresh_qa,
                )
                print(f"OK {case['alias']}: {dest}")
                ok += 1
            except Exception as e:
                print(f"FAIL {case['alias']} ({stem}): {e}", file=sys.stderr)
                fail += 1
        print(f"\nГотово: {ok} OK, {fail} ошибок")
        return 1 if fail else 0

    dest = regen_one(
        args.stem,
        contact=args.contact,
        with_qa=args.with_qa,
        refresh_qa=args.refresh_qa,
    )
    print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from orgdiag.config import RunConfig, load_env
from orgdiag.paths import CASES_DIR, resolve_path
from orgdiag.pipeline import run_diagnosis


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="orgdiag",
        description="Диагностика оргструктуры по изображению.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Один кейс: изображение → HTML/PDF")
    run_p.add_argument("--image", "-i", help="Путь к изображению оргструктуры")
    run_p.add_argument("--image-url", help="URL изображения (скачать)")
    run_p.add_argument("--org-type", "-t", required=True, help="Тип предприятия")
    run_p.add_argument("--org-name", help="Краткое название организации (для имени HTML)")
    run_p.add_argument("--pain", "-p", required=True, help="Управленческая боль")
    run_p.add_argument("--contact", help="Контакт разработчика в итоге отчёта")
    run_p.add_argument("--output", "-o", help="Путь к PDF")
    run_p.add_argument("--html-output", help="Путь к HTML")
    run_p.add_argument(
        "--format",
        choices=["html", "pdf", "both"],
        default="html",
        help="Формат отчёта (по умолчанию html)",
    )
    run_p.add_argument("--vision-model", default="gpt-4o-mini")
    run_p.add_argument("--simplify-model", default="gpt-4o")
    run_p.add_argument("--cache-dir", help="Каталог кэша org_json")
    run_p.add_argument("--no-cache", action="store_true")
    run_p.add_argument("--refresh-vision", action="store_true")
    run_p.add_argument("--skip-vision", action="store_true", help="Только кэш org_json")
    run_p.add_argument(
        "--with-llm-diagnosis",
        action="store_true",
        help="Legacy: Step1 по матрице боли в PDF",
    )
    run_p.add_argument(
        "--with-pain-matrix",
        action="store_true",
        help="Step1 по матрице боли",
    )
    run_p.add_argument(
        "--no-llm",
        action="store_true",
        help="Без LLM-выводов pass1/pass2 (только диаграммы)",
    )
    run_p.add_argument("--dry-run", action="store_true")
    run_p.add_argument("--no-visuals", action="store_true")

    batch_p = sub.add_parser("batch", help="Пакетный прогон YAML-кейсов")
    batch_p.add_argument("cases", nargs="*", help="Файлы cases/*.yaml")
    batch_p.add_argument("--format", choices=["html", "pdf", "both"], default="html")
    batch_p.add_argument("--with-llm-diagnosis", action="store_true")
    batch_p.add_argument("--with-pain-matrix", action="store_true")
    batch_p.add_argument("--refresh-vision", action="store_true")
    batch_p.add_argument("--no-llm", action="store_true")

    return p


def _cfg_from_args(args: argparse.Namespace) -> RunConfig:
    image_path: Path | None = None
    if getattr(args, "image", None):
        image_path = resolve_path(args.image)
    elif not getattr(args, "image_url", None):
        raise SystemExit("Укажите --image или --image-url")

    if image_path is None:
        image_path = Path("_url_placeholder.png")

    output = resolve_path(args.output) if getattr(args, "output", None) else None
    html_output = (
        resolve_path(args.html_output) if getattr(args, "html_output", None) else None
    )
    cache_dir = resolve_path(args.cache_dir) if getattr(args, "cache_dir", None) else None

    no_llm = getattr(args, "no_llm", False)
    return RunConfig(
        image=image_path,
        org_type=args.org_type,
        org_name=getattr(args, "org_name", "") or "",
        pain=args.pain,
        contact=getattr(args, "contact", "") or "",
        vision_model=args.vision_model,
        simplify_model=args.simplify_model,
        output=output,
        html_output=html_output,
        cache_dir=cache_dir,
        use_cache=not args.no_cache and not getattr(args, "refresh_vision", False),
        skip_vision=getattr(args, "skip_vision", False),
        with_llm_diagnosis=getattr(args, "with_llm_diagnosis", False),
        with_pain_matrix=getattr(args, "with_pain_matrix", False)
        or getattr(args, "with_llm_diagnosis", False),
        with_block_analysis=not no_llm,
        with_admin_analysis=not no_llm,
        output_format=getattr(args, "format", "html"),
        image_url=getattr(args, "image_url", None),
        dry_run=getattr(args, "dry_run", False),
        save_visuals=not getattr(args, "no_visuals", False),
    )


def _load_yaml_case(path: Path) -> RunConfig:
    try:
        import yaml
    except ImportError as e:
        raise RuntimeError("Для batch установите PyYAML: pip install pyyaml") from e

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    image = resolve_path(data["image"])
    output = resolve_path(data["output"]) if data.get("output") else None
    html_output = (
        resolve_path(data["html_output"]) if data.get("html_output") else None
    )
    return RunConfig(
        image=image,
        org_type=str(data["org_type"]),
        org_name=str(data.get("org_name", "")),
        pain=str(data["pain"]),
        contact=str(data.get("contact", "")),
        vision_model=data.get("vision_model", "gpt-4o-mini"),
        simplify_model=data.get("simplify_model", "gpt-4o"),
        output=output,
        html_output=html_output,
        cache_dir=resolve_path(data["cache_dir"]) if data.get("cache_dir") else None,
        use_cache=not data.get("refresh_vision", False),
        skip_vision=data.get("skip_vision", False),
        with_llm_diagnosis=data.get("with_llm_diagnosis", False),
        with_pain_matrix=data.get("with_pain_matrix", False),
        output_format=data.get("format", "html"),
        image_url=data.get("image_url"),
    )


def cmd_run(args: argparse.Namespace) -> int:
    if args.refresh_vision:
        args.no_cache = True
    cfg = _cfg_from_args(args)
    if cfg.dry_run:
        load_env()
        from orgdiag.config import require_api_key

        errs = []
        try:
            require_api_key()
        except RuntimeError as e:
            errs.append(str(e))
        from orgdiag.pipeline import validate_inputs

        errs.extend(validate_inputs(cfg))
        if errs:
            print("dry-run: ошибки:")
            for e in errs:
                print(" -", e)
            return 1
        print("dry-run: OK")
        print(" image:", cfg.image)
        print(" org_type:", cfg.org_type)
        print(" org_name:", cfg.display_org_name)
        print(" pain:", cfg.pain[:80], "...")
        print(" format:", cfg.output_format)
        return 0

    result = run_diagnosis(cfg)
    if result.html_path:
        print("HTML:", result.html_path)
    if result.pdf_path:
        print("PDF:", result.pdf_path)
    print("Кэш org_json:", result.cache_path)
    if result.visual_paths:
        print("Картинки:")
        for key, path in result.visual_paths.items():
            print(f"  {key}: {path}")
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    if args.cases:
        paths = [resolve_path(c) for c in args.cases]
    else:
        CASES_DIR.mkdir(parents=True, exist_ok=True)
        paths = sorted(CASES_DIR.glob("*.yaml"))
    if not paths:
        print("Нет YAML-кейсов в", CASES_DIR)
        return 1

    failed = 0
    for path in paths:
        print("\n===", path.name, "===")
        try:
            cfg = _load_yaml_case(path)
            if args.refresh_vision:
                cfg.use_cache = False
            if args.with_llm_diagnosis:
                cfg.with_llm_diagnosis = True
            if args.with_pain_matrix:
                cfg.with_pain_matrix = True
            if args.no_llm:
                cfg.with_block_analysis = False
                cfg.with_admin_analysis = False
            cfg.output_format = args.format
            result = run_diagnosis(cfg)
            out = result.html_path or result.pdf_path
            print("OK →", out)
        except Exception as e:
            failed += 1
            print("ОШИБКА:", e)
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "batch":
        return cmd_batch(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

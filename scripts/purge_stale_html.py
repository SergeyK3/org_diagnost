"""Удалить HTML в html_out/ с датой в имени раньше указанной (по умолчанию 2026-06-05)."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML_OUT = ROOT / "html_out"
DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})(?:\.html)?$|_(\d{4}-\d{2}-\d{2})_")


def file_date(name: str) -> str | None:
    m = DATE_RE.search(name)
    if not m:
        return None
    return m.group(1) or m.group(2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--keep-from",
        default="2026-06-05",
        help="Оставить файлы с датой >= этой (YYYY-MM-DD)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    keep_from = args.keep_from

    removed = []
    for path in sorted(HTML_OUT.iterdir()) if HTML_OUT.exists() else []:
        if not path.is_file() or path.suffix.lower() != ".html":
            continue
        d = file_date(path.name)
        if d is None:
            continue
        if d < keep_from:
            removed.append(path)
            if not args.dry_run:
                path.unlink()

    for p in removed:
        print(f"{'would remove' if args.dry_run else 'removed'}: {p.name}")
    print(f"Всего: {len(removed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

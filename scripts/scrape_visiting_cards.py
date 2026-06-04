"""
Улучшенный парсер сайтов-визиток с оргструктурами (v2).
Учитывает ошибки v1: SSL fallback, больше страниц, мягче порог картинок, дедуп, статистика.

  python scripts/scrape_visiting_cards.py
  python scripts/scrape_visiting_cards.py --seeds url_collect/seed_urls.txt
  python scripts/scrape_visiting_cards.py --download --replace-v1
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from url_collect.scraper_core import (  # noqa: E402
    ScraperConfig,
    load_collection,
    load_seed_urls,
    make_session,
    next_alias,
    save_collection,
    save_errors,
    scrape_one_site,
    try_download_best_candidate,
)

URL_COLLECT = ROOT / "url_collect"
IMAGES_DIR = URL_COLLECT / "images"
COLLECTION_PATH = URL_COLLECT / "org_structure_collection.json"
ERRORS_V1_PATH = URL_COLLECT / "scrape_errors_v1.json"
ERRORS_PATH = URL_COLLECT / "scrape_errors.json"
STATS_PATH = URL_COLLECT / "scrape_stats.json"
URLS_FOUND_PATH = URL_COLLECT / "org_chart_urls.txt"


def _load_v1_error_stages(path: Path) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {e.get("stage", "") for e in data.get("errors", [])}


def _existing_source_urls(items: list[dict]) -> set[str]:
    return {it.get("source_url", "") for it in items if it.get("source_url")}


def main() -> int:
    parser = argparse.ArgumentParser(description="Парсер визиток v2 (улучшенный)")
    parser.add_argument("--seeds", type=Path, default=URL_COLLECT / "seed_urls.txt")
    parser.add_argument("--download", action="store_true", default=True)
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument(
        "--replace-v1",
        action="store_true",
        help="Удалить из коллекции записи с scraper=v1 перед добавлением v2",
    )
    parser.add_argument("--skip-existing", action="store_true", default=True)
    parser.add_argument("--force", action="store_true", help="Пересканировать даже известные URL")
    args = parser.parse_args()
    if args.no_download:
        args.download = False

    v1_stages = _load_v1_error_stages(ERRORS_V1_PATH)
    print(f"Стадии ошибок v1 (для отчёта): {sorted(v1_stages)}")

    cfg = ScraperConfig(
        timeout=30,
        max_pages_per_site=8,
        max_depth=2,
        delay_seconds=0.6,
        min_image_bytes=12_000,
        min_image_width=360,
        min_image_height=280,
        verify_ssl=True,
        allow_insecure_fallback=True,
        same_domain_only=True,
        validate_downloaded_image=True,
    )

    seeds = load_seed_urls(args.seeds)
    session = make_session(cfg)
    collection = load_collection(COLLECTION_PATH)
    items: list[dict] = list(collection.get("items", []))

    if args.replace_v1:
        items = [it for it in items if it.get("scraper") != "v1"]
        print("Удалены записи v1 из коллекции")

    known = _existing_source_urls(items)
    all_errors = []
    stage_counter: Counter[str] = Counter()
    status_counter: Counter[str] = Counter()
    new_urls: list[str] = []

    print(f"v2: {len(seeds)} URL")
    for seed in seeds:
        if args.skip_existing and not args.force and seed in known:
            print(f"SKIP (уже в коллекции): {seed}")
            continue

        print(f"\n=== {seed} ===")
        item, errors, cands = scrape_one_site(
            seed, cfg=cfg, session=session, on_progress=print
        )
        for e in errors:
            all_errors.append(e)
            stage_counter[e.stage] += 1

        if not item:
            status_counter["failed"] += 1
            print(f"  -> fail, кандидатов на страницах: {len(cands)}")
            continue

        item.alias = next_alias(items)
        if args.download and cands:
            IMAGES_DIR.mkdir(parents=True, exist_ok=True)
            dest = IMAGES_DIR / f"{item.alias}.png"
            path, picked, derrs = try_download_best_candidate(
                cands, dest, session, cfg, limit=6
            )
            all_errors.extend(derrs)
            for d in derrs:
                stage_counter[d.stage] += 1
            if path and picked:
                item.org_chart_url = picked.image_url
                item.page_url = picked.page_url
                item.score = picked.score
                item.local_image = str(path.relative_to(ROOT)).replace("\\", "/")
                item.status = "image_downloaded"
                status_counter["image_downloaded"] += 1
            else:
                item.status = "candidate_not_downloaded"
                status_counter["candidate_only"] += 1
        else:
            item.status = "candidate"
            status_counter["candidate"] += 1

        row = {
            "alias": item.alias,
            "source_url": item.source_url,
            "page_url": item.page_url,
            "org_chart_url": item.org_chart_url,
            "local_image": item.local_image,
            "org_type": item.org_type,
            "pain": item.pain,
            "status": item.status,
            "notes": item.notes,
            "score": round(item.score, 2),
            "scraper": "v2",
            "candidates_seen": len(cands),
        }
        items.append(row)
        known.add(seed)
        if item.org_chart_url:
            new_urls.append(item.org_chart_url)
        print(f"  -> {item.alias} [{item.status}] score={item.score:.1f}")

    collection["items"] = items
    collection["updated"] = datetime.now(timezone.utc).isoformat()
    collection["stats_hint"] = (
        "Для batch: привяжите org_type/pain, затем orgdiag run --image-url <org_chart_url>"
    )
    save_collection(COLLECTION_PATH, collection)

    save_errors(
        ERRORS_PATH,
        all_errors,
        {
            "version": "v2",
            "criterion": "иерархия: первый руководитель + ресурсники (ORG_STRUCTURE_CRITERION.md)",
            "improvements": [
                "только страницы org-structure, не about/team",
                "штраф photo/logo/banner/multimedia",
                "проверка файла Pillow: размер и светлый фон схемы",
                "reject SVG",
            ],
            "v1_error_stages_seen": sorted(v1_stages),
            "at": datetime.now(timezone.utc).isoformat(),
        },
    )

    stats = {
        "at": datetime.now(timezone.utc).isoformat(),
        "seeds_total": len(seeds),
        "collection_items": len(items),
        "by_status": dict(status_counter),
        "error_stages": dict(stage_counter),
        "errors_total": len(all_errors),
        "urls_with_chart": len(new_urls),
    }
    STATS_PATH.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    URLS_FOUND_PATH.write_text(
        "\n".join(new_urls) + ("\n" if new_urls else ""),
        encoding="utf-8",
    )

    print(f"\nКоллекция: {COLLECTION_PATH}")
    print(f"URL картинок: {URLS_FOUND_PATH}")
    print(f"Ошибки v2: {ERRORS_PATH} ({len(all_errors)})")
    print(f"Статистика: {STATS_PATH}")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

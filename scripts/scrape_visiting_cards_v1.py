"""
Пробный парсер сайтов-визиток (v1): минимальная логика, без fallback SSL и с жёсткими лимитами.
Собирает ошибки в url_collect/scrape_errors_v1.json.

  python scripts/scrape_visiting_cards_v1.py
  python scripts/scrape_visiting_cards_v1.py --seeds url_collect/seed_urls.txt
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from url_collect.scraper_core import (  # noqa: E402
    ScraperConfig,
    download_image,
    load_collection,
    load_seed_urls,
    make_session,
    next_alias,
    save_collection,
    save_errors,
    scrape_one_site,
)

URL_COLLECT = ROOT / "url_collect"
IMAGES_DIR = URL_COLLECT / "images"
COLLECTION_PATH = URL_COLLECT / "org_structure_collection.json"
ERRORS_PATH = URL_COLLECT / "scrape_errors_v1.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Пробный парсер визиток v1")
    parser.add_argument(
        "--seeds",
        type=Path,
        default=URL_COLLECT / "seed_urls.txt",
    )
    parser.add_argument("--download", action="store_true", help="Скачать лучшее изображение")
    args = parser.parse_args()

    cfg = ScraperConfig(
        timeout=15,
        max_pages_per_site=3,
        max_depth=1,
        delay_seconds=0.3,
        min_image_bytes=15_000,
        verify_ssl=True,
        allow_insecure_fallback=False,
        same_domain_only=True,
    )

    seeds = load_seed_urls(args.seeds)
    session = make_session(cfg)
    collection = load_collection(COLLECTION_PATH)
    items: list[dict] = list(collection.get("items", []))
    all_errors = []

    print(f"v1: {len(seeds)} URL, конфиг: pages={cfg.max_pages_per_site} depth={cfg.max_depth}")
    for seed in seeds:
        print(f"\n=== {seed} ===")
        item, errors, _cands = scrape_one_site(
            seed, cfg=cfg, session=session, on_progress=print
        )
        all_errors.extend(errors)
        if not item:
            print("  -> нет результата")
            continue

        item.alias = next_alias(items)
        if args.download and item.org_chart_url:
            dest = IMAGES_DIR / f"{item.alias}.png"
            IMAGES_DIR.mkdir(parents=True, exist_ok=True)
            from url_collect.scraper_core import ImageCandidate

            cand = ImageCandidate(
                image_url=item.org_chart_url,
                page_url=item.page_url,
                score=item.score,
            )
            path, derr = download_image(cand, dest, session, cfg)
            if derr:
                all_errors.append(derr)
                item.status = "candidate_not_downloaded"
            elif path:
                item.local_image = str(path.relative_to(ROOT)).replace("\\", "/")
                item.status = "image_downloaded"

        items.append(
            {
                "alias": item.alias,
                "source_url": item.source_url,
                "page_url": item.page_url,
                "org_chart_url": item.org_chart_url,
                "local_image": item.local_image,
                "org_type": item.org_type,
                "pain": item.pain,
                "status": item.status,
                "notes": item.notes,
                "score": item.score,
                "scraper": "v1",
            }
        )
        print(f"  -> {item.alias} score={item.score:.1f} {item.org_chart_url[:80]}...")

    collection["items"] = items
    collection["updated_v1"] = datetime.now(timezone.utc).isoformat()
    save_collection(COLLECTION_PATH, collection)
    save_errors(
        ERRORS_PATH,
        all_errors,
        {
            "version": "v1",
            "seeds": args.seeds.as_posix(),
            "count_seeds": len(seeds),
            "count_errors": len(all_errors),
            "at": datetime.now(timezone.utc).isoformat(),
        },
    )
    print(f"\nКоллекция: {COLLECTION_PATH} ({len(items)} записей)")
    print(f"Ошибки v1: {ERRORS_PATH} ({len(all_errors)} шт.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

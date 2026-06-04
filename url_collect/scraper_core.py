"""
Ядро парсера сайтов-визиток: поиск страниц и изображений с оргструктурой.

Критерий оргструктуры (см. ORG_STRUCTURE_CRITERION.md):
  иерархия, первый руководитель наверху, подчинённые / ресурсники ниже.
  Не: фото, баннеры, логотипы, «команда на фото».
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlparse, urlunparse

import requests

# --- Конфигурация по умолчанию (v2 переопределяет часть полей) ---

DEFAULT_USER_AGENT = (
    "OrgDiagUrlCollector/2.0 (+org structure hierarchy; research)"
)

# Страницы, где реально публикуют схему (не общий «about» / «команда»)
ORG_STRUCTURE_PAGE_HINTS = (
    "оргструктур",
    "организационн",
    "структур компани",
    "структура компании",
    "структура управления",
    "organizational structure",
    "organizational-structure",
    "org-structure",
    "orgstructure",
    "org-chart",
    "orgchart",
    "org_chart",
    "organigram",
    "organigrama",
    "иерарх",
    "подчин",
    "штатн",
    "схема управления",
    "management structure",
    "company structure",
)

# В URL/alt картинки — признаки именно схемы
ORG_STRUCTURE_IMAGE_HINTS = (
    "оргструктур",
    "orgstruct",
    "org-struct",
    "orgchart",
    "org-chart",
    "org_chart",
    "organigram",
    "organizational",
    "иерарх",
    "hierarchy",
    "структур",
    "structure",
    "chart",
    "подчин",
    "штат",
    "дерев",
    "tree",
    "схем",
    "scheme",
    "organizational-chart",
)

# Явно не оргструктура
IMAGE_NEGATIVE_HINTS = (
    "/photos/",
    "/photo/",
    "/avatars/",
    "/avatar/",
    "photo",
    "portrait",
    "portret",
    "portrait",
    "logo",
    "logotype",
    "icon",
    "favicon",
    "banner",
    "slider",
    "promo",
    "product",
    "продукт",
    "баннер",
    "логотип",
    "фото",
    "сотрудник",
    "employee",
    "team-photo",
    "illustration",
    "cover",
    "hero",
    "background",
    "pattern",
    "multimedia",
    "pfa-multimedia",
    "карточк",
    "лицо",
)

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")

# Минимальный score кандидата (на странице со «структурой» — ниже порог)
MIN_IMAGE_SCORE_ON_STRUCTURE_PAGE = 4.0
MIN_IMAGE_SCORE_OTHER_PAGE = 9.0
MIN_PAGE_STRUCTURE_SCORE = 4.0

# Дополнительно при review_mode (страницы «руководство» без слова org-structure в URL)
REVIEW_PAGE_HINTS = (
    "management",
    "governance",
    "structure",
    "struktura",
    "struktur",
    "руководств",
    "управлен",
    "подраздел",
    "enterprises",
    "company",
)


@dataclass
class ScrapeError:
    seed_url: str
    stage: str
    message: str
    detail: str = ""


@dataclass
class ImageCandidate:
    image_url: str
    page_url: str
    score: float
    alt: str = ""
    reason: str = ""


@dataclass
class CollectionItem:
    alias: str
    source_url: str
    page_url: str = ""
    org_chart_url: str = ""
    local_image: str = ""
    org_type: str = ""
    pain: str = ""
    status: str = "pending"
    notes: str = ""
    score: float = 0.0


@dataclass
class ScraperConfig:
    timeout: int = 25
    max_pages_per_site: int = 8
    max_depth: int = 2
    delay_seconds: float = 0.8
    min_image_bytes: int = 12_000
    min_image_width: int = 360
    min_image_height: int = 280
    user_agent: str = DEFAULT_USER_AGENT
    verify_ssl: bool = True
    allow_insecure_fallback: bool = False
    resolve_relative: bool = True
    same_domain_only: bool = True
    max_candidates: int = 12
    validate_downloaded_image: bool = True
    review_mode: bool = False


class _LinkImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self.images: list[tuple[str, str, str, str]] = []
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k.lower(): (v or "") for k, v in attrs if k}
        if tag == "a" and ad.get("href"):
            self.links.append((ad["href"], ad.get("title", "")))
        elif tag == "img":
            src = ad.get("src") or ad.get("data-src") or ad.get("data-lazy-src") or ""
            if src:
                w = ad.get("width", "")
                h = ad.get("height", "")
                dim = f"{w}x{h}" if w or h else ""
                self.images.append(
                    (src, ad.get("alt", ""), ad.get("title", ""), dim)
                )
        elif tag == "title":
            self._in_title = True

    def handle_data(self, data: str) -> None:
        if getattr(self, "_in_title", False):
            self._title_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    @property
    def title(self) -> str:
        return " ".join(self._title_parts).strip()


def load_seed_urls(path: Path) -> list[str]:
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    return lines


def normalize_url(base: str, href: str, *, resolve_relative: bool) -> str | None:
    href = href.strip()
    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
        return None
    if resolve_relative:
        return urljoin(base, href)
    if href.startswith(("http://", "https://")):
        return href
    return None


def same_domain(a: str, b: str) -> bool:
    pa, pb = urlparse(a), urlparse(b)
    return (pa.netloc or "").lower() == (pb.netloc or "").lower()


def _hint_score(text: str, hints: tuple[str, ...]) -> float:
    t = text.lower()
    return sum(2.0 for h in hints if h in t)


def _negative_penalty(blob: str) -> float:
    return sum(5.0 for n in IMAGE_NEGATIVE_HINTS if n in blob)


def is_org_structure_page(blob: str) -> bool:
    """Страница про организационную/иерархическую структуру, а не общий лендинг."""
    t = blob.lower()
    return _hint_score(t, ORG_STRUCTURE_PAGE_HINTS) >= MIN_PAGE_STRUCTURE_SCORE


def page_priority(
    url: str, anchor_text: str = "", title: str = "", *, review_mode: bool = False
) -> float:
    blob = f"{url} {anchor_text} {title}".lower()
    if is_org_structure_page(blob):
        return _hint_score(blob, ORG_STRUCTURE_PAGE_HINTS)
    if review_mode:
        weak = _hint_score(blob, REVIEW_PAGE_HINTS)
        if weak >= 2.0:
            return weak
    return 0.0


def image_priority(
    url: str,
    alt: str = "",
    title: str = "",
    dimensions: str = "",
    *,
    page_blob: str = "",
) -> float:
    blob = f"{url} {alt} {title} {dimensions} {page_blob}".lower()
    path = urlparse(url).path.lower()

    if _negative_penalty(blob) >= 5.0:
        return -100.0
    if path.endswith(".svg"):
        return -100.0

    score = _hint_score(blob, ORG_STRUCTURE_IMAGE_HINTS)
    if any(path.endswith(ext) for ext in IMAGE_EXTENSIONS):
        score += 1.0
    if is_org_structure_page(page_blob):
        score += 2.0

    m = re.search(r"(\d{3,4})\s*[xх×]\s*(\d{3,4})", dimensions.replace("px", ""))
    if m:
        w, h = int(m.group(1)), int(m.group(2))
        if w >= 500 and h >= 350:
            score += 2.5
        elif w >= 350 and h >= 250:
            score += 1.5
        elif w < 160 or h < 160:
            score -= 4.0

    return score


def min_score_for_page(page_blob: str, *, review_mode: bool = False) -> float:
    if review_mode:
        return 2.0 if is_org_structure_page(page_blob) else 7.0
    if is_org_structure_page(page_blob):
        return MIN_IMAGE_SCORE_ON_STRUCTURE_PAGE
    return MIN_IMAGE_SCORE_OTHER_PAGE


def validate_org_structure_image_file(
    path: Path,
    *,
    min_width: int = 360,
    min_height: int = 280,
) -> tuple[bool, str]:
    """
    Эвристика после скачивания: схема обычно крупная, не квадратное фото, много светлого фона.
    """
    try:
        from PIL import Image
    except ImportError:
        return True, "Pillow не установлен — проверка пропущена"

    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            w, h = im.size
    except Exception as e:
        return False, f"не читается как изображение: {e}"

    if w < min_width or h < min_height:
        return False, f"размер {w}×{h} мал для схемы"

    aspect = w / max(h, 1)
    if 0.82 < aspect < 1.22 and max(w, h) < 520:
        return False, "похоже на квадратное фото/портрет"

    step = max(1, (w * h) // 2500)
    pixels = list(im.getdata())[::step]
    if not pixels:
        return True, "ok"
    light = sum(1 for r, g, b in pixels if r > 235 and g > 235 and b > 235)
    light_ratio = light / len(pixels)
    if light_ratio < 0.12:
        return False, f"мало светлого фона ({light_ratio:.0%}), не типичная схема"

    return True, "похоже на схему (иерархия: проверка вручную)"


def fetch_html(
    url: str,
    session: requests.Session,
    cfg: ScraperConfig,
) -> tuple[str | None, ScrapeError | None]:
    try:
        resp = session.get(url, timeout=cfg.timeout, verify=cfg.verify_ssl)
        resp.raise_for_status()
        ctype = (resp.headers.get("content-type") or "").lower()
        if "html" not in ctype and "text" not in ctype:
            return None, ScrapeError(
                url, "fetch_html", "Не HTML-ответ", detail=ctype[:120]
            )
        resp.encoding = resp.encoding or "utf-8"
        return resp.text, None
    except requests.exceptions.SSLError as e:
        if cfg.allow_insecure_fallback:
            try:
                resp = session.get(url, timeout=cfg.timeout, verify=False)
                resp.raise_for_status()
                resp.encoding = resp.encoding or "utf-8"
                return resp.text, None
            except Exception as e2:
                return None, ScrapeError(url, "ssl", str(e2))
        return None, ScrapeError(url, "ssl", str(e))
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        return None, ScrapeError(url, "http", f"HTTP {code}", detail=str(e))
    except requests.exceptions.Timeout:
        return None, ScrapeError(url, "timeout", "Превышено время ожидания")
    except requests.exceptions.ConnectionError as e:
        return None, ScrapeError(url, "connection", str(e))
    except Exception as e:
        return None, ScrapeError(url, "fetch", str(e))


def parse_page(html: str) -> _LinkImageParser:
    parser = _LinkImageParser()
    try:
        parser.feed(html)
    except Exception:
        pass
    return parser


def collect_page_urls(
    seed: str,
    html: str,
    page_url: str,
    cfg: ScraperConfig,
) -> list[tuple[str, float]]:
    parsed = parse_page(html)
    out: list[tuple[str, float]] = []
    seen: set[str] = set()
    for href, title in parsed.links:
        abs_url = normalize_url(page_url, href, resolve_relative=cfg.resolve_relative)
        if not abs_url:
            continue
        if cfg.same_domain_only and not same_domain(seed, abs_url):
            continue
        key = urlunparse(urlparse(abs_url)._replace(fragment=""))
        if key in seen:
            continue
        seen.add(key)
        pr = page_priority(
            abs_url, title, parsed.title, review_mode=cfg.review_mode
        )
        if pr > 0:
            out.append((abs_url, pr))
        elif cfg.review_mode and _is_chart_file_url(abs_url):
            out.append((abs_url, 3.0))
    out.sort(key=lambda x: -x[1])
    return out


def _is_chart_file_url(url: str) -> bool:
    p = urlparse(url).path.lower()
    return any(p.endswith(ext) for ext in IMAGE_EXTENSIONS) and _hint_score(
        url.lower(), ORG_STRUCTURE_IMAGE_HINTS + REVIEW_PAGE_HINTS
    ) >= 2.0


def collect_linked_chart_images(page_url: str, html: str) -> list[ImageCandidate]:
    """Ссылки <a href=\"...png\"> на файлы схем."""
    parsed = parse_page(html)
    page_blob = f"{page_url} {parsed.title}"
    out: list[ImageCandidate] = []
    seen: set[str] = set()
    for href, title in parsed.links:
        abs_url = urljoin(page_url, href)
        if abs_url in seen or not _is_chart_file_url(abs_url):
            continue
        seen.add(abs_url)
        sc = image_priority(abs_url, title, "", page_blob=page_blob) + 2.0
        if sc > 0:
            out.append(
                ImageCandidate(
                    image_url=abs_url,
                    page_url=page_url,
                    score=sc,
                    alt=title,
                    reason="linked image file",
                )
            )
    return out


def collect_image_candidates(
    page_url: str,
    html: str,
    *,
    review_mode: bool = False,
) -> list[ImageCandidate]:
    parsed = parse_page(html)
    page_blob = f"{page_url} {parsed.title}"
    min_sc = min_score_for_page(page_blob, review_mode=review_mode)
    candidates: list[ImageCandidate] = []
    seen: set[str] = set()
    for src, alt, title, dim in parsed.images:
        abs_url = urljoin(page_url, src)
        if abs_url in seen:
            continue
        seen.add(abs_url)
        sc = image_priority(abs_url, alt, title, dim, page_blob=page_blob)
        if sc < min_sc:
            continue
        candidates.append(
            ImageCandidate(
                image_url=abs_url,
                page_url=page_url,
                score=sc,
                alt=alt,
                reason=(
                    f"page_structure={is_org_structure_page(page_blob)}; "
                    f"alt={alt!r}; min_sc={min_sc}"
                ),
            )
        )
    candidates.sort(key=lambda c: -c.score)
    return candidates


def download_image(
    candidate: ImageCandidate,
    dest: Path,
    session: requests.Session,
    cfg: ScraperConfig,
) -> tuple[Path | None, ScrapeError | None]:
    try:
        resp = session.get(
            candidate.image_url, timeout=cfg.timeout, verify=cfg.verify_ssl, stream=True
        )
        resp.raise_for_status()
        data = resp.content
        if len(data) < cfg.min_image_bytes:
            return None, ScrapeError(
                candidate.page_url,
                "image_too_small",
                f"{len(data)} байт < {cfg.min_image_bytes}",
                detail=candidate.image_url,
            )
        ctype = (resp.headers.get("content-type") or "").lower()
        suffix = dest.suffix or ".png"
        if "jpeg" in ctype or "jpg" in ctype:
            suffix = ".jpg"
        elif "webp" in ctype:
            suffix = ".webp"
        elif "gif" in ctype:
            suffix = ".gif"
        elif "svg" in ctype:
            suffix = ".svg"
        if dest.suffix != suffix:
            dest = dest.with_suffix(suffix)
        dest.write_bytes(data)
        return dest, None
    except Exception as e:
        return None, ScrapeError(
            candidate.page_url, "download", str(e), detail=candidate.image_url
        )


def try_download_best_candidate(
    candidates: list[ImageCandidate],
    dest: Path,
    session: requests.Session,
    cfg: ScraperConfig,
    *,
    limit: int = 8,
) -> tuple[Path | None, ImageCandidate | None, list[ScrapeError]]:
    """Скачивает кандидатов, пока файл не пройдёт проверку «похоже на оргсхему»."""
    errors: list[ScrapeError] = []
    for cand in candidates[:limit]:
        path, err = download_image(cand, dest, session, cfg)
        if err:
            errors.append(err)
            continue
        if not path:
            continue
        if cfg.validate_downloaded_image:
            ok, reason = validate_org_structure_image_file(
                path,
                min_width=cfg.min_image_width,
                min_height=cfg.min_image_height,
            )
            if not ok:
                errors.append(
                    ScrapeError(
                        cand.page_url,
                        "not_org_structure_image",
                        reason,
                        detail=cand.image_url,
                    )
                )
                path.unlink(missing_ok=True)
                continue
            cand.reason = f"{cand.reason}; validate={reason}"
        return path, cand, errors
    return None, None, errors


def make_session(cfg: ScraperConfig) -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": cfg.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        }
    )
    return s


def crawl_all_candidates(
    seed_url: str,
    *,
    cfg: ScraperConfig,
    session: requests.Session,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[list[ImageCandidate], list[ScrapeError]]:
    """Обход сайта: все кандидаты-картинки без выбора «лучшего»."""
    errors: list[ScrapeError] = []
    all_candidates: list[ImageCandidate] = []

    def log(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    pages_to_visit: list[tuple[str, int, float]] = [
        (
            seed_url,
            0,
            max(page_priority(seed_url, review_mode=cfg.review_mode), 1.0),
        )
    ]
    visited: set[str] = set()

    while pages_to_visit and len(visited) < cfg.max_pages_per_site:
        pages_to_visit.sort(key=lambda x: -x[2])
        page_url, depth, _ = pages_to_visit.pop(0)
        norm = urlunparse(urlparse(page_url)._replace(fragment=""))
        if norm in visited:
            continue
        visited.add(norm)

        log(f"GET {page_url}")
        html, err = fetch_html(page_url, session, cfg)
        if err:
            errors.append(err)
            continue
        assert html is not None

        for cand in collect_image_candidates(
            page_url, html, review_mode=cfg.review_mode
        ):
            all_candidates.append(cand)
        if cfg.review_mode:
            all_candidates.extend(collect_linked_chart_images(page_url, html))

        if depth < cfg.max_depth:
            for link, pr in collect_page_urls(seed_url, html, page_url, cfg):
                if pr > 0 and link not in visited:
                    pages_to_visit.append((link, depth + 1, pr))

        time.sleep(cfg.delay_seconds)

    dedup: dict[str, ImageCandidate] = {}
    for c in all_candidates:
        if c.image_url not in dedup or c.score > dedup[c.image_url].score:
            dedup[c.image_url] = c
    ranked = sorted(dedup.values(), key=lambda x: -x.score)
    return ranked, errors


def scrape_one_site(
    seed_url: str,
    *,
    cfg: ScraperConfig,
    session: requests.Session,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[CollectionItem | None, list[ScrapeError], list[ImageCandidate]]:
    errors: list[ScrapeError] = []
    all_candidates: list[ImageCandidate] = []

    def log(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    pages_to_visit: list[tuple[str, int, float]] = [
        (seed_url, 0, max(page_priority(seed_url, review_mode=cfg.review_mode), 0.5))
    ]
    visited: set[str] = set()
    best: ImageCandidate | None = None

    while pages_to_visit and len(visited) < cfg.max_pages_per_site:
        pages_to_visit.sort(key=lambda x: -x[2])
        page_url, depth, _ = pages_to_visit.pop(0)
        norm = urlunparse(urlparse(page_url)._replace(fragment=""))
        if norm in visited:
            continue
        visited.add(norm)

        log(f"GET {page_url}")
        html, err = fetch_html(page_url, session, cfg)
        if err:
            errors.append(err)
            if page_url == seed_url:
                return None, errors, all_candidates
            continue
        assert html is not None

        for cand in collect_image_candidates(
            page_url, html, review_mode=cfg.review_mode
        ):
            all_candidates.append(cand)
            if best is None or cand.score > best.score:
                best = cand

        if depth < cfg.max_depth:
            for link, pr in collect_page_urls(seed_url, html, page_url, cfg):
                if pr > 0 and link not in visited:
                    pages_to_visit.append((link, depth + 1, pr))

        time.sleep(cfg.delay_seconds)

    if not best or best.score < MIN_IMAGE_SCORE_ON_STRUCTURE_PAGE:
        errors.append(
            ScrapeError(
                seed_url,
                "no_org_structure",
                "Не найдено изображений иерархической оргструктуры "
                "(руководитель + подчинённые/ресурсники). См. ORG_STRUCTURE_CRITERION.md",
            )
        )
        return None, errors, all_candidates

    item = CollectionItem(
        alias="",
        source_url=seed_url,
        page_url=best.page_url,
        org_chart_url=best.image_url,
        status="candidate",
        notes=best.reason,
        score=best.score,
    )
    return item, errors, all_candidates


def load_collection(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "schema_version": 1,
        "description": (
            "Оргструктуры с сайтов: иерархия, первый руководитель, ресурсники "
            "(url_collect/ORG_STRUCTURE_CRITERION.md). org_type/pain — перед batch."
        ),
        "items": [],
    }


def save_collection(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def save_errors(path: Path, errors: list[ScrapeError], run_meta: dict) -> None:
    payload = {
        "run": run_meta,
        "errors": [asdict(e) for e in errors],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def next_alias(items: list[dict], prefix: str = "web") -> str:
    nums = []
    for it in items:
        a = it.get("alias", "")
        m = re.match(rf"{prefix}_(\d+)$", a)
        if m:
            nums.append(int(m.group(1)))
    n = max(nums, default=0) + 1
    return f"{prefix}_{n:03d}"

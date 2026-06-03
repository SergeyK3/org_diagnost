from __future__ import annotations

import base64
import html
import re
from datetime import date
from pathlib import Path

# Перед эталонным рисунком (PDF, стр. 3)
ORG_SCHEME_INTRO = (
    "Организующая схема (оргсхема) отличается от оргструктуры: в ней видно "
    "направление создания продукта или услуги, а не только «кто кому подчиняется». "
    "Ниже — правильная упрощённая оргсхема (эталон для сравнения)."
)

# После эталонного рисунка (reference_org_scheme.md, 5 пунктов)
REFERENCE_NARRATIVE_ITEMS: tuple[str, ...] = (
    "Управление — возникает идея производства или услуги; руководитель задаёт направление. "
    "Найм на старте часто встроен в самого руководителя; отдельный блок «Кадры» появляется при росте.",
    "Маркетинг — нужно продать идею ценности продукта или услуги. "
    "Без продаж до производства запускать производство бессмысленно; здесь частые провалы у МСП.",
    "Бухгалтерия (учёт / финансы) — когда услуга «продаётся», нужен учёт денег "
    "(один человек, аутсорс или сам руководитель).",
    "Производство (оказание услуг) — руководителю часто близко; на схемах обычно проработано; "
    "на ранних этапах качество часто держит сам производственник.",
    "Контроль качества и связь с обществом (СМИ, филиалы) — зрелые функции; "
    "на упрощённых «иерархических» схемах часто отсутствуют.",
)

RECOMMENDATION_HTML = (
    'для уточнения диагностики и прояснения возникших вопросов рекомендуем '
    'обратиться к автору проекта (Ким Сергей Васильевич, Tg: '
    '<a href="https://t.me/kimsergeiv">@kimsergeiv</a>)'
)

PLACEHOLDER_NOT_DONE = "Анализ не выполнен."


def slugify_org_name(name: str) -> str:
    """Краткое имя файла: латиница, цифры, подчёркивание."""
    tr = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    s = name.strip().lower()
    out = []
    for ch in s:
        if ch in tr:
            out.append(tr[ch])
        elif ch.isalnum():
            out.append(ch)
        elif ch in " -_":
            out.append("_")
    slug = re.sub(r"_+", "_", "".join(out)).strip("_")
    return slug[:40] or "org"


def _img_to_base64(path: Path) -> str:
    data = path.read_bytes()
    mime = "image/png"
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        mime = "image/jpeg"
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _section_img(title: str, path: Path | None) -> str:
    if path is None or not path.exists():
        return f"<h3>{html.escape(title)}</h3><p><em>Изображение недоступно</em></p>"
    src = _img_to_base64(path)
    return (
        f"<h3>{html.escape(title)}</h3>"
        f'<p><img src="{src}" alt="{html.escape(title)}" style="max-width:100%;height:auto;" /></p>'
    )


def _recommendation_html(contact: str) -> str:
    """Текст рекомендации в конце отчёта; по умолчанию — автор проекта."""
    c = contact.strip()
    if not c or c.startswith("@") or "kimsergeiv" in c.lower():
        return RECOMMENDATION_HTML
    if c.startswith("<"):
        return (
            "для уточнения диагностики и прояснения возникших вопросов рекомендуем "
            f"{c}"
        )
    return (
        "для уточнения диагностики и прояснения возникших вопросов рекомендуем "
        f"{html.escape(c)}"
    )


def _reference_org_scheme_block(visual_paths: dict[str, Path]) -> str:
    intro = f"<p class='intro'>{html.escape(ORG_SCHEME_INTRO)}</p>"
    img = _section_img("Эталонная упрощённая оргсхема", visual_paths.get("block_reference"))
    items = "".join(
        f"<li>{html.escape(item)}</li>" for item in REFERENCE_NARRATIVE_ITEMS
    )
    narrative = (
        "<p class='narrative-title'><strong>Зачем такой порядок блоков:</strong></p>"
        f"<ol class='narrative'>{items}</ol>"
    )
    return intro + img + narrative


def has_analysis_text(pass1_text: str, pass2_text: str) -> bool:
    return bool(pass1_text.strip() or pass2_text.strip())


def generate_html_report(
    dest: Path,
    *,
    org_name: str,
    org_type: str,
    analysis_date: date | None = None,
    visual_paths: dict[str, Path],
    pass1_text: str,
    pass2_text: str,
    contact: str = "",
) -> Path:
    if not has_analysis_text(pass1_text, pass2_text):
        raise ValueError(
            "Нет текстов выводов pass1/pass2 для HTML — "
            "анализ LLM не выполнен или вернул пустой ответ."
        )

    analysis_date = analysis_date or date.today()
    recommendation = _recommendation_html(contact)
    reference_block = _reference_org_scheme_block(visual_paths)

    pass1_section = (
        f"<h3>Выводы (блочная структура)</h3>"
        f"<div class='conclusion'>{_text_to_html(pass1_text)}</div>"
    )

    footer = (
        f"<p class='recommendation'><strong>Рекомендация:</strong> {recommendation}.</p>"
    )

    body = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <title>Анализ оргструктуры — {html.escape(org_name)}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; color: #222; }}
    h1 {{ border-bottom: 2px solid #1565c0; padding-bottom: 0.5rem; }}
    h2 {{ margin-top: 2rem; color: #1565c0; }}
    h3 {{ margin-top: 1.25rem; font-size: 1.1rem; }}
    .meta {{ color: #555; }}
    .conclusion {{ white-space: pre-wrap; line-height: 1.5; background: #f5f5f5; padding: 1rem; border-radius: 6px; }}
    .intro, .narrative-title {{ font-size: 0.95rem; color: #444; line-height: 1.5; }}
    .narrative {{ font-size: 0.92rem; color: #555; line-height: 1.45; margin: 0.5rem 0 1rem 1.25rem; }}
    .recommendation {{ margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #ddd; }}
  </style>
</head>
<body>
  <h1>Анализ оргструктуры</h1>
  <p class="meta"><strong>Организация:</strong> {html.escape(org_name)}<br />
  <strong>Профиль:</strong> {html.escape(org_type)}<br />
  <strong>Дата анализа:</strong> {analysis_date.isoformat()}</p>

  <h2>Анализ блочной структуры</h2>
  {_section_img("Исходный граф", visual_paths.get("block_source"))}
  {_section_img("Проанализированная упрощённая структура", visual_paths.get("block_analyzed"))}
  {reference_block}
  {pass1_section}

  <h2>Анализ административных должностей (руководители)</h2>
  {_section_img("Структура с должностями и руководителями", visual_paths.get("admin_roles"))}
  <h3>Выводы (руководители)</h3>
  <div class="conclusion">{_text_to_html(pass2_text)}</div>

  {footer}
</body>
</html>
"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(body, encoding="utf-8")
    return dest.resolve()


def _text_to_html(text: str) -> str:
    if not text or not text.strip():
        return f"<em>{PLACEHOLDER_NOT_DONE}</em>"
    return html.escape(text.strip()).replace("\n", "<br />\n")


def default_html_path(
    html_out_dir: Path,
    org_name: str,
    analysis_date: date | None = None,
) -> Path:
    analysis_date = analysis_date or date.today()
    slug = slugify_org_name(org_name)
    return html_out_dir / f"{slug}_{analysis_date.isoformat()}.html"

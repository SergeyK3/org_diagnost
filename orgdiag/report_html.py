from __future__ import annotations

import base64
import html
import re
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orgdiag.owner_questions import OwnerQAPair

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


def _pain_field_block(pain: str) -> str:
    """Блок с управленческой болью сразу после исходной оргструктуры."""
    text = pain.strip()
    if not text:
        return (
            '<div class="pain-field pain-field--empty">'
            "<label>Управленческая боль организации</label>"
            "<p><em>Не указана</em></p></div>"
        )
    return (
        '<div class="pain-field">'
        "<label>Управленческая боль организации</label>"
        f"<p>{html.escape(text)}</p></div>"
    )


def _section_img(title: str, path: Path | None) -> str:
    if path is None or not path.exists():
        return (
            f'<div class="figure"><h3>{html.escape(title)}</h3>'
            f"<p><em>Изображение недоступно</em></p></div>"
        )
    src = _img_to_base64(path)
    return (
        f'<div class="figure"><h3>{html.escape(title)}</h3>'
        f'<p><img src="{src}" alt="{html.escape(title)}" /></p></div>'
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


def _owner_qa_section(pairs: list[OwnerQAPair] | None) -> str:
    if not pairs:
        return ""
    blocks: list[str] = [
        "<h2>Уточняющие вопросы собственника</h2>",
        "<p class='intro'>Три типичных вопроса после заключения и ответы консультанта (LLM по контексту анализа).</p>",
    ]
    for i, pair in enumerate(pairs, 1):
        gate = "" if pair.allowed else " <em>(вне темы диагностики)</em>"
        blocks.append(
            f'<div class="owner-qa">'
            f"<h3>Вопрос {i}{gate}</h3>"
            f"<p class='owner-q'><strong>В:</strong> {html.escape(pair.question)}</p>"
            f"<div class='owner-a'><strong>О:</strong> {_text_to_html(pair.answer)}</div>"
            f"</div>"
        )
    return "\n  ".join(blocks)


def has_analysis_text(pass1_text: str, pass2_text: str) -> bool:
    return bool(pass1_text.strip() or pass2_text.strip())


def generate_html_report(
    dest: Path,
    *,
    org_name: str,
    org_type: str,
    pain: str = "",
    analysis_date: date | None = None,
    visual_paths: dict[str, Path],
    pass1_text: str,
    pass2_text: str,
    contact: str = "",
    owner_qa: list[OwnerQAPair] | None = None,
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

    owner_qa_block = _owner_qa_section(owner_qa)
    footer = (
        f"<p class='recommendation'><strong>Рекомендация:</strong> {recommendation}.</p>"
    )

    body = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <title>Анализ оргструктуры — {html.escape(org_name)}</title>
  <style>
    body {{ font-family: system-ui, "Segoe UI", sans-serif; font-size: 14px; max-width: 960px; margin: 1rem auto; padding: 0 0.75rem; color: #222; line-height: 1.4; }}
    h1 {{ font-size: 1.35rem; border-bottom: 2px solid #1565c0; padding-bottom: 0.35rem; margin: 0 0 0.75rem; }}
    h2 {{ margin: 1.25rem 0 0.5rem; font-size: 1.1rem; color: #1565c0; }}
    h3 {{ margin: 0.65rem 0 0.25rem; font-size: 1rem; font-weight: 600; }}
    .meta {{ font-size: 0.92rem; color: #555; margin-bottom: 0.75rem; }}
    .figure {{ margin: 0.35rem 0 0.6rem; }}
    .figure img {{ max-width: 100%; height: auto; display: block; }}
    .conclusion {{ background: #f5f5f5; padding: 0.5rem 0.65rem; border-radius: 4px; font-size: 0.95rem; line-height: 1.38; }}
    .conclusion p {{ margin: 0.25rem 0 0.4rem; }}
    .conclusion p:first-child {{ margin-top: 0; }}
    .conclusion p:last-child {{ margin-bottom: 0; }}
    .conclusion ul, .conclusion ol {{ margin: 0.2rem 0 0.35rem 1.1rem; padding: 0; }}
    .conclusion li {{ margin: 0.1rem 0; }}
    .intro, .narrative-title {{ font-size: 0.9rem; color: #444; line-height: 1.38; margin: 0.25rem 0; }}
    .narrative {{ font-size: 0.88rem; color: #555; line-height: 1.35; margin: 0.25rem 0 0.5rem 1.1rem; }}
    .recommendation {{ margin-top: 1rem; padding-top: 0.6rem; border-top: 1px solid #ddd; font-size: 0.92rem; }}
    .pain-field {{ margin: 0.5rem 0 0.85rem; padding: 0.55rem 0.7rem; background: #fff8e1; border: 1px solid #ffe082; border-radius: 4px; }}
    .pain-field label {{ display: block; font-size: 0.82rem; font-weight: 600; color: #6d4c00; margin-bottom: 0.25rem; text-transform: uppercase; letter-spacing: 0.02em; }}
    .pain-field p {{ margin: 0; font-size: 0.95rem; line-height: 1.4; color: #333; }}
    .pain-field--empty {{ background: #f5f5f5; border-color: #e0e0e0; }}
    .pain-field--empty label {{ color: #757575; }}
    .owner-qa {{ margin: 0.75rem 0 1rem; padding: 0.6rem 0.75rem; border-left: 4px solid #1976d2; background: #f8fbff; border-radius: 0 4px 4px 0; }}
    .owner-qa h3 {{ margin: 0 0 0.35rem; font-size: 0.95rem; color: #0d47a1; }}
    .owner-q {{ margin: 0 0 0.45rem; font-size: 0.94rem; }}
    .owner-a {{ font-size: 0.93rem; color: #333; }}
    .owner-a p {{ margin: 0.2rem 0; }}
    @media print {{
      body {{ font-size: 10pt; margin: 0.6cm; padding: 0; max-width: none; }}
      h1 {{ font-size: 13pt; }}
      h2 {{ font-size: 11pt; margin-top: 0.75rem; page-break-after: avoid; }}
      h3 {{ font-size: 10pt; margin-top: 0.4rem; }}
      .meta, .intro, .narrative, .recommendation {{ font-size: 9pt; }}
      .conclusion {{ font-size: 9pt; line-height: 1.32; padding: 0.35rem 0.5rem; background: #fafafa; }}
      .figure img {{ max-height: 200px; max-width: 100%; object-fit: contain; }}
      .narrative {{ margin-left: 0.9rem; }}
      h2, h3, .figure {{ page-break-inside: avoid; }}
    }}
  </style>
</head>
<body>
  <h1>Анализ оргструктуры</h1>
  <p class="meta"><strong>Организация:</strong> {html.escape(org_name)}<br />
  <strong>Профиль:</strong> {html.escape(org_type)}<br />
  <strong>Дата анализа:</strong> {analysis_date.isoformat()}</p>

  <h2>Анализ блочной структуры</h2>
  {_section_img("Исходный граф", visual_paths.get("block_source"))}
  {_pain_field_block(pain)}
  {_section_img("Проанализированная упрощённая структура", visual_paths.get("block_analyzed"))}
  {reference_block}
  {pass1_section}

  <h2>Анализ административных должностей (руководители)</h2>
  {_section_img("Структура с должностями и руководителями", visual_paths.get("admin_roles"))}
  <h3>Выводы (руководители)</h3>
  <div class="conclusion">{_text_to_html(pass2_text)}</div>

  {owner_qa_block}

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
    raw = text.strip().replace("\r\n", "\n")
    blocks = re.split(r"\n\s*\n+", raw)
    parts: list[str] = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        if _block_looks_like_list(lines):
            parts.append(_lines_to_list_html(lines))
        else:
            inner = html.escape(block).replace("\n", " ")
            parts.append(f"<p>{inner}</p>")
    return "\n".join(parts) if parts else f"<em>{PLACEHOLDER_NOT_DONE}</em>"


def _block_looks_like_list(lines: list[str]) -> bool:
    if len(lines) < 2:
        return False
    list_like = sum(
        1
        for ln in lines
        if re.match(r"^(\d+[\.\)]\s+|[-•*]\s+)", ln.strip())
    )
    return list_like >= max(2, len(lines) // 2)


def _lines_to_list_html(lines: list[str]) -> str:
    items: list[str] = []
    ordered = True
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        m_num = re.match(r"^\d+[\.\)]\s+(.*)$", ln)
        m_bullet = re.match(r"^[-•*]\s+(.*)$", ln)
        if m_bullet:
            ordered = False
            items.append(f"<li>{html.escape(m_bullet.group(1))}</li>")
        elif m_num:
            items.append(f"<li>{html.escape(m_num.group(1))}</li>")
        else:
            items.append(f"<li>{html.escape(ln)}</li>")
    tag = "ol" if ordered else "ul"
    return f"<{tag}>{''.join(items)}</{tag}>"


def default_html_path(
    html_out_dir: Path,
    org_name: str,
    analysis_date: date | None = None,
) -> Path:
    analysis_date = analysis_date or date.today()
    slug = slugify_org_name(org_name)
    return html_out_dir / f"{slug}_{analysis_date.isoformat()}.html"

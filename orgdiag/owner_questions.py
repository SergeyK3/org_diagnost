from __future__ import annotations

import html
import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from openai import OpenAI

from orgdiag.config import default_contact, require_api_key
from orgdiag.followup_chat import (
    FollowupTurn,
    answer_followup_question,
    build_followup_context,
)
from orgdiag.paths import HTML_OUT_DIR, PROMPTS_DIR
from orgdiag.pipeline import DiagnosisResult
from orgdiag.prompts import load_prompt
from orgdiag.report_html import slugify_org_name

SIM_PROMPT = "owner_questions_sim_prompt.txt"
REPORT_QA_COUNT = 3
OWNER_QA_CACHE_NAME = "owner_qa_report.json"


@dataclass
class OwnerQAPair:
    question: str
    answer: str
    allowed: bool = True


def owner_qa_cache_path(cache_stem: str, cache_root: Path) -> Path:
    return cache_root / cache_stem / OWNER_QA_CACHE_NAME


def load_owner_qa_cache(path: Path) -> list[OwnerQAPair]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        OwnerQAPair(
            question=p["question"],
            answer=p["answer"],
            allowed=p.get("allowed", True),
        )
        for p in data.get("pairs", [])
    ]


def save_owner_qa_cache(path: Path, pairs: list[OwnerQAPair]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"pairs": [asdict(p) for p in pairs]},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def generate_owner_qa_for_report(
    result: DiagnosisResult,
    *,
    count: int = REPORT_QA_COUNT,
    contact: str = "",
    client: OpenAI | None = None,
) -> list[OwnerQAPair]:
    """Три (по умолчанию) вопроса собственника и ответы LLM для вставки в HTML-отчёт."""
    require_api_key()
    client = client or OpenAI()
    contact = contact or default_contact()
    questions = generate_owner_questions(result, count=count, client=client)
    history: list[FollowupTurn] = []
    pairs: list[OwnerQAPair] = []
    for question in questions:
        reply = answer_followup_question(
            question,
            result=result,
            history=[t for t in history if t.allowed],
            contact=contact,
            client=client,
        )
        history.append(
            FollowupTurn(question=question, answer=reply.text, allowed=reply.allowed)
        )
        pairs.append(
            OwnerQAPair(question=question, answer=reply.text, allowed=reply.allowed)
        )
    return pairs


def resolve_owner_qa_for_report(
    result: DiagnosisResult,
    cache_stem: str,
    cache_root: Path,
    *,
    contact: str = "",
    refresh: bool = False,
    client: OpenAI | None = None,
) -> list[OwnerQAPair]:
    path = owner_qa_cache_path(cache_stem, cache_root)
    if not refresh:
        cached = load_owner_qa_cache(path)
        if len(cached) >= REPORT_QA_COUNT:
            return cached[:REPORT_QA_COUNT]
    pairs = generate_owner_qa_for_report(result, contact=contact, client=client)
    save_owner_qa_cache(path, pairs)
    return pairs


def generate_owner_questions(
    result: DiagnosisResult,
    *,
    count: int = 8,
    client: OpenAI | None = None,
) -> list[str]:
    require_api_key()
    client = client or OpenAI()
    template = load_prompt(SIM_PROMPT)
    prompt = template.replace("{count}", str(count))
    context = build_followup_context(result)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "Верни только список вопросов, по одному на строку.",
            },
            {
                "role": "user",
                "content": f"{prompt}\n\n---\nКонтекст:\n{context[:12000]}",
            },
        ],
        temperature=0.4,
        max_tokens=900,
    )
    raw = response.choices[0].message.content.strip()
    lines: list[str] = []
    for line in raw.splitlines():
        line = re.sub(r"^\s*\d+[\.\)]\s*", "", line.strip())
        if len(line) >= 12:
            lines.append(line)
    return lines[:count]


def write_questions_text(
    path: Path,
    *,
    alias: str,
    image_file: str,
    org_type: str,
    pain: str,
    questions: list[str],
    pass1_excerpt: str = "",
    pass2_excerpt: str = "",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Вероятные вопросы собственника — {alias}",
        f"Исходный файл: {image_file}",
        f"Тип: {org_type}",
        f"Боль: {pain}",
        "",
    ]
    if pass1_excerpt.strip():
        lines.extend(["## Контекст (фрагмент pass1)", "", pass1_excerpt.strip()[:800], ""])
    if pass2_excerpt.strip():
        lines.extend(["## Контекст (фрагмент pass2)", "", pass2_excerpt.strip()[:800], ""])
    lines.extend(["## Вопросы", ""])
    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. {q}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_questions_html(
    path: Path,
    *,
    alias: str,
    image_file: str,
    org_type: str,
    pain: str,
    questions: list[str],
    analysis_date: date | None = None,
) -> Path:
    analysis_date = analysis_date or date.today()
    path.parent.mkdir(parents=True, exist_ok=True)
    items = "".join(
        f"<li>{html.escape(q)}</li>" for q in questions
    )
    body = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <title>Вопросы собственника — {html.escape(alias)}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; font-size: 14px; max-width: 720px; margin: 1rem auto; padding: 0 1rem; color: #222; line-height: 1.4; }}
    h1 {{ font-size: 1.2rem; color: #1565c0; border-bottom: 1px solid #ccc; padding-bottom: 0.35rem; }}
    .meta {{ color: #555; font-size: 0.92rem; margin-bottom: 1rem; }}
    ol {{ margin: 0.5rem 0; padding-left: 1.25rem; }}
    li {{ margin: 0.35rem 0; }}
    @media print {{
      body {{ font-size: 10pt; margin: 0.6cm; }}
      h1 {{ font-size: 12pt; }}
      li {{ margin: 0.2rem 0; }}
    }}
  </style>
</head>
<body>
  <h1>Вероятные уточняющие вопросы</h1>
  <p class="meta">
    <strong>Условное название:</strong> {html.escape(alias)}<br />
    <strong>Файл схемы:</strong> {html.escape(image_file)}<br />
    <strong>Профиль:</strong> {html.escape(org_type)}<br />
    <strong>Боль:</strong> {html.escape(pain)}<br />
    <strong>Дата:</strong> {analysis_date.isoformat()}
  </p>
  <p>Коллекция типичных вопросов после заключения по оргдиагностике (моделирование, не ответы клиента).</p>
  <ol>{items}</ol>
</body>
</html>
"""
    path.write_text(body, encoding="utf-8")
    return path


def default_questions_html_path(alias: str, base_dir: Path | None = None) -> Path:
    base = base_dir or HTML_OUT_DIR
    slug = slugify_org_name(alias)
    return base / f"questions_{slug}_{date.today().isoformat()}.html"


def default_questions_text_path(cache_stem: str, cache_root: Path) -> Path:
    return cache_root / cache_stem / "likely_owner_questions.txt"


def build_master_questions_markdown(rows: list[dict], *, built_date: date | None = None) -> str:
    """Сводный документ: общий раздел + раздел на каждую организацию."""
    built_date = built_date or date.today()
    lines = [
        "# Сводная коллекция вопросов собственника",
        "",
        f"**Дата сборки:** {built_date.isoformat()}",
        "",
        "Источники: `html_out/questions_<alias>_<дата>.html`, "
        "`cache/<stem>/likely_owner_questions.txt`, отчёты анализа.",
        "",
        "---",
        "",
        "## Общий раздел",
        "",
        "Ниже — все кейсы галереи `images/`. Вопросы сгенерированы LLM по результатам "
        "оргдиагностики (pass1/pass2); это моделирование типичных уточнений после заключения, "
        "не ответы реального клиента.",
        "",
        "| Условное имя | Тип | Боль (кратко) | HTML вопросов |",
        "|---|---|---|---|",
    ]
    for row in rows:
        pain_short = row["pain"]
        if len(pain_short) > 60:
            pain_short = pain_short[:57] + "…"
        pain_short = pain_short.replace("|", "\\|")
        q_html = row.get("html") or "—"
        if isinstance(q_html, Path):
            q_html = f"`{q_html}`"
        else:
            q_html = f"`{q_html}`"
        lines.append(
            f"| {row['alias']} | {row['org_type']} | {pain_short} | {q_html} |"
        )
    lines.extend(["", "---", ""])

    for row in rows:
        lines.extend(
            [
                f"## {row['alias']}",
                "",
                f"- **Файл схемы:** `{row['image']}`",
                f"- **Тип предприятия:** {row['org_type']}",
                f"- **Управленческая боль:** {row['pain']}",
            ]
        )
        if row.get("report_html"):
            lines.append(f"- **Отчёт анализа:** `{row['report_html']}`")
        if row.get("html"):
            lines.append(f"- **Вопросы (HTML):** `{row['html']}`")
        if row.get("txt"):
            lines.append(f"- **Вопросы (текст):** `{row['txt']}`")
        lines.extend(["", "### Вопросы", ""])
        for i, q in enumerate(row.get("questions") or [], 1):
            lines.append(f"{i}. {q}")
        lines.extend(["", "---", ""])

    return "\n".join(lines)


def write_master_questions_html(
    path: Path,
    rows: list[dict],
    *,
    built_date: date | None = None,
) -> Path:
    built_date = built_date or date.today()
    path.parent.mkdir(parents=True, exist_ok=True)

    toc = "".join(
        f'<li><a href="#{html.escape(row["alias"])}">{html.escape(row["alias"])}</a></li>'
        for row in rows
    )
    sections: list[str] = []
    for row in rows:
        items = "".join(
            f"<li>{html.escape(q)}</li>" for q in row.get("questions") or []
        )
        sections.append(
            f"""<section id="{html.escape(row['alias'])}">
  <h2>{html.escape(row['alias'])}</h2>
  <p class="meta">
    <strong>Схема:</strong> {html.escape(row['image'])}<br />
    <strong>Профиль:</strong> {html.escape(row['org_type'])}<br />
    <strong>Боль:</strong> {html.escape(row['pain'])}
  </p>
  <ol>{items}</ol>
</section>"""
        )

    body = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <title>Сводная коллекция вопросов собственника</title>
  <style>
    body {{ font-family: system-ui, sans-serif; font-size: 14px; max-width: 820px; margin: 1rem auto; padding: 0 1rem; color: #222; line-height: 1.45; }}
    h1 {{ font-size: 1.35rem; color: #1565c0; border-bottom: 2px solid #1565c0; padding-bottom: 0.35rem; }}
    h2 {{ font-size: 1.1rem; margin-top: 1.5rem; color: #0d47a1; }}
    .intro {{ color: #444; margin: 1rem 0; }}
    .toc {{ background: #f5f5f5; padding: 0.75rem 1rem; border-radius: 6px; }}
    .toc ul {{ margin: 0.35rem 0 0; padding-left: 1.2rem; }}
    section {{ margin-bottom: 1.5rem; padding-bottom: 1rem; border-bottom: 1px solid #e0e0e0; }}
    .meta {{ font-size: 0.92rem; color: #555; }}
    ol {{ padding-left: 1.25rem; }}
    li {{ margin: 0.4rem 0; }}
  </style>
</head>
<body>
  <h1>Сводная коллекция вопросов собственника</h1>
  <p class="intro"><strong>Дата сборки:</strong> {built_date.isoformat()}. 
  Общий перечень кейсов и по разделу на каждую организацию — типичные уточняющие вопросы после заключения.</p>
  <nav class="toc"><strong>Оглавление</strong><ul>{toc}</ul></nav>
  <section id="general">
    <h2>Общий раздел</h2>
    <p>Всего организаций в коллекции: <strong>{len(rows)}</strong>. 
    Отдельные файлы: <code>html_out/questions_&lt;alias&gt;_&lt;дата&gt;.html</code>.</p>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%;font-size:0.9rem;">
      <tr><th>Имя</th><th>Тип</th><th>Боль</th></tr>
      {
          "".join(
              f"<tr><td>{html.escape(r['alias'])}</td>"
              f"<td>{html.escape(r['org_type'])}</td>"
              f"<td>{html.escape(r['pain'][:80])}</td></tr>"
              for r in rows
          )
      }
    </table>
  </section>
  {''.join(sections)}
</body>
</html>
"""
    path.write_text(body, encoding="utf-8")
    return path

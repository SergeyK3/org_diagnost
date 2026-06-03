from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

from orgdiag.config import require_api_key

# Полный эталон из docs/Упрощ оргсхема.pdf (рисунок → reference_org_scheme.png)
REFERENCE_BLOCK_FLOW = (
    "Управление → Кадры → Маркетинг → Бухгалтерия → "
    "Производство (оказание услуг) → Контроль качества → "
    "Связь с обществом (СМИ и филиалы)"
)

# Устаревшая модель «боковых» блоков; эталон — одна линия из PDF
REFERENCE_SIDE_BLOCKS: tuple[str, ...] = ()

# Обратная совместимость
RIGHT_SIMPLE_STRUCTURE = REFERENCE_BLOCK_FLOW

BLOCK_CATEGORIES = (
    "Управление",
    "Кадры",
    "Маркетинг",
    "Бухгалтерия",
    "Учёт / Финансы",
    "Производство",
    "Контроль качества",
    "Связь с обществом",
)


def reference_flow_text() -> str:
    return REFERENCE_BLOCK_FLOW


def reference_full_text() -> str:
    return REFERENCE_BLOCK_FLOW


def fmt_role(role_label: str, count: int, person_name: str | None = None) -> str:
    base = (
        f"{role_label} ({count})"
        if isinstance(count, int) and count > 1
        else role_label
    )
    if person_name and str(person_name).strip():
        return f"{base} — {person_name.strip()}"
    return base


def render_sideways_tree(org: dict) -> str:
    owner = (org.get("owner_label") or "").strip()
    director = (org.get("director_label") or "").strip()
    depts = org.get("departments") or []

    head_left = " → ".join([x for x in [owner, director] if x]).strip()
    if not head_left:
        head_left = director or owner or "Оргструктура"

    if not isinstance(depts, list) or not depts:
        return head_left + "\n"

    base_indent = " " * (len(head_left) + 3)
    lines: list[str] = []

    for idx, d in enumerate(depts):
        dept = (d.get("dept_label") or "").strip() or f"Управление {idx + 1}"
        dept_person = (d.get("person_name") or "").strip() or None
        roles = d.get("roles") or []

        dept_display = dept
        if dept_person:
            dept_display = f"{dept} — {dept_person}"

        if idx == 0:
            lines.append(f"{head_left} → {dept_display}")
        else:
            lines.append("")
            lines.append(f"{base_indent}→ {dept_display}")

        role_lines = []
        for r in roles:
            rl = (r.get("role_label") or "").strip()
            if not rl:
                continue
            cnt = r.get("count", 1)
            try:
                cnt = int(cnt)
            except (TypeError, ValueError):
                cnt = 1
            pn = (r.get("person_name") or "").strip() or None
            role_lines.append(fmt_role(rl, cnt, pn))

        for i, rl in enumerate(role_lines):
            prefix = "├─" if i < len(role_lines) - 1 else "└─"
            lines.append(f"{base_indent}   {prefix} {rl}")

    return "\n".join(lines).rstrip() + "\n"


def simplify_structure_llm(
    frag_text: str,
    *,
    org_type: str | None = None,
    model: str = "gpt-4o",
    client: OpenAI | None = None,
) -> str:
    require_api_key()
    client = client or OpenAI()
    categories = (
        "'Управление', 'Маркетинг', 'Бухгалтерия' (или 'Учёт / Финансы'), 'Производство'. "
        "'Кадры' — только если на схеме явно выделен HR/подбор. "
        "Отдел продаж и лидогенерация относятся к 'Маркетинг'. "
        "Контроль качества и связь с обществом — только если явно есть на схеме."
    )
    prompt = (
        "Ты — эксперт по организационным структурам любых предприятий. "
        "Проанализируй фрагмент иерархии (см. ниже) и интерпретируй все должности и отделы как укрупнённые блоки, "
        f"которые соответствуют только этим ключевым категориям: {categories} "
        "Если блок по смыслу не относится ни к одной из этих категорий — не выводи его. "
        "Если несколько блоков относятся к одной категории, объедини их в один. "
        "Если профиль предприятия — медицинская клиника, завод, IT-компания, торговая фирма и т.д., то все специфические подразделения "
        "(врачи, лаборатории, производственные участки, разработчики и т.п.) относить к 'Производство'. "
        "Категорию 'Управление' упоминай только один раз и только в самом начале списка. "
        "Выводи только список найденных укрупнённых блоков в порядке их появления, через стрелку '→', без лишнего текста. "
        "Не повторяй одну и ту же категорию подряд.\n"
        + (f"Профиль предприятия: {org_type}.\n" if org_type else "")
        + "Фрагмент иерархии:\n"
        + f"{frag_text}"
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Ты — эксперт по оргструктурам."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=200,
    )
    return response.choices[0].message.content.strip()


def _normalize_flow(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("→", "->").strip().lower())


def compare_simple_structures(
    real: str, ideal: str | None = None
) -> str:
    ideal = ideal or REFERENCE_BLOCK_FLOW
    lines = [
        "Реальная структура (упрощённый поток):",
        str(real),
        "\nЭталонная упрощённая оргсхема (полный поток из PDF):",
        str(ideal),
        "\nРезультат сравнения:",
    ]
    if _normalize_flow(real) == _normalize_flow(ideal):
        lines.append("Структуры совпадают по ключевым блокам и порядку основного потока.")
    else:
        lines.append(
            "Отличия обнаружены. Проверьте порядок и наличие всех ключевых блоков "
            "в соответствии с потоком информации."
        )
    lines.append(
        "Эталонная структура показывает направление создания продукта (оказания услуги) "
        "и движения информации. Это организующая схема, а не только «кто кому подчиняется»."
    )
    return "\n".join(lines)


def _parse_flow_blocks(text: str) -> list[str]:
    parts = [p.strip() for p in text.replace("→", "->").split("->") if p.strip()]
    return parts if parts else []


def map_departments_to_blocks(
    org_json: dict,
    simple_structure: str,
    *,
    org_type: str = "",
    model: str = "gpt-4o",
    client: OpenAI | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """
    Сопоставляет departments/roles с укрупнёнными блоками из simple_structure.
    Возвращает {block_name: [{dept_label, role_label, person_name}, ...]}.
    """
    blocks = _parse_flow_blocks(simple_structure)
    if not blocks:
        blocks = ["Управление", "Производство"]

    empty: dict[str, list[dict[str, Any]]] = {b: [] for b in blocks}
    depts = org_json.get("departments") or []
    if not depts:
        owner = (org_json.get("owner_label") or "").strip()
        director = (org_json.get("director_label") or "").strip()
        if owner or director:
            empty.setdefault(blocks[0], []).append(
                {
                    "dept_label": "Верхний уровень",
                    "role_label": director or owner or "Руководитель",
                    "person_name": None,
                }
            )
        return enrich_block_roles(org_json, empty)

    require_api_key()
    client = client or OpenAI()
    payload = {
        "blocks": blocks,
        "org_type": org_type,
        "owner_label": org_json.get("owner_label"),
        "director_label": org_json.get("director_label"),
        "departments": depts,
    }
    prompt = (
        "Сопоставь каждый department из JSON с ровно одним block из списка blocks. "
        "Для каждой записи в departments добавь поле mapped_block. "
        "Верни ТОЛЬКО JSON: {\"mappings\": [{\"dept_label\": \"...\", \"mapped_block\": \"...\", "
        "\"role_label\": \"главная должность отдела или null\", \"person_name\": \"ФИО или null\"}]} "
        "Используй role_label руководителя отдела, если виден; иначе dept_label как роль.\n"
        f"Данные:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Ты сопоставляешь отделы с блоками оргсхемы. Только JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=1500,
        )
        text = response.choices[0].message.content.strip()
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            for item in data.get("mappings") or []:
                block = (item.get("mapped_block") or "").strip()
                if block not in empty:
                    for b in blocks:
                        if b.lower() in block.lower() or block.lower() in b.lower():
                            block = b
                            break
                    else:
                        block = blocks[0] if blocks else "Производство"
                empty.setdefault(block, []).append(
                    {
                        "dept_label": item.get("dept_label") or "",
                        "role_label": item.get("role_label") or item.get("dept_label") or "—",
                        "person_name": item.get("person_name"),
                    }
                )
            return enrich_block_roles(org_json, empty)
    except (json.JSONDecodeError, KeyError, IndexError):
        pass

    # Fallback: первый блок — управление, остальные — производство
    for i, d in enumerate(depts):
        dept = (d.get("dept_label") or f"Отдел {i+1}").strip()
        roles = d.get("roles") or []
        lead = None
        for r in roles:
            rl = (r.get("role_label") or "").strip()
            if rl and re.search(
                r"руковод|директор|начальник|главн|зав\.|заведующ",
                rl,
                re.I,
            ):
                lead = r
                break
        role_label = (lead or (roles[0] if roles else {})).get("role_label") or dept
        person = (lead or {}).get("person_name") or d.get("person_name")
        block = blocks[0] if i == 0 and "управ" in dept.lower() else (
            blocks[-1] if len(blocks) > 1 else blocks[0]
        )
        empty.setdefault(block, []).append(
            {
                "dept_label": dept,
                "role_label": role_label,
                "person_name": person,
            }
        )
    return enrich_block_roles(org_json, empty)


def normalize_role_for_display(
    role_label: str,
    dept_label: str,
    block_name: str,
) -> str:
    rl = (role_label or "").strip()
    dl = (dept_label or "").strip()
    block = (block_name or "").lower()
    ctx = f"{rl} {dl}".lower()
    if re.search(r"фин", rl, re.I) and re.search(r"директор", rl, re.I):
        if "маркет" in block or any(
            x in ctx for x in ("продаж", "реклам", "маркет", "колл")
        ):
            return f"Коммерческий директор (на схеме: {rl})"
    return rl or dl or "—"


def rebalance_block_roles(
    org_json: dict,
    block_roles: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Финдиректор с подчинёнными из маркетинга/рекламы → блок Маркетинг."""
    blocks = list(block_roles.keys())
    marketing_key = next((b for b in blocks if "маркет" in b.lower()), None)
    if not marketing_key:
        return block_roles

    depts_by_label = {
        (d.get("dept_label") or ""): d for d in org_json.get("departments") or []
    }

    for block in blocks:
        kept: list[dict[str, Any]] = []
        for entry in block_roles.get(block) or []:
            dl = (entry.get("dept_label") or "").lower()
            dept = depts_by_label.get(entry.get("dept_label") or "")
            if dept and "фин" in dl and "директор" in dl:
                sub_roles = [
                    (r.get("role_label") or "").lower() for r in dept.get("roles") or []
                ]
                if any(
                    x in s for s in sub_roles for x in ("реклам", "продаж", "маркет", "колл")
                ):
                    block_roles.setdefault(marketing_key, []).append(entry)
                    continue
            kept.append(entry)
        block_roles[block] = kept
    return block_roles


def enrich_block_roles(
    org_json: dict,
    block_roles: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Добавляет owner/director_label, если их нет среди отделов (напр. Генеральный директор)."""
    blocks_order = list(block_roles.keys())
    if not blocks_order:
        return block_roles
    mgmt_key = next(
        (b for b in blocks_order if "управ" in b.lower()),
        blocks_order[0],
    )

    def _already_present(label: str) -> bool:
        low = label.lower()
        for entries in block_roles.values():
            for e in entries:
                if low in (e.get("role_label") or "").lower():
                    return True
                if low in (e.get("dept_label") or "").lower():
                    return True
        return False

    for leader in (org_json.get("owner_label"), org_json.get("director_label")):
        text = (leader or "").strip() if leader else ""
        if text and not _already_present(text):
            block_roles.setdefault(mgmt_key, []).insert(
                0,
                {
                    "dept_label": "Верхний уровень",
                    "role_label": text,
                    "person_name": None,
                },
            )
    return block_roles


def build_admin_context_notes(org_json: dict) -> str:
    labels = [(d.get("dept_label") or "") for d in org_json.get("departments") or []]
    low = [l.lower() for l in labels]
    notes: list[str] = []
    if any("бухгал" in l for l in low) and any("фин" in l for l in low):
        notes.append(
            "На схеме есть главный бухгалтер и финансовый директор: "
            "если главбух подчинён финдиректору — по смыслу одна функция учёта "
            "(финдиректор и главбух часто синонимы)."
        )
    if any("фин" in l for l in low) and any(
        x in l for l in low for x in ("продаж", "маркет", "реклам")
    ):
        notes.append(
            "Если финансовый директор возглавляет продажи/маркетинг — "
            "корректное название: коммерческий директор."
        )
    return "\n".join(notes)

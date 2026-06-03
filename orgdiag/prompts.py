from __future__ import annotations

from pathlib import Path

from orgdiag.paths import PROMPTS_DIR


def load_prompt(name: str, prompts_dir: Path | None = None) -> str:
    base = prompts_dir or PROMPTS_DIR
    path = base / name
    if not path.exists():
        raise FileNotFoundError(f"Промпт не найден: {path}")
    return path.read_text(encoding="utf-8")


def load_all_prompts() -> dict[str, str]:
    prompts = {
        "system": load_prompt("2steps_system_prompt.txt"),
        "step1": load_prompt("step1_diagnostics_prompt.txt"),
        "step2": load_prompt("step2_report_prompt.txt"),
        "vision": build_vision_system_prompt(),
    }
    for key, fname in (
        ("pass1", "pass1_blocks_prompt.txt"),
        ("pass2", "pass2_admin_prompt.txt"),
    ):
        if (PROMPTS_DIR / fname).exists():
            prompts[key] = load_prompt(fname)
    return prompts


SIDEWAYS_TREE_EXAMPLE = """
Собственник → Директор → 4 управление (Производство)
                           ├─ Руководитель производства
                           ├─ Мастера (2)
                           └─ Рабочие (2)

                     → 2 управление (Маркетинг / Продажи)
                           ├─ Руководитель отдела продаж
                           ├─ Ассистент (1)
                           └─ Менеджеры продаж (12)

                     → 3 управление (Бухгалтерия)
                           ├─ Главный бухгалтер (1)
                           ├─ Бухгалтер (1)
                           └─ Экономист (1)
""".strip()


def build_vision_system_prompt() -> str:
    return f"""
Ты — аналитик оргструктур. По изображению оргструктуры извлеки структуру и верни СТРОГО JSON по схеме ниже.
Никакого текста вне JSON. Никакого markdown.

Требования:
1) Удали любые 4-буквенные коды/метки (например, психотипы, MBTI и т.п.) — НЕ включай их в результат.
2) Количества вида x2 / ×2 / 2 шт / 2 человека — конвертируй в целое count.
3) Если количество не указано, ставь count = 1.
4) Нормализуй названия управлений, где возможно: "1 управление", "2 управление", "3 управление", "4 управление", "7 управление".
   Если номера нет, оставь как есть.
5) В результате верни owner_label, director_label и departments с roles.
6) Если на схеме указаны ФИО руководителей — добавь person_name на уровне department или role (иначе null).

Схема JSON:
{{
  "owner_label": "Собственник" | null,
  "director_label": "Директор" | "Операционный директор" | "Исполнительный директор" | null,
  "departments": [
    {{
      "dept_label": "4 управление (Производство)",
      "person_name": "Иванов И.И." | null,
      "roles": [
        {{"role_label": "Мастера", "count": 2, "person_name": null}},
        {{"role_label": "Рабочие", "count": 2, "person_name": null}}
      ]
    }}
  ]
}}

Важно: итог должен быть пригоден для вывода "горизонтального дерева" примерно как в примере ниже (пример НЕ возвращай):
{SIDEWAYS_TREE_EXAMPLE}
""".strip()

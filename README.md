# org_diagnost

Диагностика оргструктур по изображению: Vision → упрощение → матрица боли → HTML/PDF-отчёт.

**Методология:** [`docs/reference_org_scheme.md`](docs/reference_org_scheme.md) (исходник — [`docs/Упрощ оргсхема.pdf`](docs/Упрощ%20оргсхема.pdf)). Отчёты для разбора — в `html_out/`.

Репозиторий: [github.com/SergeyK3/org_diagnost](https://github.com/SergeyK3/org_diagnost)

## Миграция с sergey_kim / Colab

Проект вынесен из `AiUnivercity/Stage2HR/kim_sergey/sergey_kim` в автономный Python-репозиторий. Colab и ноутбуки **не** входят в этот репозиторий.

| Было (sergey_kim) | Стало (org_diagnost) |
|-------------------|----------------------|
| `colabs/prompts/` | `prompts/` |
| `colabs/matrix_defects.txt` | `data/matrix_defects.txt` |
| `colabs/DejaVuSans.ttf` | `data/DejaVuSans.ttf` |
| `colabs/.env` | `.env` в корне проекта |
| `colabs/reports/` | `reports/` |
| `colabs/venv/` | `.venv` в корне (`python -m venv .venv`) |
| `run_orgdiag.ps1` → venv в colabs | `run_orgdiag.ps1` → `.venv` |

После клона: скопируйте ключ из старого `colabs/.env` в новый `.env` (файл в git не коммитится). Путь к схемам по умолчанию — `images/` в корне; при необходимости задайте `ORGDIAG_IMAGES_DIR` в `.env`.

Кэш Vision (`cache/*_org.json`) и кейсы (`cases/*.yaml`) совместимы — можно копировать из старого `sergey_kim/cache` и `sergey_kim/cases`.

## Установка

```powershell
cd "D:\MyActivity\MyInfoBusiness\MyPythonApps\14 OrgDiagnost"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
pip install streamlit   # опционально, для UI
```

### Веб-интерфейс (прототип)

```powershell
streamlit run app/streamlit_app.py
```

Шаги: загрузка оргсхемы и боли → заключение (HTML/PDF) → до **3** уточняющих вопросов только по этой диагностике. Посторонние запросы отсекаются правилами и короткой проверкой модели (`gpt-4o-mini`), чтобы не расходовать платный доступ. Лимит настраивается в `.env`: `ORGDIAG_FOLLOWUP_MAX`.

Скопируйте `.env.example` → `.env` и укажите `OPENAI_API_KEY`.

Для PDF с кириллицей положите `data/DejaVuSans.ttf` (шрифт DejaVu Sans).

## CLI

```powershell
.\run_orgdiag.ps1 run `
  --image images/medclinic3.png `
  --org-type "медицинская клиника" `
  --org-name medclinic3 `
  --pain "Перегруз администраторов, очереди, жалобы на сервис" `
  --format html
```

Пакетный прогон: `python -m orgdiag batch cases/medclinic3.yaml`

Выводы pass1/pass2 всегда формируются LLM; в `cache/<stem>/` сохраняется копия для отладки (не подставляется вместо нового анализа).

## Структура

```
orgdiag/       # пакет Python
app/           # Streamlit UI
prompts/       # промпты LLM
data/          # matrix_defects.txt, DejaVuSans.ttf
images/        # входные оргсхемы
cases/         # YAML-кейсы
cache/         # org_json и PNG артефакты
html_out/      # HTML-отчёты
docs/          # reference_org_scheme.md, Упрощ оргсхема.pdf
reports/       # PDF (legacy)
```

# org_diagnost

Диагностика оргструктур по изображению: Vision → упрощение → матрица боли → HTML/PDF-отчёт.

Репозиторий: [github.com/SergeyK3/org_diagnost](https://github.com/SergeyK3/org_diagnost)

## Установка

```powershell
cd "D:\MyActivity\MyInfoBusiness\MyPythonApps\14 OrgDiagnost"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
pip install streamlit   # опционально, для UI
```

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
reports/       # PDF (legacy)
```

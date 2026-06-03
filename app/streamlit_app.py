"""
Локальный UI: streamlit run app/streamlit_app.py (из корня проекта)
"""

from __future__ import annotations

import base64
import html
import sys
import tempfile
from pathlib import Path

# корень проекта в PYTHONPATH
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
import streamlit.components.v1 as components

from orgdiag.config import RunConfig, default_contact
from orgdiag.followup_chat import (
    FollowupTurn,
    answer_followup_question,
    limit_reached_message,
    max_followup_questions,
)
from orgdiag.paths import IMAGES_DIR
from orgdiag.pipeline import DiagnosisResult, run_diagnosis

PASTE_HTML = """
<div id="paste-zone" style="border:2px dashed #ccc;padding:24px;text-align:center;">
  Кликните сюда и вставьте скриншот (Ctrl+V)
</div>
<script>
const zone = window.parent.document.getElementById('paste-zone');
if (zone) {
  zone.setAttribute('tabindex', '0');
  zone.addEventListener('paste', (e) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (const item of items) {
      if (item.type.indexOf('image') !== -1) {
        const blob = item.getAsFile();
        const reader = new FileReader();
        reader.onload = () => {
          window.parent.postMessage({type: 'streamlit:setComponentValue', value: reader.result}, '*');
        };
        reader.readAsDataURL(blob);
        e.preventDefault();
        break;
      }
    }
  });
}
</script>
"""

PAGE_CSS = """
<style>
  .block-container { padding-top: 1.5rem; max-width: 1100px; }
  .od-step {
    display: inline-block;
    padding: 0.35rem 0.75rem;
    border-radius: 999px;
    font-size: 0.85rem;
    margin-right: 0.5rem;
    background: #f0f2f6;
  }
  .od-step-active { background: #e8f4fc; color: #0d47a1; font-weight: 600; }
  .od-card {
    border: 1px solid #e6e6e6;
    border-radius: 8px;
    padding: 1rem 1.25rem;
    margin-bottom: 1rem;
    background: #fafafa;
  }
  .od-chat-user {
    background: #eef6ff;
    border-left: 4px solid #1976d2;
    padding: 0.75rem 1rem;
    margin: 0.5rem 0;
    border-radius: 4px;
  }
  .od-chat-bot {
    background: #f5f5f5;
    border-left: 4px solid #9e9e9e;
    padding: 0.75rem 1rem;
    margin: 0.5rem 0 1rem;
    border-radius: 4px;
  }
</style>
"""


def _init_session() -> None:
    defaults: dict = {
        "diagnosis_result": None,
        "followup_history": [],
        "followup_contact": "",
        "last_cfg_summary": "",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def _followup_used() -> int:
    return len(st.session_state.followup_history)


def _render_steps(active: int) -> None:
    labels = ["1. Исходные данные", "2. Заключение", "3. Уточняющие вопросы"]
    html = []
    for i, label in enumerate(labels, start=1):
        cls = "od-step od-step-active" if i == active else "od-step"
        html.append(f'<span class="{cls}">{label}</span>')
    st.markdown("".join(html), unsafe_allow_html=True)


def _collect_image_inputs() -> tuple[Path | None, str | None, bytes | None]:
    image_path: Path | None = None
    image_url: str | None = None
    uploaded_bytes: bytes | None = None

    tab_file, tab_folder, tab_url = st.tabs(
        ["Файл / вставка", "Папка images/", "Ссылка"]
    )

    with tab_file:
        uploaded = st.file_uploader(
            "Открыть файл",
            type=["png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff"],
            key="upload_file",
        )
        if uploaded is not None:
            uploaded_bytes = uploaded.getvalue()
            st.image(uploaded_bytes, caption="Загруженное изображение", use_container_width=True)

        st.caption("Или вставьте скриншот из буфера (экспериментально):")
        paste_result = components.html(PASTE_HTML, height=120)
        if paste_result and isinstance(paste_result, str) and paste_result.startswith(
            "data:image"
        ):
            _header, b64 = paste_result.split(",", 1)
            uploaded_bytes = base64.b64decode(b64)
            st.image(uploaded_bytes, caption="Вставленный скриншот", use_container_width=True)

    with tab_folder:
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        files = sorted(
            f
            for f in IMAGES_DIR.iterdir()
            if f.is_file()
            and f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}
        )
        if files:
            choice = st.selectbox("Файл из images/", [f.name for f in files])
            image_path = IMAGES_DIR / choice
            st.image(str(image_path), use_container_width=True)
        else:
            st.info(f"Положите изображения в {IMAGES_DIR}")

    with tab_url:
        image_url = st.text_input("URL изображения", key="image_url").strip() or None
        if image_url:
            st.caption("Изображение будет скачано при запуске анализа.")

    return image_path, image_url, uploaded_bytes


def _resolve_image_path(
    image_path: Path | None,
    image_url: str | None,
    uploaded_bytes: bytes | None,
) -> Path | None:
    tmp_path = image_path
    if uploaded_bytes:
        tmp = Path(tempfile.gettempdir()) / "orgdiag_upload.png"
        tmp.write_bytes(uploaded_bytes)
        tmp_path = tmp
    if tmp_path is None and not image_url:
        return None
    if tmp_path is None:
        tmp_path = Path(tempfile.gettempdir()) / "orgdiag_url_placeholder.png"
        tmp_path.touch()
    return tmp_path


def _render_input_form() -> None:
    _render_steps(1)
    st.subheader("Исходные данные")
    st.caption(f"Папка схем: {IMAGES_DIR}")

    image_path, image_url, uploaded_bytes = _collect_image_inputs()

    col1, col2 = st.columns(2)
    with col1:
        org_name = st.text_input("Краткое название организации", key="org_name")
        org_type = st.text_input("Тип предприятия *", "медицинская клиника", key="org_type")
    with col2:
        contact = st.text_input("Контакт в отчёте", default_contact(), key="contact")
        fmt = st.selectbox("Формат отчёта", ["html", "pdf", "both"], index=0, key="fmt")

    pain = st.text_area("Управленческая боль *", height=120, key="pain")

    if st.button("Запустить анализ", type="primary", key="run_analysis"):
        if not org_type.strip():
            st.error("Укажите тип предприятия")
            return
        if not pain.strip():
            st.error("Укажите управленческую боль")
            return

        tmp_path = _resolve_image_path(image_path, image_url, uploaded_bytes)
        if tmp_path is None:
            st.error("Выберите изображение, файл из папки или URL")
            return

        cfg = RunConfig(
            image=tmp_path,
            org_type=org_type.strip(),
            org_name=org_name.strip(),
            pain=pain.strip(),
            contact=contact.strip(),
            output_format=fmt,  # type: ignore[arg-type]
            image_url=image_url,
        )
        with st.spinner("Анализ оргсхемы… это может занять несколько минут."):
            try:
                result = run_diagnosis(cfg)
            except Exception as e:
                st.exception(e)
                return

        st.session_state.diagnosis_result = result
        st.session_state.followup_history = []
        st.session_state.followup_contact = contact.strip()
        st.session_state.last_cfg_summary = (
            f"{cfg.display_org_name} · {cfg.org_type}"
        )
        st.rerun()


def _render_report(result: DiagnosisResult) -> None:
    _render_steps(2)
    st.subheader("Заключение")
    if st.session_state.last_cfg_summary:
        st.caption(st.session_state.last_cfg_summary)

    if result.html_path:
        st.markdown(f"Файл отчёта: `{result.html_path}`")
        st.markdown(
            result.html_path.read_text(encoding="utf-8"),
            unsafe_allow_html=True,
        )
    if result.pdf_path:
        st.markdown(f"PDF: `{result.pdf_path}`")

    with st.expander("Технические артефакты", expanded=False):
        if result.visual_paths:
            for label, path in result.visual_paths.items():
                if path.exists():
                    st.image(str(path), caption=label, use_container_width=True)
        if result.cache_path:
            st.text(f"Кэш org_json: {result.cache_path}")


def _render_followup(result: DiagnosisResult) -> None:
    _render_steps(3)
    st.subheader("Уточняющие вопросы")
    max_q = max_followup_questions()
    used = _followup_used()
    remaining = max(0, max_q - used)
    contact = st.session_state.followup_contact or default_contact()

    st.markdown(
        f'<div class="od-card">'
        f"После заключения можно задать до <b>{max_q}</b> вопросов "
        f"только по этой оргсхеме и выводам отчёта. "
        f"Осталось: <b>{remaining}</b>. "
        f"Посторонние запросы отклоняются (сначала правила, затем короткая проверка модели); "
        f"каждая попытка учитывается в лимите."
        f"</div>",
        unsafe_allow_html=True,
    )

    history: list[FollowupTurn] = st.session_state.followup_history
    if history:
        st.markdown("**История уточнений**")
        for turn in history:
            q_safe = html.escape(turn.question)
            a_safe = html.escape(turn.answer)
            st.markdown(
                f'<div class="od-chat-user"><b>Вы:</b> {q_safe}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="od-chat-bot"><b>Ответ:</b> {a_safe}</div>',
                unsafe_allow_html=True,
            )

    if remaining <= 0:
        st.warning(limit_reached_message(contact=contact))
        if st.button("Новая диагностика", key="new_diag_limit"):
            st.session_state.diagnosis_result = None
            st.session_state.followup_history = []
            st.rerun()
        return

    question = st.text_area(
        "Ваш вопрос по оргструктуре или схеме",
        height=100,
        placeholder="Например: почему блок «Контроль качества» у нас не выделен отдельно?",
        key="followup_question",
    )

    col_a, col_b = st.columns([1, 3])
    with col_a:
        ask = st.button("Спросить", type="primary", key="ask_followup")
    with col_b:
        if st.button("Новая диагностика", key="new_diag"):
            st.session_state.diagnosis_result = None
            st.session_state.followup_history = []
            st.rerun()

    if ask:
        q = question.strip()
        if not q:
            st.error("Введите вопрос")
            return
        with st.spinner("Проверка темы и подготовка ответа…"):
            try:
                reply = answer_followup_question(
                    q,
                    result=result,
                    history=[t for t in history if t.allowed],
                    contact=contact,
                )
            except Exception as e:
                st.exception(e)
                return

        history.append(
            FollowupTurn(question=q, answer=reply.text, allowed=reply.allowed)
        )
        st.session_state.followup_history = history
        st.rerun()


def main() -> None:
    st.set_page_config(
        page_title="Оргдиагностика",
        layout="wide",
        page_icon="📊",
    )
    _init_session()
    st.markdown(PAGE_CSS, unsafe_allow_html=True)
    st.title("Диагностика оргструктуры")
    st.caption("Прототип интерфейса · загрузка схемы → заключение → до 3 уточнений")

    result: DiagnosisResult | None = st.session_state.diagnosis_result

    if result is None:
        _render_input_form()
        return

    st.success("Диагностика выполнена")
    tab_report, tab_qa = st.tabs(["Заключение", "Уточняющие вопросы"])
    with tab_report:
        _render_report(result)
    with tab_qa:
        _render_followup(result)


if __name__ == "__main__":
    main()

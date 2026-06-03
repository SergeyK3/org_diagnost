"""
Локальный UI: streamlit run app/streamlit_app.py (из корня проекта)
"""

from __future__ import annotations

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
from orgdiag.paths import IMAGES_DIR
from orgdiag.pipeline import run_diagnosis

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


def main() -> None:
    st.set_page_config(page_title="Оргдиагностика", layout="wide")
    st.title("Диагностика оргструктуры")
    st.caption(f"Папка схем: {IMAGES_DIR}")

    tab_file, tab_folder, tab_url = st.tabs(
        ["Файл / вставка", "Папка images/", "Ссылка"]
    )

    image_path: Path | None = None
    image_url: str | None = None
    uploaded_bytes: bytes | None = None

    with tab_file:
        uploaded = st.file_uploader(
            "Открыть файл",
            type=["png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff"],
        )
        if uploaded is not None:
            uploaded_bytes = uploaded.getvalue()
            st.image(uploaded_bytes, caption="Загруженное изображение", use_container_width=True)

        st.caption("Или вставьте скриншот из буфера (экспериментально):")
        paste_result = components.html(PASTE_HTML, height=120)
        if paste_result and isinstance(paste_result, str) and paste_result.startswith("data:image"):
            import base64

            header, b64 = paste_result.split(",", 1)
            uploaded_bytes = base64.b64decode(b64)
            st.image(uploaded_bytes, caption="Вставленный скриншот", use_container_width=True)

    with tab_folder:
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        files = sorted(
            f
            for f in IMAGES_DIR.iterdir()
            if f.is_file() and f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}
        )
        if files:
            choice = st.selectbox("Файл из images/", [f.name for f in files])
            image_path = IMAGES_DIR / choice
            st.image(str(image_path), use_container_width=True)
        else:
            st.info(f"Положите изображения в {IMAGES_DIR}")

    with tab_url:
        image_url = st.text_input("URL изображения").strip() or None
        if image_url:
            st.caption("Изображение будет скачано при запуске анализа.")

    org_name = st.text_input("Краткое название организации", "")
    org_type = st.text_input("Тип предприятия *", "медицинская клиника")
    pain = st.text_area("Управленческая боль *", height=120)
    contact = st.text_input("Контакт в отчёте", default_contact())
    fmt = st.selectbox("Формат отчёта", ["html", "pdf", "both"], index=0)
    no_llm = st.checkbox("Без LLM-выводов (только диаграммы)", value=False)

    if st.button("Запустить анализ", type="primary"):
        if not org_type.strip():
            st.error("Укажите тип предприятия")
            return
        if not pain.strip():
            st.error("Укажите управленческую боль")
            return

        tmp_path: Path | None = image_path
        if uploaded_bytes:
            tmp = Path(tempfile.gettempdir()) / "orgdiag_upload.png"
            tmp.write_bytes(uploaded_bytes)
            tmp_path = tmp
        if tmp_path is None and not image_url:
            st.error("Выберите изображение, файл из папки или URL")
            return

        if tmp_path is None:
            tmp_path = Path(tempfile.gettempdir()) / "orgdiag_url_placeholder.png"
            tmp_path.touch()

        cfg = RunConfig(
            image=tmp_path,
            org_type=org_type.strip(),
            org_name=org_name.strip(),
            pain=pain.strip(),
            contact=contact.strip(),
            output_format=fmt,  # type: ignore[arg-type]
            image_url=image_url,
            with_block_analysis=not no_llm,
            with_admin_analysis=not no_llm,
        )
        with st.spinner("Анализ…"):
            try:
                result = run_diagnosis(cfg)
            except Exception as e:
                st.exception(e)
                return

        st.success("Готово")
        if result.html_path:
            st.markdown(f"**HTML:** `{result.html_path}`")
            st.markdown(result.html_path.read_text(encoding="utf-8"), unsafe_allow_html=True)
        if result.pdf_path:
            st.markdown(f"**PDF:** `{result.pdf_path}`")


if __name__ == "__main__":
    main()

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from orgdiag.paths import FONT_FILE


def ensure_font_registered(font_path: Path | None = None) -> str:
    path = font_path or FONT_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"Шрифт DejaVuSans.ttf не найден: {path}\n"
            "Положите файл в data/DejaVuSans.ttf (скачайте DejaVu Sans)."
        )
    if "DejaVu" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("DejaVu", str(path)))
    return "DejaVu"


def generate_pdf_report(
    filename: Path,
    *,
    profile_text: str,
    org_structure_text: str,
    simple_structure_text: str,
    compare_text: str,
    pain_text: str,
    pain_analysis_text: str,
    causes_text: str = "",
    actions_text: str = "",
    conclusion_text: str | None = None,
    font_path: Path | None = None,
) -> Path:
    ensure_font_registered(font_path)
    filename = Path(filename)
    filename.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(filename),
        pagesize=A4,
        leftMargin=25 * mm,
        rightMargin=20 * mm,
        topMargin=25 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CustomTitle",
            fontName="DejaVu",
            fontSize=14,
            leading=18,
            alignment=TA_LEFT,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CustomSection",
            fontName="DejaVu",
            fontSize=12,
            leading=15,
            spaceAfter=5,
            spaceBefore=8,
            textColor=colors.HexColor("#003366"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="CustomNormalDejaVu",
            fontName="DejaVu",
            fontSize=10,
            leading=13,
            spaceAfter=3,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CustomSmall",
            fontName="DejaVu",
            fontSize=9,
            leading=11,
            spaceAfter=2,
        )
    )

    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    elements: list = []
    elements.append(Paragraph("Отчет по диагностике оргструктуры", styles["CustomTitle"]))
    elements.append(Paragraph(f"Дата и время формирования: {now}", styles["CustomSmall"]))
    elements.append(Spacer(1, 8))

    elements.append(Paragraph(f"Профиль предприятия - {profile_text.strip()}", styles["CustomSection"]))
    elements.append(Spacer(1, 3))
    elements.append(Paragraph(f"Боль: {pain_text.strip()}", styles["CustomSection"]))
    elements.append(Spacer(1, 3))

    elements.append(Paragraph("Оргструктура (иерархия)", styles["CustomSection"]))
    for line in org_structure_text.split("\n"):
        if line.strip():
            elements.append(Paragraph(line, styles["CustomNormalDejaVu"]))
    elements.append(Spacer(1, 3))

    elements.append(Paragraph("Упрощённая оргструктура (LLM)", styles["CustomSection"]))
    for line in simple_structure_text.split("\n"):
        if line.strip():
            elements.append(Paragraph(line, styles["CustomNormalDejaVu"]))
    elements.append(Spacer(1, 3))

    elements.append(Paragraph("Сравнение реальной и эталонной структуры", styles["CustomSection"]))
    for line in compare_text.split("\n"):
        if line.strip():
            elements.append(Paragraph(line, styles["CustomNormalDejaVu"]))
    elements.append(Spacer(1, 3))

    elements.append(Paragraph("Интерпретация управленческой боли", styles["CustomSection"]))
    for line in pain_analysis_text.split("\n"):
        if line.strip():
            elements.append(Paragraph(line, styles["CustomNormalDejaVu"]))
    elements.append(Spacer(1, 3))

    if causes_text.strip() or actions_text.strip():
        elements.append(Paragraph("Сводка по матрице дефектов", styles["CustomSection"]))
        if causes_text.strip():
            elements.append(Paragraph("Системные причины:", styles["CustomNormalDejaVu"]))
            for line in causes_text.split("\n"):
                if line.strip():
                    elements.append(Paragraph(line, styles["CustomNormalDejaVu"]))
        if actions_text.strip():
            elements.append(Paragraph("Управленческие действия:", styles["CustomNormalDejaVu"]))
            for line in actions_text.split("\n"):
                if line.strip():
                    elements.append(Paragraph(line, styles["CustomNormalDejaVu"]))
        elements.append(Spacer(1, 3))

    elements.append(Paragraph("Заключение", styles["CustomSection"]))
    if conclusion_text:
        summary_lines = [
            line
            for line in conclusion_text.strip().split("\n")
            if not line.startswith("Отчет по диагностике")
            and not line.startswith("Дата и время формирования")
            and not line.startswith("Профиль предприятия")
        ]
        short = "\n".join(summary_lines[:6])
        if short.strip():
            for line in short.split("\n"):
                if line.strip():
                    elements.append(Paragraph(line, styles["CustomNormalDejaVu"]))
    elements.append(
        Paragraph(
            "Это только предварительная диагностика предприятия. "
            "Для подтверждения и уточнения рекомендуем обратиться к специалисту.",
            styles["CustomNormalDejaVu"],
        )
    )

    doc.build(elements)
    return filename.resolve()

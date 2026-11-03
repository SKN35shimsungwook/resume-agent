"""결과를 DOCX·PDF로 내보낸다.

DOCX는 python-docx, PDF는 reportlab + Windows 기본 한글 글꼴(맑은 고딕)을 쓴다.
"""
import io
from pathlib import Path

from .pipeline import current_answers, resume_text

FONT_PATHS = [Path("C:/Windows/Fonts/malgun.ttf"), Path("C:/Windows/Fonts/NanumGothic.ttf")]


def _blocks(state: dict, profile) -> list[tuple[str, str]]:
    """(종류, 글) 목록. 종류: title, h1, h2, p"""
    a = state.get("analysis", {})
    blocks = [("title", f"{a.get('company', '')} · {a.get('position', '')}"),
              ("p", f"{profile.name}  {profile.email}  {profile.phone}".strip())]
    if state.get("resume"):
        blocks.append(("h1", "이력서"))
        resume = state["resume"]
        if resume.get("summary"):
            blocks.append(("p", resume["summary"]))
        for sec in resume.get("sections", []):
            blocks.append(("h2", sec.get("title", "")))
            blocks += [("p", f"• {it.get('text', '')}") for it in sec.get("items", [])]
    answers = current_answers(state)
    if answers:
        blocks.append(("h1", "자기소개서"))
        for ans in answers:
            blocks.append(("h2", ans.get("question", "")))
            blocks.append(("p", ans.get("text", "")))
    return blocks


def to_docx(state: dict, profile) -> bytes:
    import docx
    from docx.shared import Pt

    doc = docx.Document()
    style = doc.styles["Normal"]
    style.font.name = "맑은 고딕"
    style.font.size = Pt(10.5)
    for kind, text in _blocks(state, profile):
        if kind == "title":
            doc.add_heading(text, level=0)
        elif kind == "h1":
            doc.add_heading(text, level=1)
        elif kind == "h2":
            doc.add_heading(text, level=2)
        else:
            doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def to_pdf(state: dict, profile) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    font = next((p for p in FONT_PATHS if p.exists()), None)
    if font is None:
        raise RuntimeError("한글 글꼴(맑은 고딕)을 찾지 못해 PDF를 만들 수 없습니다. DOCX로 받아 주세요.")
    pdfmetrics.registerFont(TTFont("KR", str(font)))
    styles = {
        "title": ParagraphStyle("t", fontName="KR", fontSize=17, leading=24, spaceAfter=6),
        "h1": ParagraphStyle("h1", fontName="KR", fontSize=14, leading=20, spaceBefore=10, spaceAfter=4),
        "h2": ParagraphStyle("h2", fontName="KR", fontSize=11.5, leading=17, spaceBefore=8, spaceAfter=2),
        "p": ParagraphStyle("p", fontName="KR", fontSize=10.5, leading=17, wordWrap="CJK"),
    }
    story = []
    for kind, text in _blocks(state, profile):
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
        story.append(Paragraph(safe, styles[kind]))
        if kind == "p":
            story.append(Spacer(1, 2 * mm))
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                      topMargin=18 * mm, bottomMargin=18 * mm).build(story)
    return buf.getvalue()

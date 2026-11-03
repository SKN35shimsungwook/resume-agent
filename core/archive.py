"""지원 보관용 PDF: 면접·시험 준비 때 '이 회사에 뭘 냈더라'를 한 파일로 보게 한다.

자동 저장 시점: 작성이 끝났을 때, 답변을 직접 고쳐 저장했을 때, 지원 상태를 '제출'로 바꿨을 때.
파일 위치: data/applications/2026-11/2026-11-03_회사_직무.pdf (날짜 = 제출일, 제출 전이면 작성일)
담는 것: 표지(회사·직무·날짜·링크·근무 조건) → 회사 정보·공고와 비교 → 제출한 자소서 → 맞춤 이력서
        → 인사담당자 점수·평가 기준·지적 → 예상 면접 질문 → 확인이 필요했던 문장 → 공고 원문
"""
import io
import re
from datetime import date
from pathlib import Path

from .checks import INFO_FIELDS
from .paths import workspace
from .pipeline import current_answers, load_state, resume_text, save_state

FONT = Path("C:/Windows/Fonts/malgun.ttf")
FONT_BOLD = Path("C:/Windows/Fonts/malgunbd.ttf")


def archive_dir() -> Path:
    return workspace() / "applications"


def file_date(state: dict) -> str:
    return state.get("applied_on") or (state.get("created") or date.today().isoformat())[:10]


def file_path(state: dict) -> Path:
    a = state.get("analysis", {})
    name = re.sub(r'[\\/:*?"<>|\s]+', "_", f"{file_date(state)}_{a.get('company', '회사')}_{a.get('position', '')}")
    return archive_dir() / file_date(state)[:7] / f"{name.strip('_')[:90]}.pdf"


def build_pdf(state: dict, profile) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    if not FONT.exists():
        raise RuntimeError("한글 글꼴(맑은 고딕)을 찾지 못해 PDF를 만들 수 없습니다.")
    pdfmetrics.registerFont(TTFont("KR", str(FONT)))
    pdfmetrics.registerFont(TTFont("KRB", str(FONT_BOLD if FONT_BOLD.exists() else FONT)))
    registerFontFamily("KR", normal="KR", bold="KRB", italic="KR", boldItalic="KRB")
    base = ParagraphStyle("p", fontName="KR", fontSize=9.8, leading=16, wordWrap="CJK")
    st = {
        "title": ParagraphStyle("t", parent=base, fontName="KRB", fontSize=18, leading=25, spaceAfter=4),
        "sub": ParagraphStyle("s", parent=base, textColor=colors.HexColor("#52514e"), spaceAfter=8),
        "h1": ParagraphStyle("h1", parent=base, fontName="KRB", fontSize=13, leading=19, spaceBefore=12, spaceAfter=5,
                             textColor=colors.HexColor("#1c5cab")),
        "h2": ParagraphStyle("h2", parent=base, fontName="KRB", fontSize=10.5, leading=16, spaceBefore=7, spaceAfter=2),
        "p": ParagraphStyle("p2", parent=base, spaceAfter=4),
        "small": ParagraphStyle("sm", parent=base, fontSize=8, leading=11.5, textColor=colors.HexColor("#52514e")),
        "cell": ParagraphStyle("c", parent=base, fontSize=8.8, leading=13),
    }

    def esc(t) -> str:
        return str(t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")

    def para(text, style="p"):
        return Paragraph(esc(text), st[style])

    def table(rows, widths):
        t = Table([[Paragraph(esc(c), st["cell"]) for c in r] for r in rows], colWidths=[w * mm for w in widths],
                  hAlign="LEFT")
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f4f6fa")),
                               ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#e1e0d9")),
                               ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        return t

    a, hr, res = state.get("analysis", {}), state.get("hr", {}), state.get("research", {})
    info = a.get("info") or {}
    story = [para(f"{a.get('company', '')} · {a.get('position', '')}", "title"),
             para(f"{profile.name} · 지원 상태 {state.get('apply_status', '준비')} · "
                  f"{'제출일' if state.get('applied_on') else '작성일'} {file_date(state)}", "sub")]

    rows = [["지원일", state.get("applied_on") or "아직 제출 전"], ["작성일", (state.get("created") or "")[:10]],
            ["공고 링크", state.get("source_url") or "(붙여 넣은 공고)"], ["세부 직무", a.get("subrole", "")]]
    for key, label in INFO_FIELDS.items():
        item = info.get(key) or {}
        value = item.get("value") or (f"확인 필요 (AI가 '{item['dropped']}'라고 했지만 공고에서 근거를 못 찾음)"
                                      if item.get("dropped") else "공고에 없음")
        rows.append([label, value])
    rows.append(["적합도", f"{(a.get('fit') or {}).get('score', '-')}점 — {(a.get('fit') or {}).get('why', '')}"])
    rows.append(["인사담당자", f"{hr.get('total', '-')}점 · {hr.get('verdict', '-')}"])
    story += [para("지원 정보", "h1"), table(rows, [32, 138])]

    prof = res.get("company_profile") or {}
    if res:
        story.append(para("회사 정보", "h1"))
        if res.get("summary"):
            story.append(para(res["summary"]))
        crow = [["위치", ", ".join(prof.get("locations") or []) or "-"], ["업종", prof.get("industry") or "-"],
                ["규모", prof.get("size") or "-"], ["설립", prof.get("founded") or "-"],
                ["주요 사업", ", ".join(res.get("business") or []) or "-"],
                ["주요 제품", ", ".join(res.get("products") or []) or "-"],
                ["주요 고객", ", ".join(prof.get("main_customers") or []) or "-"],
                ["인재상", ", ".join(res.get("talent") or a.get("talent") or []) or "-"]]
        story.append(table(crow, [32, 138]))
        if res.get("compare"):
            story.append(para("공고 내용과 회사 자료 비교", "h2"))
            cmp_rows = [["항목", "공고", "회사 자료", "비교"]] + [
                [c.get("item", ""), c.get("posting", ""), c.get("company", ""), c.get("match", "")] for c in res["compare"]]
            t = table(cmp_rows, [24, 62, 62, 22])
            story.append(t)
        if res.get("role_challenges"):
            story.append(para("이 직무가 풀어야 할 과제", "h2"))
            story += [para(f"• {c.get('challenge', '')}") for c in res["role_challenges"]]
        story.append(para("출처: " + " · ".join(res.get("sources") or []), "small"))

    answers = current_answers(state)
    if answers:
        story.append(PageBreak())
        story.append(para("제출한 자기소개서", "h1"))
        for ans in answers:
            story.append(para(ans.get("question", ""), "h2"))
            story.append(para(ans.get("text", "")))
            story.append(para(f"{len(ans.get('text', ''))}자 (공백 포함)", "small"))
    if state.get("resume"):
        story.append(para("맞춤 이력서", "h1"))
        story.append(para(resume_text(state["resume"])))

    if hr:
        story.append(PageBreak())
        story.append(para(f"인사담당자 평가 — {hr.get('total', '-')}점 · {hr.get('verdict', '-')}", "h1"))
        if hr.get("scores"):
            srows = [["평가 기준", "점수", "근거"]] + [
                [s.get("item", ""), f"{s.get('score', '')}/{s.get('max', '')}", s.get("evidence", "")] for s in hr["scores"]]
            story.append(table(srows, [45, 18, 107]))
        if hr.get("reasons"):
            story.append(para("지적 사항", "h2"))
            story += [para(f"• {x}") for x in hr["reasons"]]
        if hr.get("interview_questions"):
            story.append(para("예상 면접 질문", "h1"))
            story += [para(f"{i}. {q}") for i, q in enumerate(hr["interview_questions"], 1)]
            story.append(para("답변 준비: 위 자기소개서의 해당 경험을 '상황 → 내가 한 일 → 결과 → 배운 점' 순서로 1분 안에 말해 보세요.",
                              "small"))
    missing = (state.get("draft") or {}).get("missing_questions") or []
    if state.get("final_check") or missing:
        story.append(para("확인이 필요했던 것", "h1"))
        story += [para(f"• (문장 확인) {v.get('sentence', '')}") for v in state.get("final_check", [])]
        story += [para(f"• (추가 질문) {q.get('question', '')}") for q in missing]
        story.append(para("면접에서 이 부분을 물으면 실제 있었던 일로만 답하세요.", "small"))

    story.append(PageBreak())
    story.append(para("공고 원문 (저장 당시)", "h1"))
    story.append(para(re.sub(r"\n{3,}", "\n\n", state.get("posting", ""))[:30000], "small"))

    buf = io.BytesIO()

    def footer(c, d):
        c.setFont("KR", 7.5)
        c.setFillColor(colors.HexColor("#898781"))
        c.drawString(20 * mm, 10 * mm, f"{a.get('company', '')} · {a.get('position', '')} · {file_date(state)}")
        c.drawRightString(A4[0] - 20 * mm, 10 * mm, str(d.page))

    SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
                      title=f"{a.get('company', '')} {a.get('position', '')}").build(story, onFirstPage=footer,
                                                                                   onLaterPages=footer)
    return buf.getvalue()


def save(rid: str, profile=None) -> Path | None:
    """보관 PDF를 (다시) 저장한다. 날짜가 바뀌어 파일 이름이 달라지면 예전 파일은 지운다."""
    from .profile import load_profile
    state = load_state(rid)
    if not state.get("analysis", {}).get("company") or state.get("status") not in ("done", "waiting"):
        return None
    path = file_path(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_pdf(state, profile or load_profile()))
    old = state.get("pdf_path")
    if old and Path(old) != path and Path(old).exists():
        Path(old).unlink()
    state["pdf_path"] = str(path)
    save_state(rid, state)
    return path


def set_status(rid: str, status: str) -> None:
    """지원 상태를 바꾼다. 처음 '제출'로 바꾸는 날이 지원일이 되고, 보관 PDF를 그 날짜로 다시 저장한다."""
    state = load_state(rid)
    state["apply_status"] = status
    if status == "제출" and not state.get("applied_on"):
        state["applied_on"] = date.today().isoformat()
    save_state(rid, state)
    save(rid)

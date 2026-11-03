import json

import streamlit as st

from core import ui
from core.loaders import load_file, load_url
from core.pipeline import STEPS, char_count, final_answers, list_runs, run

STEP_LABELS = {
    "analyze": "공고 분석", "draft": "경험 고르기·초안", "checks": "코드 검사",
    "verify_a": "검증 A (사실·일관성)", "verify_b": "검증 B (구조·직무 적합·문장)",
    "revise": "수정", "hr": "인사담당자 평가", "revise_2": "추가 수정",
}
RULE_NAMES = {"FA": "사실", "FC": "제출 점검", "WR": "작성", "CF": "직무·회사 적합", "MA": "경험 배치",
              "AN": "공고 분석", "RS": "이력서", "HR": "인사담당자"}

ui.back_link()
st.markdown("## 🏢 회사 맞춤 작성")
st.caption("공고를 넣으면 분석 → 초안 → 검증 → 수정 → 인사담당자 평가까지 한 번에 해요. 공고 하나에 AI 호출 5~7번(일반 모드).")

# ── 공고 넣기 ─────────────────────────────────────────────
with st.container(border=True, key="card_posting"):
    tab_url, tab_file, tab_text = st.tabs(["링크", "파일", "붙여넣기"])
    urls = tab_url.text_area("공고 링크 (한 줄에 하나, 여러 개면 차례로 처리)", height=90)
    files = tab_file.file_uploader("공고 파일", type=["pdf", "docx", "hwp", "hwpx", "txt", "md"],
                                   accept_multiple_files=True)
    pasted = tab_text.text_area("공고 내용 붙여넣기", height=160)

    if st.button("▶ 작성 시작", type="primary", width="stretch"):
        postings = []
        for u in [u.strip() for u in urls.splitlines() if u.strip()]:
            try:
                postings.append(load_url(u))
            except Exception as e:
                st.error(f"{u}: {e}")
        for f in files or []:
            try:
                postings.append(load_file(f.name, f.getvalue()))
            except Exception as e:
                st.error(f"{f.name}: {e}")
        if pasted.strip():
            postings.append(pasted)

        for i, text in enumerate(postings, start=1):
            with st.status(f"공고 {i}/{len(postings)} 처리 중", expanded=True) as box:
                state = run(text, on_step=lambda s, _: box.write(f"• {STEP_LABELS.get(s, s)}"))
                company = state.get("analysis", {}).get("company", "")
                if state["status"] == "done":
                    box.update(label=f"공고 {i} 완료 · {company}", state="complete")
                else:
                    box.update(label=f"공고 {i} 일시 멈춤 · {company} — 다시 시작하면 이어서 해요", state="error")
                    st.warning(state.get("error", ""))

# ── 결과 목록 ─────────────────────────────────────────────
runs = list_runs()
st.markdown(f"### 결과 ({len(runs)}건)")
if not runs:
    st.caption("아직 처리한 공고가 없어요.")

ui.tiles([
    ("완료", f"{sum(r.get('status') == 'done' for r in runs)}건"),
    ("멈춤", f"{sum(r.get('status') == 'paused' for r in runs)}건"),
    ("평균 점수", f"{(sum(r.get('hr', {}).get('total') or 0 for r in runs if r.get('hr')) / max(1, sum(1 for r in runs if r.get('hr')))):.0f}"),
    ("확인 질문", f"{sum(len(r.get('draft', {}).get('missing_questions', [])) for r in runs)}개"),
])

for r in sorted(runs, key=lambda r: -(r.get("hr", {}).get("total") or 0)):
    a = r.get("analysis", {})
    hr = r.get("hr", {})
    icon = {"done": "✅", "paused": "⏸️"}.get(r.get("status"), "⏳")
    title = f"{icon} {a.get('company', '(분석 전)')} · {a.get('position', '')} · `{a.get('subrole', '')}`"
    if hr:
        title += f" · {hr.get('total', '-')}점 {hr.get('verdict', '')}"
    with st.expander(title):
        done = r.get("done", [])
        ui.steps([STEP_LABELS[s] for s in STEPS], len(done) + 1)
        if r.get("status") == "paused":
            st.warning(f"멈춘 이유: {r.get('error', '')}")
            if st.button("이어서 하기", key=f"resume_{r['id']}"):
                with st.spinner("이어서 처리 중..."):
                    run(r["posting"])
                st.rerun()

        t_ans, t_check, t_hr, t_info = st.tabs(["최종 답변", "검증 결과", "인사담당자", "공고 분석"])
        with t_ans:
            limits = {q.get("question"): q.get("limit", 0) for q in a.get("questions", [])}
            for ans in final_answers(r):
                with_sp, no_sp = char_count(ans.get("text", ""))
                limit = limits.get(ans.get("question"), 0)
                st.markdown(f"**{ans.get('question', '')}**")
                st.caption(f"{with_sp}자 (공백 제외 {no_sp}자)" + (f" / 제한 {limit}자" if limit else ""))
                st.text_area("답변", ans.get("text", ""), height=220, key=f"ans_{r['id']}_{ans.get('question', '')[:20]}",
                             label_visibility="collapsed")
            for q in r.get("draft", {}).get("missing_questions", []):
                st.info(f"확인 질문 · {q.get('card_id', '')}: {q.get('question', '')}")
        with t_check:
            allv = (r.get("code_violations", []) + r.get("verify_a", {}).get("violations", [])
                    + r.get("verify_b", {}).get("violations", []))
            st.caption(f"코드 검사 {len(r.get('code_violations', []))}건 · 검증 A {r.get('verify_a', {}).get('score', '-')}점 · "
                       f"검증 B {r.get('verify_b', {}).get('score', '-')}점")
            for v in allv:
                rule = v.get("rule", "")
                st.markdown(f"- **{rule}** ({RULE_NAMES.get(rule[:2], '')}) {v.get('why', '')}"
                            + (f" — `{v.get('sentence', '')[:60]}`" if v.get("sentence") else ""))
            for rev in r.get("revisions", []):
                st.caption(f"{STEP_LABELS.get(rev['after'], rev['after'])}에서 고친 곳 {len(rev.get('changes', []))}건")
        with t_hr:
            if hr:
                ui.tiles([("총점", f"{hr.get('total', '-')}"), ("판정", hr.get("verdict", "-")),
                          ("탈락 사유", f"{len(hr.get('reasons', []))}개"),
                          ("면접 질문", f"{len(hr.get('interview_questions', []))}개")])
                for s in hr.get("scores", []):
                    st.markdown(f"- {s.get('item', '')}: **{s.get('score', '')}/{s.get('max', '')}** — {s.get('evidence', '')}")
                if hr.get("reasons"):
                    st.markdown("**지적 사항**")
                    for x in hr["reasons"]:
                        st.markdown(f"- {x}")
                if hr.get("interview_questions"):
                    st.markdown("**면접 예상 질문**")
                    for x in hr["interview_questions"]:
                        st.markdown(f"- {x}")
        with t_info:
            st.markdown(f"**직무 판단**: `{a.get('subrole', '')}` — {a.get('subrole_why', '')}")
            st.json(a, expanded=False)

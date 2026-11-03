"""인사담당자 첨삭: 내가 쓴 지원서를 인사담당자가 빨간 펜으로 본 것처럼 보여 준다."""
import html

import streamlit as st

from core import db, ui
from core.pipeline import apply_hr_feedback, char_count, current_answers, load_state, rescore

ui.back_link()
st.markdown("## 🖍️ 인사담당자 첨삭")
st.caption("글 쓴 AI와 다른 AI가 이 직무 인사담당자 입장에서 채점하고 지적한 내용이에요. "
           "지적받은 문장은 본문에 표시돼요.")

rows = [r for r in db.applications() if r["hr_total"] is not None]
if not rows and db.rebuild():
    rows = [r for r in db.applications() if r["hr_total"] is not None]
if not rows:
    st.info("아직 채점된 지원서가 없어요. '회사 맞춤 작성'에서 공고를 넣어 보세요.")
    st.stop()

order = st.radio("정렬", ["최근", "점수 낮은 순", "점수 높은 순"], horizontal=True, label_visibility="collapsed")
if order != "최근":
    rows = sorted(rows, key=lambda r: r["hr_total"], reverse=(order == "점수 높은 순"))
labels = {f"{r['hr_total']}점 {r['verdict']} · {r['company']} · {r['position']} "
          f"({r['applied_on'] or (r['created'] or '')[:10]})": r["run_id"] for r in rows}
keys = list(labels)
start = next((i for i, k in enumerate(keys) if labels[k] == st.session_state.get("review_rid")), 0)
rid = labels[st.selectbox("지원서 고르기", keys, index=start)]
st.session_state["review_rid"] = rid

state = load_state(rid)
hr = state.get("hr") or {}
a = state.get("analysis", {})

ui.tiles([("총점", f"{hr.get('total', '-')}점"), ("판정", hr.get("verdict", "-")),
          ("지적 사항", f"{len(hr.get('reasons', [])) + len(hr.get('violations', []))}개"),
          ("면접 질문", f"{len(hr.get('interview_questions', []))}개")])
if state.get("hr_history"):
    st.caption("채점 기록: " + " → ".join(f"{h.get('total')}점" for h in state["hr_history"]) + f" → 지금 {hr.get('total')}점")
if state.get("hr_applied"):
    st.info("지적대로 고친 글이에요. 점수는 '다시 채점'을 눌러야 바뀌어요.")

# ── 평가 기준 ─────────────────────────────────────────────
with st.container(border=True, key="card_scores"):
    st.markdown("**평가 기준별 점수**")
    for s in hr.get("scores", []):
        score, mx = s.get("score") or 0, s.get("max") or 1
        c1, c2 = st.columns([3, 1], vertical_alignment="center")
        c1.markdown(f"**{s.get('item', '')}**  \n<span style='color:#52514e;font-size:.88rem'>{html.escape(s.get('evidence', ''))}</span>",
                    unsafe_allow_html=True)
        c2.progress(min(1.0, score / mx), text=f"{score}/{mx}")

# ── 총평 ──────────────────────────────────────────────────
if hr.get("reasons"):
    with st.container(border=True, key="card_reasons"):
        st.markdown("**총평 (지적 사항)**")
        for x in hr["reasons"]:
            st.markdown(f"- {x}")

# ── 본문 첨삭 ─────────────────────────────────────────────
marks = [v for v in hr.get("violations", []) if v.get("sentence") or v.get("question")]
answers = current_answers(state)


def locate(v: dict) -> tuple[int, str]:
    """지적이 붙을 답변 번호와 본문 속 문장. 인사담당자가 문장을 '…'로 줄이거나 문항 전체를 지적하기도 해서 느슨하게 찾는다."""
    sent = (v.get("sentence") or "").strip().rstrip(".…").rstrip(".").strip()
    for i, ans in enumerate(answers):
        text = ans.get("text", "")
        if sent and sent in text:
            return i, sent
        head = sent[:25]
        if len(head) >= 15 and head in text:  # 앞부분만 맞으면 그 문장 전체를 표시한다
            start = text.index(head)
            end = min([text.find(t, start + len(head)) for t in ("다.", "요.") if text.find(t, start + len(head)) >= 0] or [len(text) - 2])
            return i, text[start:end + 2]
        q = ans.get("question", "").strip().rstrip(".…").strip()
        if (sent and sent == q) or (v.get("question") and v["question"].strip()[:20] == q[:20]):
            return i, ""  # 문항 전체에 대한 지적
    return -1, ""


placed = {}
for v in marks:
    i, sent = locate(v)
    placed.setdefault(i, []).append((v, sent))

st.markdown("### 본문 첨삭")
st.caption("노란 표시가 인사담당자가 지적한 문장이에요. 아래에 이유가 붙어 있어요.")
for i, ans in enumerate(answers):
    text = ans.get("text", "")
    shown = html.escape(text)
    for v, sent in placed.get(i, []):
        if sent:
            shown = shown.replace(html.escape(sent), f"<mark style='background:#fde68a;border-radius:3px'>{html.escape(sent)}</mark>")
    with st.container(border=True):
        n, _ = char_count(text)
        st.markdown(f"**{ans.get('question', '')}**")
        st.caption(f"{n}자")
        st.html(f"<div style='line-height:1.8;font-size:.95rem'>{shown}</div>")
        for v, sent in placed.get(i, []):
            where = "문장" if sent else "답변 전체"
            st.markdown(f"🖍️ ({where}) {v.get('why', '')}")
if placed.get(-1):
    st.markdown("**본문에서 위치를 못 찾은 지적** (이미 고쳐졌을 수 있어요)")
    for v, _ in placed[-1]:
        st.markdown(f"- `{(v.get('sentence') or '')[:60]}` — {v.get('why', '')}")

# ── 면접 대비 ─────────────────────────────────────────────
if hr.get("interview_questions"):
    with st.container(border=True, key="card_interview"):
        st.markdown("**예상 면접 질문** — 자소서에 쓴 경험을 '상황 → 내가 한 일 → 결과 → 배운 점' 순서로 1분 안에 말해 보세요.")
        for i, q in enumerate(hr["interview_questions"], 1):
            st.markdown(f"{i}. {q}")

# ── 다음 행동 ─────────────────────────────────────────────
st.write("")
c1, c2, c3 = st.columns(3)
if c1.button("✍️ 지적대로 고치기 (호출 1번)", type="primary", width="stretch",
             help="지적 사항만 고치고 경험 카드에 없는 사실은 만들지 않아요. 고치기 전 글은 수정 기록에 남아요."):
    with st.spinner("고치는 중..."):
        apply_hr_feedback(rid)
    st.rerun()
if c2.button("🔁 다시 채점 (호출 1번)", width="stretch", help="직접 고쳤거나 지적대로 고친 뒤 점수를 다시 받아요."):
    with st.spinner("채점 중..."):
        rescore(rid)
    st.rerun()
c3.page_link("views/write.py", label="직접 고치러 가기 →")
st.caption(f"{a.get('company', '')} · {a.get('position', '')} — 고친 내용은 보관 PDF에도 자동으로 반영돼요.")

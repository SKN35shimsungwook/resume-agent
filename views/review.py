"""인사담당자 첨삭: 내가 쓴 지원서를 인사담당자가 빨간 펜으로 본 것처럼 보여 준다.

화면 순서: 공고 대조표 → 먼저 고칠 3가지 → 7가지 관점 → 점수 → 본문 첨삭 → 면접 질문.
7관점 결과가 없는 예전 채점은 점수·총평·본문 첨삭만 보여 준다.
"""
import html

import streamlit as st

from core import db, ui
from core.pipeline import apply_hr_feedback, char_count, current_answers, load_state, rescore, set_discarded
from core.prompts import HR_PERSPECTIVES

ui.back_link()
st.markdown("## 🖍️ 인사담당자 첨삭")
st.caption("글 쓴 AI와 다른 AI가 이 직무 인사담당자 입장에서 7가지 관점으로 보고 지적한 내용이에요. "
           "지적마다 내 서류 문장과 공고 문장을 그대로 옮겨 와요. 나이·성별·사진·가족 정보는 평가하지 않아요.")

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
views = hr.get("perspectives") or []
discarded = set(state.get("hr_discarded") or [])
answers = current_answers(state)

GRAY = "color:#52514e;font-size:.88rem"


def esc(text: str) -> str:
    """[확인 필요]는 내가 직접 채울 자리라 눈에 띄게 칠한다."""
    return html.escape(text or "").replace(
        "[확인 필요]", "<mark style='background:#fecaca;border-radius:3px;padding:0 2px'>[확인 필요]</mark>")


def quote(label: str, text: str, ok) -> str:
    """서류·공고 인용 한 줄. 코드가 원문에서 못 찾은 인용은 표시해 둔다(모델이 바꿔 썼을 수 있다)."""
    if not text:
        return ""
    warn = "" if ok is not False else " <span style='color:#b45309'>⚠️ 원문에서 그대로 못 찾음</span>"
    return (f"<div style='border-left:3px solid #d6d3d1;padding:2px 10px;margin:4px 0;{GRAY}'>"
            f"<b>{label}</b> “{esc(text)}”{warn}</div>")


def toggle(key: str) -> None:
    discarded.symmetric_difference_update({key})
    set_discarded(rid, list(discarded))


def finding_block(f: dict, slot: str) -> None:
    """지적 하나: 내 문장 → 공고 문장 → 문제 → 고칠 방향, 그리고 버리기 버튼."""
    gone = f.get("key") in discarded
    style = "opacity:.45;text-decoration:line-through" if gone else ""
    body = (quote("내 서류", f.get("my_quote", ""), f.get("my_ok"))
            + quote("공고", f.get("posting_quote", ""), f.get("posting_ok"))
            + (f"<div style='margin-top:6px'>🖍️ {esc(f.get('problem', ''))}</div>" if f.get("problem") else "")
            + (f"<div>✏️ <b>고칠 방향</b> {esc(f.get('fix', ''))}</div>" if f.get("fix") else "")
            + (f"<div style='{GRAY}'>먼저 고칠 이유: {esc(f['why_first'])}</div>" if f.get("why_first") else ""))
    st.html(f"<div style='line-height:1.7;font-size:.93rem;{style}'>{body}</div>")
    if f.get("key"):
        st.button("↩️ 되살리기" if gone else "🗑️ 내 경험과 달라요 — 버리기", key=f"{slot}_{f['key']}",
                  on_click=toggle, args=(f["key"],), type="tertiary",
                  help="버린 지적은 '지적대로 고치기'에서 빠져요.")


# ── 요약 ──────────────────────────────────────────────────
if views:
    clean = sum(1 for p in views if p.get("result") == "고칠 것 없음")
    ui.tiles([("총점", f"{hr.get('total', '-')}점"), ("판정", hr.get("verdict", "-")),
              ("고칠 것 없음", f"{clean}/{len(views)} 관점"),
              ("먼저 고칠 것", f"{len([t for t in hr.get('top3', []) if t.get('key') not in discarded])}개")])
else:
    ui.tiles([("총점", f"{hr.get('total', '-')}점"), ("판정", hr.get("verdict", "-")),
              ("지적 사항", f"{len(hr.get('reasons', [])) + len(hr.get('violations', []))}개"),
              ("면접 질문", f"{len(hr.get('interview_questions', []))}개")])
if state.get("hr_history"):
    st.caption("채점 기록: " + " → ".join(f"{h.get('total')}점" for h in state["hr_history"]) + f" → 지금 {hr.get('total')}점")
if state.get("hr_applied"):
    st.info("지적대로 고친 글이에요. 점수는 '다시 채점'을 눌러야 바뀌어요.")
if any("[확인 필요]" in x.get("text", "") for x in answers):
    st.warning("본문에 **[확인 필요]** 자리가 남아 있어요. 경험 카드에 없는 수치라 AI가 비워 둔 곳이니, "
               "실제 숫자를 직접 채우거나 문장을 빼고 내세요.")

if not views:
    st.caption("이 지원서는 7가지 관점 첨삭이 생기기 전에 채점됐어요. 아래 '다시 채점'을 누르면 7관점으로 다시 봐요.")

# ── 1. 공고 대조표 ────────────────────────────────────────
STATUS = {"반영": "✅ 반영", "약함": "🟡 약함", "빠짐": "❌ 빠짐", "AI가 안 봄": "❔ AI가 안 봄"}
if hr.get("posting_match"):
    with st.container(border=True, key="card_match"):
        st.markdown("**① 공고 대조표** — 공고의 자격 요건·우대 사항이 내 서류 어디에 있는지")
        cells = "".join(
            f"<tr><td style='white-space:nowrap'>{html.escape(m.get('kind', ''))}</td>"
            f"<td>“{esc(m.get('requirement', ''))}”"
            + ("" if m.get("requirement_ok") is not False else " <span style='color:#b45309'>⚠️</span>") + "</td>"
            f"<td style='white-space:nowrap'>{STATUS.get(m.get('status', ''), html.escape(m.get('status', '')))}</td>"
            f"<td>{('“' + esc(m['my_quote']) + '”') if m.get('my_quote') else '<span style=color:#a8a29e>서류에 없음</span>'}"
            + ("" if m.get("my_ok") is not False else " <span style='color:#b45309'>⚠️</span>")
            + (f"<div style='{GRAY}'>{esc(m['note'])}</div>" if m.get("note") else "") + "</td></tr>"
            for m in hr["posting_match"])
        st.html("<table style='width:100%;border-collapse:collapse;font-size:.9rem;line-height:1.6'>"
                "<thead><tr style='text-align:left;border-bottom:1px solid #e7e5e4'>"
                "<th>구분</th><th>공고 문장</th><th>상태</th><th>내 서류 문장</th></tr></thead>"
                f"<tbody>{cells}</tbody></table>"
                "<style>td{padding:6px 8px;border-bottom:1px solid #f5f5f4;vertical-align:top}</style>")
        st.caption("⚠️는 AI가 옮긴 문장을 원문에서 글자 그대로 찾지 못한 경우예요.")

# ── 2. 먼저 고칠 3가지 ────────────────────────────────────
if views:
    with st.container(border=True, key="card_top3"):
        st.markdown("**② 먼저 고칠 3가지** — 합격에 가장 크게 영향을 주는 것만 골랐어요. 내 경험과 다르면 버리세요.")
        if not hr.get("top3"):
            st.success("모든 관점에서 고칠 것 없음이에요.")
        for i, t in enumerate(hr.get("top3", []), 1):
            st.markdown(f"**{i}. {t.get('perspective', '')}**")
            finding_block(t, "top")

# ── 3. 7가지 관점 ─────────────────────────────────────────
if views:
    st.markdown("**③ 7가지 관점**")
    asks = dict(HR_PERSPECTIVES)
    for p in views:
        n = len(p.get("findings") or [])
        icon = "✅" if p.get("result") == "고칠 것 없음" else ("⚪" if p.get("result") == "결과 없음" else "🖍️")
        tail = p.get("result") if n == 0 else f"지적 {n}개"
        with st.expander(f"{icon} {p.get('name', '')} — {tail}", expanded=False):
            st.caption(asks.get(p.get("name", ""), ""))
            if n == 0:
                st.markdown("고칠 것 없음" if p.get("result") != "결과 없음" else "이번 채점에서 이 관점 결과가 오지 않았어요.")
            for f in p.get("findings") or []:
                finding_block(f, f"p{p.get('name', '')}")

# ── 점수 ──────────────────────────────────────────────────
with st.expander(f"평가 기준별 점수 ({hr.get('total', '-')}점)", expanded=not views):
    for s in hr.get("scores", []):
        score, mx = s.get("score") or 0, s.get("max") or 1
        c1, c2 = st.columns([3, 1], vertical_alignment="center")
        c1.markdown(f"**{s.get('item', '')}**  \n<span style='{GRAY}'>{html.escape(s.get('evidence', ''))}</span>",
                    unsafe_allow_html=True)
        c2.progress(min(1.0, score / mx), text=f"{score}/{mx}")
    if hr.get("reasons"):
        st.markdown("**총평**")
        for x in hr["reasons"]:
            st.markdown(f"- {x}")

# ── 본문 첨삭 ─────────────────────────────────────────────
marks = [v for v in hr.get("violations", [])
         if (v.get("sentence") or v.get("question")) and v.get("key") not in discarded]


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
st.caption("노란 표시가 지적받은 문장이에요. 버린 지적은 표시하지 않아요.")
for i, ans in enumerate(answers):
    text = ans.get("text", "")
    shown = esc(text)
    for v, sent in placed.get(i, []):
        if sent:
            shown = shown.replace(esc(sent), f"<mark style='background:#fde68a;border-radius:3px'>{esc(sent)}</mark>")
    with st.container(border=True):
        n, _ = char_count(text)
        st.markdown(f"**{ans.get('question', '')}**")
        st.caption(f"{n}자")
        st.html(f"<div style='line-height:1.8;font-size:.95rem'>{shown}</div>")
        for v, sent in placed.get(i, []):
            where = "문장" if sent else "답변 전체"
            who = f"[{v['rule']}] " if v.get("rule") and v["rule"] in dict(HR_PERSPECTIVES) else ""
            st.markdown(f"🖍️ ({where}) {who}{v.get('why', '')}"
                        + (f"  \n✏️ {v['fix_hint']}" if v.get("fix_hint") else ""))
if placed.get(-1):
    st.markdown("**본문에서 위치를 못 찾은 지적** (이력서 문장이거나 이미 고쳐졌을 수 있어요)")
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
label = "✍️ 지적대로 고치기 (호출 1번)" + (f" · 버린 {len(discarded)}개 빼고" if discarded else "")
if c1.button(label, type="primary", width="stretch",
             help="버리지 않은 지적만 고치고, 경험 카드에 없는 수치는 [확인 필요]로 비워 둬요. 고치기 전 글은 수정 기록에 남아요."):
    with st.spinner("고치는 중..."):
        apply_hr_feedback(rid)
    st.rerun()
if c2.button("🔁 다시 채점 (호출 1번)", width="stretch", help="직접 고쳤거나 지적대로 고친 뒤 점수를 다시 받아요."):
    with st.spinner("채점 중..."):
        rescore(rid)
    st.rerun()
c3.page_link("views/write.py", label="직접 고치러 가기 →")
st.caption(f"{a.get('company', '')} · {a.get('position', '')} — 고친 내용은 보관 PDF에도 자동으로 반영돼요.")

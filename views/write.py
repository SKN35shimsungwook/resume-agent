import subprocess
import sys
from pathlib import Path

import streamlit as st

from core import ui
from core.export import to_docx, to_pdf
from core.loaders import load_file, load_url
from core.pipeline import (APPLY_STATUSES, approve, char_count, current_answers, list_runs, restore,
                           resume_text, run, set_field, steps_for)
from core.profile import ExperienceCard, load_profile, save_profile
from core import demo
from core.paths import demo_on, runs_dir
from core.research import search_links

ROOT = Path(__file__).resolve().parent.parent
STEP_LABELS = {
    "analyze": "공고 분석", "research": "회사 리서치", "draft": "경험 고르기·초안", "checks": "코드 검사",
    "verify_a": "검증 A (사실·일관성)", "verify_b": "검증 B (구조·직무 적합·문장)", "revise": "수정",
    "v1_fact": "1차 사실성", "v2_structure": "2차 구조", "v3_fit": "3차 직무 적합", "v4_style": "4차 문장",
    "v5_consistency": "5차 일관성", "resume": "맞춤 이력서", "hr": "인사담당자 평가", "revise_2": "추가 수정",
}
for _r in ["v1_fact", "v2_structure", "v3_fit", "v4_style", "v5_consistency"]:
    STEP_LABELS[f"revise_{_r}"] = f"{STEP_LABELS[_r]} 수정"
RULE_NAMES = {"FA": "사실", "FC": "제출 점검", "WR": "작성", "CF": "직무·회사 적합", "MA": "경험 배치",
              "AN": "공고 분석", "RS": "이력서", "HR": "인사담당자", "PL": "표절·획일성"}
FORMAT_LABELS = {"resume_only": "이력서만", "free_one": "자유 양식 1개", "multi_questions": "문항 여러 개"}

profile = load_profile()
card_titles = {c.id: c.title for c in profile.cards} | {"posting": "공고 내용"}

ui.back_link()
st.markdown("## 🏢 회사 맞춤 작성")
st.caption("공고를 넣으면 분석 → 회사 리서치 → 초안 → 검증 → 수정 → 맞춤 이력서 → 인사담당자 평가까지 해요.")

# ── 공고 넣기 ─────────────────────────────────────────────
with st.container(border=True, key="card_posting"):
    tab_url, tab_file, tab_text = st.tabs(["링크", "파일", "붙여넣기"])
    urls = tab_url.text_area("공고 링크 (한 줄에 하나, 여러 개면 차례로 처리)", height=90)
    files = tab_file.file_uploader("공고 파일", type=["pdf", "docx", "hwp", "hwpx", "txt", "md"],
                                   accept_multiple_files=True)
    if demo_on():
        tab_text.caption("체험용 가상 공고를 골라 넣어 보세요. (시작을 누르면 실제 AI를 불러요)")
        for name, text in demo.demo_postings().items():
            if tab_text.button(f"샘플 공고 넣기 · {name}", key=f"demo_post_{name}"):
                st.session_state["pasted_posting"] = text
    pasted = tab_text.text_area("공고 내용 붙여넣기", height=160, key="pasted_posting")
    extra = st.text_area("회사 자료 링크 (선택: 홈페이지 소개·기사·IR, 한 줄에 하나)", height=70,
                         help="검색 엔진은 긁지 않고, 여기 넣은 페이지와 공고만 읽어서 회사를 정리해요.")
    c1, c2 = st.columns(2)
    mode = c1.radio("모드", ["normal", "precise"], horizontal=True,
                    format_func=lambda m: {"normal": "일반 (호출 6~9번)", "precise": "정밀 (호출 13~17번)"}[m])
    screen = c2.toggle("적합도만 먼저 보기", help="공고당 1번 호출로 분석·적합도만 보고 멈춰요. 마음에 드는 공고만 이어서 작성.")

    if st.button("▶ 시작", type="primary", width="stretch"):
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
        extra_urls = [u.strip() for u in extra.splitlines() if u.strip()]
        for i, text in enumerate(postings, start=1):
            with st.status(f"공고 {i}/{len(postings)} 처리 중", expanded=True) as box:
                state = run(text, on_step=lambda s, _: box.write(f"• {STEP_LABELS.get(s, s)}"), mode=mode,
                            extra_urls=extra_urls, stop_after="analyze" if screen else None)
                company = state.get("analysis", {}).get("company", "")
                label = {"done": "완료", "screened": "적합도 확인", "waiting": "확인 대기"}.get(state["status"])
                if label:
                    box.update(label=f"공고 {i} {label} · {company}", state="complete")
                else:
                    box.update(label=f"공고 {i} 일시 멈춤 · {company} — 다시 시작하면 이어서 해요", state="error")
                    st.warning(state.get("error", ""))

# ── 기본 이력서 ───────────────────────────────────────────
with st.expander("세부 직무별 기본 이력서 (한 번 만들어 두면 공고마다 살짝 고쳐 써요)"):
    from core.pipeline import base_resume, build_base_resume
    for sub in profile.target_roles:
        c1, c2 = st.columns([3, 1], vertical_alignment="center")
        has = base_resume(sub)
        c1.markdown(f"`{sub}` — {'✅ 있음' if has else '없음'}")
        if c2.button("다시 만들기" if has else "만들기", key=f"base_{sub}"):
            with st.spinner(f"{sub} 기본 이력서 만드는 중..."):
                build_base_resume(sub)
            st.rerun()

# ── 결과 목록 ─────────────────────────────────────────────
runs = list_runs()
st.markdown(f"### 결과 ({len(runs)}건)")
scored = [r for r in runs if r.get("hr")]
ui.tiles([
    ("완료", f"{sum(r.get('status') == 'done' for r in runs)}건"),
    ("대기·멈춤", f"{sum(r.get('status') in ('waiting', 'paused', 'screened') for r in runs)}건"),
    ("평균 점수", f"{sum(r['hr'].get('total') or 0 for r in scored) / max(1, len(scored)):.0f}"),
    ("제출", f"{sum(r.get('apply_status') == '제출' for r in runs)}건"),
])
sort_key = st.radio("정렬", ["점수", "적합도", "최근"], horizontal=True, label_visibility="collapsed")
keyf = {"점수": lambda r: -(r.get("hr", {}).get("total") or 0),
        "적합도": lambda r: -(r.get("analysis", {}).get("fit", {}).get("score") or 0),
        "최근": lambda r: r.get("updated", "")}[sort_key]
runs = sorted(runs, key=keyf, reverse=(sort_key == "최근"))

for r in runs:
    rid = r["id"]
    a, hr = r.get("analysis", {}), r.get("hr", {})
    icon = {"done": "✅", "paused": "⏸️", "waiting": "✋", "screened": "🔎"}.get(r.get("status"), "⏳")
    fit = a.get("fit", {}).get("score")
    title = (f"{icon} {a.get('company', '(분석 전)')} · {a.get('position', '')} · `{a.get('subrole', '')}`"
             + (f" · 적합도 {fit}" if fit is not None else "")
             + (f" · {hr.get('total', '-')}점 {hr.get('verdict', '')}" if hr else "")
             + f" · {r.get('apply_status', '준비')}")
    with st.expander(title):
        done = r.get("done", [])
        steps = steps_for(r.get("mode", "normal"))
        st.caption(f"{'정밀' if r.get('mode') == 'precise' else '일반'} 모드 · {FORMAT_LABELS.get(a.get('format'), '')} · "
                   f"진행 {len([s for s in steps if s in done])}/{len(steps)}")

        # 상태별 버튼
        c1, c2, c3 = st.columns(3)
        if r.get("status") == "paused":
            st.warning(f"멈춘 이유: {r.get('error', '')}")
            if c1.button("이어서 하기", key=f"resume_{rid}"):
                with st.spinner("이어서 처리 중..."):
                    run(r["posting"])
                st.rerun()
        if r.get("status") == "screened" and c1.button("이어서 작성", key=f"go_{rid}"):
            with st.spinner("작성 중..."):
                run(r["posting"])
            st.rerun()
        if r.get("status") == "waiting":
            st.info(f"'{STEP_LABELS.get(r.get('waiting_at'), r.get('waiting_at'))}' 결과를 확인하고 계속 진행해 주세요. "
                    "답변을 직접 고치고 싶으면 '최종 답변' 탭에서 고친 뒤 승인하세요.")
            if c1.button("승인하고 계속", key=f"ok_{rid}", type="primary"):
                approve(rid)
                with st.spinner("이어서 처리 중..."):
                    run(r["posting"])
                st.rerun()
        new_status = c2.selectbox("지원 상태", APPLY_STATUSES, index=APPLY_STATUSES.index(r.get("apply_status", "준비")),
                                  key=f"st_{rid}", label_visibility="collapsed")
        if new_status != r.get("apply_status", "준비"):
            set_field(rid, apply_status=new_status)
            st.rerun()

        tabs = st.tabs(["최종 답변", "근거", "수정 기록", "검증 결과", "이력서", "인사담당자", "회사·공고", "내보내기"])
        with tabs[0]:  # 최종 답변 + 확인 질문
            suspects = r.get("final_check", [])
            if suspects:
                st.warning(f"최종본에 경험 카드에 없을 수 있는 문장이 {len(suspects)}개 있어요. 사실인지 확인하고, 아니면 고쳐서 저장하세요.")
                for v in suspects:
                    st.markdown(f"- `{v.get('sentence', '')[:80]}` — {v.get('why', '')}")
            limits = {q.get("question"): q.get("limit", 0) for q in a.get("questions", [])}
            for i, ans in enumerate(current_answers(r)):
                with_sp, no_sp = char_count(ans.get("text", ""))
                limit = limits.get(ans.get("question"), 0)
                st.markdown(f"**{ans.get('question', '')}**")
                st.caption(f"{with_sp}자 (공백 제외 {no_sp}자)" + (f" / 제한 {limit}자" if limit else ""))
                st.text_area("답변", ans.get("text", ""), height=220, key=f"ans_{rid}_{i}", label_visibility="collapsed")
            if current_answers(r) and st.button("고친 답변 저장", key=f"save_{rid}"):
                edited = [dict(ans, text=st.session_state[f"ans_{rid}_{i}"]) for i, ans in enumerate(current_answers(r))]
                hist = r.get("history", []) + [{"label": "직접 수정", "at": "", "answers": edited}]
                set_field(rid, final={"answers": edited, "changes": []}, history=hist)
                st.toast("저장했어요. 문장별 근거는 직접 고친 문장에는 맞지 않을 수 있어요.", icon="✅")
                st.rerun()
            missing = r.get("draft", {}).get("missing_questions", [])
            if missing:
                st.markdown("**확인 질문** — 답하면 경험 카드에 저장돼서 다음 공고부터 쓰여요.")
            for j, q in enumerate(missing):
                reply = st.text_input(f"{card_titles.get(q.get('card_id'), q.get('card_id', ''))} · {q.get('question', '')}",
                                      key=f"mq_{rid}_{j}")
                if reply and st.button("카드에 저장", key=f"mqs_{rid}_{j}"):
                    prof = load_profile()
                    card = next((c for c in prof.cards if c.id == q.get("card_id")), None)
                    if card is None:
                        card = ExperienceCard(title="추가 확인 사실", kind="기타")
                        prof.cards.append(card)
                    card.action = (card.action + f"\n(추가 확인) {q.get('question', '')} → {reply}").strip()
                    save_profile(prof)
                    st.toast("경험 카드에 저장했어요.", icon="✅")
        with tabs[1]:  # 문장별 근거 보고서
            st.caption("문장마다 어떤 경험 카드(또는 공고)를 근거로 썼는지 보여 줘요. 근거가 비어 있으면 확인이 필요해요.")
            for ans in current_answers(r):
                st.markdown(f"**{ans.get('question', '')}**")
                for s in ans.get("sentences", []):
                    ids = s.get("card_ids") or []
                    tag = ", ".join(card_titles.get(i, f"⚠️ 없는 카드 {i}") for i in ids) or "⚠️ 근거 없음"
                    st.markdown(f"- {s.get('text', '')}  \n  ↳ *{tag}*")
        with tabs[2]:  # 수정 전후 비교 + 되돌리기
            hist = r.get("history", [])
            if len(hist) < 2:
                st.caption("아직 수정 기록이 없어요.")
            for k in range(len(hist) - 1, -1, -1):
                h = hist[k]
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1], vertical_alignment="center")
                    c1.markdown(f"**{STEP_LABELS.get(h['label'], h['label'])}** · {h['at']}")
                    if k < len(hist) - 1 and c2.button("이걸로 되돌리기", key=f"undo_{rid}_{k}"):
                        restore(rid, k)
                        st.rerun()
            for rev in r.get("revisions", []):
                st.markdown(f"**{STEP_LABELS.get(rev['after'], rev['after'])}에서 고친 곳 {len(rev.get('changes', []))}건**")
                for ch in rev.get("changes", []):
                    st.markdown(f"- `{ch.get('rule', '')}` {ch.get('why', '')}")
                    c1, c2 = st.columns(2)
                    c1.caption("전")
                    c1.write(ch.get("before", ""))
                    c2.caption("후")
                    c2.write(ch.get("after", ""))
        with tabs[3]:  # 검증 결과
            keys = ["verify_a", "verify_b", "v1_fact", "v2_structure", "v3_fit", "v4_style", "v5_consistency"]
            scores = " · ".join(f"{STEP_LABELS[k]} {r[k].get('score', '-')}점" for k in keys if r.get(k))
            st.caption(f"코드 검사 {len(r.get('code_violations', []))}건 · {scores}")
            allv = r.get("code_violations", []) + [v for k in keys for v in r.get(k, {}).get("violations", [])]
            for v in allv:
                rule = v.get("rule", "")
                st.markdown(f"- **{rule}** ({RULE_NAMES.get(rule[:2], '')}) {v.get('why', '')}"
                            + (f" — `{v.get('sentence', '')[:60]}`" if v.get("sentence") else ""))
        with tabs[4]:  # 맞춤 이력서
            if r.get("resume"):
                st.text(resume_text(r["resume"]))
            else:
                st.caption("아직 맞춤 이력서가 없어요.")
        with tabs[5]:  # 인사담당자
            if hr:
                ui.tiles([("총점", f"{hr.get('total', '-')}"), ("판정", hr.get("verdict", "-")),
                          ("지적 사항", f"{len(hr.get('reasons', []))}개"),
                          ("면접 질문", f"{len(hr.get('interview_questions', []))}개")])
                for s in hr.get("scores", []):
                    st.markdown(f"- {s.get('item', '')}: **{s.get('score', '')}/{s.get('max', '')}** — {s.get('evidence', '')}")
                for title_, key in (("지적 사항", "reasons"), ("면접 예상 질문", "interview_questions")):
                    if hr.get(key):
                        st.markdown(f"**{title_}**")
                        for x in hr[key]:
                            st.markdown(f"- {x}")
        with tabs[6]:  # 회사·공고
            st.markdown(f"**직무 판단**: `{a.get('subrole', '')}` — {a.get('subrole_why', '')}")
            if a.get("fit"):
                st.markdown(f"**적합도 {a['fit'].get('score', '-')}** — {a['fit'].get('why', '')}")
                st.markdown("강점: " + ", ".join(a["fit"].get("strengths", [])) + "  \n부족: " + ", ".join(a["fit"].get("gaps", [])))
            res = r.get("research")
            if res:
                st.markdown(f"**회사 요약**: {res.get('summary', '')}")
                for ch in res.get("role_challenges", []):
                    st.markdown(f"- 직무 과제: {ch.get('challenge', '')} *({ch.get('source', '')})*")
                st.caption("출처: " + " · ".join(res.get("sources", [])))
            if a.get("company"):
                st.markdown("직접 찾아볼 곳: " + " · ".join(f"[{k}]({v})" for k, v in search_links(a["company"]).items()))
            st.json(a, expanded=False)
        with tabs[7]:  # 내보내기 + 사이트 입력
            name = f"{a.get('company', 'result')}_{a.get('position', '')}".replace(" ", "_")[:60]
            c1, c2 = st.columns(2)
            c1.download_button("⬇ DOCX", to_docx(r, profile), file_name=f"{name}.docx", key=f"docx_{rid}")
            try:
                c2.download_button("⬇ PDF", to_pdf(r, profile), file_name=f"{name}.pdf", key=f"pdf_{rid}")
            except Exception as e:
                c2.caption(f"PDF를 만들지 못했어요: {e}")
            st.markdown("**채용 사이트 입력칸 채우기**")
            st.caption("Edge가 열리면 직접 로그인하고 자소서 입력 화면까지 가 주세요. 입력칸이 보이면 답변을 채워요. "
                       "제출·임시저장 버튼은 누르지 않아요 — 확인 후 직접 누르세요.")
            apply_url = st.text_input("지원서 작성 페이지 주소", key=f"apply_{rid}",
                                      value=demo.apply_form_url() if demo_on() else "",
                                      help="체험 모드에서는 가짜 지원서 페이지가 미리 들어가 있어요.")
            if apply_url and st.button("Edge로 열어서 채우기", key=f"fill_{rid}"):
                subprocess.Popen([sys.executable, "-m", "core.site_filler", rid, apply_url], cwd=str(ROOT))
                st.toast("Edge 창을 열었어요. 결과는 잠시 뒤 data/runs 폴더에 기록돼요.", icon="🖥️")
            fill_report = runs_dir() / rid / "site_fill.json"
            if fill_report.exists():
                st.json(fill_report.read_text(encoding="utf-8"), expanded=False)

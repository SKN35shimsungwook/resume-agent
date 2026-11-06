from dataclasses import asdict

import streamlit as st

from core import ui
from core.extract import extract_cards
from core.knowledge import GROUPS, SUBROLE_LABELS
from core.paths import workspace
from core.loaders import load_file, load_url
from datetime import datetime

from core.profile import CARD_KINDS, ExperienceCard, add_answer, is_duplicate, load_profile, save_profile

# 체험 모드를 켜고 끌 때 다른 폴더의 데이터를 들고 있지 않도록, 작업 폴더가 바뀌면 다시 읽는다
if st.session_state.get("profile_ws") != str(workspace()):
    st.session_state.profile = load_profile()
    st.session_state.profile_ws = str(workspace())
profile = st.session_state.profile
# 이 기능 전에 만든 프로필: 카드가 있으면 올려 둔 자료는 이미 정리한 것으로 본다 (다시 읽어 겹치지 않게)
if profile.cards and profile.raw_documents and not profile.processed_docs:
    profile.processed_docs = list(profile.raw_documents)

ui.back_link()
st.markdown("## 🗂️ 내 경험 정리")
st.caption("이력서·포트폴리오를 올리면 경험 카드로 나눠 드려요. 여기 적힌 사실만 AI가 글에 써요.")

current = 1 if not profile.raw_documents and not profile.cards else 2 if not profile.cards else 3
ui.steps(["자료 올리기", "경험 카드 확인", "저장"], current)

# ── 1. 자료 올리기 ────────────────────────────────────────
with st.container(border=True, key="card_upload"):
    files = st.file_uploader(
        "이력서·포트폴리오 파일을 여기에 끌어다 놓으세요 (PDF · DOCX · HWP · HWPX · TXT)",
        type=["pdf", "docx", "hwp", "hwpx", "txt", "md"],
        accept_multiple_files=True,
    )
    url = st.text_input(
        "웹페이지 링크", placeholder="포트폴리오·GitHub·노션 주소 (선택)"
    )
    quick = st.text_area("새 활동 직접 적기 (선택: 이번 주 만든 프로그램·팀플을 자유롭게)", height=90,
                         placeholder="예) 11/3 팀플 — LangGraph로 자소서 검증 에이전트, 내 역할: 평가 화면·시험 30건, 결과: 인사 점수 58→78점")
    if st.button("텍스트 추출", width="stretch"):
        if quick.strip():
            profile.raw_documents[f"직접 입력 {datetime.now():%Y-%m-%d %H:%M}"] = quick.strip()
        for f in files or []:
            try:
                profile.raw_documents[f.name] = load_file(f.name, f.getvalue())
            except Exception as e:
                st.error(f"{f.name}: {e}")
        if url:
            try:
                profile.raw_documents[url] = load_url(url)
            except Exception as e:
                st.error(f"{url}: {e}")

    for name, text in list(profile.raw_documents.items()):
        c1, c2 = st.columns([10, 1], vertical_alignment="center")
        done = "✅ 카드로 정리됨" if name in profile.processed_docs else "🆕 아직 안 정리됨"
        with c1.expander(f"📄 {name} · {len(text):,}자 · {done}"):
            st.text(text[:3000] + ("…" if len(text) > 3000 else ""))
        if c2.button("✕", key=f"rm_{name}", help="이 자료 빼기"):
            del profile.raw_documents[name]
            if name in profile.processed_docs:
                profile.processed_docs.remove(name)
            st.rerun()

    # 매주 새 활동을 더할 때 예전 자료를 다시 읽으면 카드가 겹쳐 쌓여서, 아직 안 정리한 자료만 읽는다
    new_docs = {n: t for n, t in profile.raw_documents.items() if n not in profile.processed_docs}
    if new_docs:
        st.success(f"새 자료 {len(new_docs)}개가 있어요. 'AI로 경험 카드 만들기'를 누르면 이것만 읽어요 (호출 1번쯤).")
        if st.button("✨ AI로 경험 카드 만들기", type="primary", width="stretch"):
            with st.spinner("새 자료를 읽고 경험을 나누는 중..."):
                try:
                    new_cards, questions = extract_cards(new_docs, [c.title for c in profile.cards])
                    added = [c for c in new_cards if not is_duplicate(profile, c)]
                    profile.cards.extend(added)
                    profile.processed_docs += list(new_docs)
                    titles = {c.title: c.id for c in profile.cards}
                    profile.open_questions += [{"card_id": titles.get(q.get("card", ""), ""), "card": q.get("card", ""),
                                                "question": q.get("question", "")} for q in questions if q.get("question")]
                    save_profile(profile)  # 정리 결과를 바로 저장한다 (새로고침해도 남게)
                    st.toast(f"새 카드 {len(added)}장 · 이미 있는 경험이라 건너뜀 {len(new_cards) - len(added)}장 · "
                             f"보완 질문 {len(questions)}개", icon="✅")
                    st.rerun()
                except Exception as e:
                    st.error(f"만들지 못했어요: {e}")
    elif profile.raw_documents:
        st.caption("올린 자료는 모두 카드로 정리했어요. 새 활동이 생기면 위에 적거나 파일을 올려 주세요.")

# ── 2. 경험 카드 ──────────────────────────────────────────
with st.container(border=True, key="card_cards"):
    questions = profile.open_questions
    ui.tiles([
        ("올린 자료", f"{len(profile.raw_documents)}개"),
        ("경험 카드", f"{len(profile.cards)}개"),
        ("수치 있는 카드", f"{sum(1 for c in profile.cards if c.metrics)}개"),
        ("보완 질문", f"{len(questions)}개"),
    ])
    if questions:
        st.markdown("**보완 질문** — 답하면 해당 경험 카드에 덧붙여 저장돼요. 자소서에 쓸 수 있는 사실이 늘어나요.")
    for j, q in enumerate(list(questions)):
        with st.container(border=True):
            st.markdown(f"**{q.get('card', '') or '기타'}** — {q.get('question', '')}")
            c1, c2, c3 = st.columns([6, 1, 1], vertical_alignment="bottom")
            reply = c1.text_input("답", key=f"oq_{j}", label_visibility="collapsed", placeholder="사실만 짧게 적어 주세요")
            if c2.button("저장", key=f"oqs_{j}", disabled=not reply):
                add_answer(profile, q.get("question", ""), reply, q.get("card_id", ""), q.get("card", ""))
                profile.open_questions.pop(j)
                save_profile(profile)
                st.rerun()
            if c3.button("넘기기", key=f"oqx_{j}", help="이 질문은 답하지 않고 지워요"):
                profile.open_questions.pop(j)
                save_profile(profile)
                st.rerun()

    with st.expander("기본 인적사항", expanded=not profile.name):
        c1, c2, c3 = st.columns(3)
        profile.name = c1.text_input("이름", profile.name)
        profile.email = c2.text_input("이메일", profile.email)
        profile.phone = c3.text_input("연락처", profile.phone)
        profile.summary = st.text_input("한 줄 소개", profile.summary)
        profile.education = st.text_area("학력", profile.education, height=80)
        options = [s for subs in GROUPS.values() for s in subs]
        profile.target_roles = st.multiselect(
            "희망 세부 직무 (먼저 고른 것이 공고 분석이 애매할 때 기본값)", options,
            default=[r for r in profile.target_roles if r in options],
            format_func=lambda s: f"{SUBROLE_LABELS.get(s, s)} ({s})",
        )

    for idx, card in enumerate(profile.cards):
        with st.expander(f"{card.kind} · {card.title}  ·  {card.period or '기간 미입력'}"):
            k = card.id
            c1, c2, c3 = st.columns([2, 1, 1])
            card.title = c1.text_input("제목", card.title, key=f"t_{k}")
            card.kind = c2.selectbox(
                "종류", CARD_KINDS,
                index=CARD_KINDS.index(card.kind) if card.kind in CARD_KINDS else 0, key=f"k_{k}",
            )
            card.period = c3.text_input("기간", card.period, key=f"p_{k}")
            c1, c2 = st.columns(2)
            card.organization = c1.text_input("소속·팀", card.organization, key=f"o_{k}")
            card.role = c2.text_input("내 역할", card.role, key=f"r_{k}")
            card.situation = st.text_area("상황 (S)", card.situation, key=f"s_{k}", height=70)
            card.task = st.text_area("과제 (T)", card.task, key=f"ta_{k}", height=70)
            card.action = st.text_area(
                "내가 한 행동 (A) — 가장 자세히", card.action, key=f"a_{k}", height=120
            )
            card.result = st.text_area("결과 (R)", card.result, key=f"re_{k}", height=70)
            card.metrics = st.text_input("수치로 된 성과", card.metrics, key=f"m_{k}")
            card.learned = st.text_area("배운 점·가치관 (V/L)", card.learned, key=f"l_{k}", height=70)
            skills = st.text_input("기술 (쉼표로 구분)", ", ".join(card.skills), key=f"sk_{k}")
            card.skills = [s.strip() for s in skills.split(",") if s.strip()]
            evidence = st.text_input("증빙 링크 (쉼표로 구분)", ", ".join(card.evidence), key=f"e_{k}")
            card.evidence = [e.strip() for e in evidence.split(",") if e.strip()]
            if st.button("🗑️ 이 카드 삭제", key=f"del_{k}"):
                profile.cards.pop(idx)
                st.rerun()

    if st.button("➕ 빈 카드 추가"):
        profile.cards.append(ExperienceCard(title="새 경험"))
        st.rerun()

# ── 3. 저장 ───────────────────────────────────────────────
c1, c2 = st.columns([1, 2], vertical_alignment="center")
if c1.button("💾 전부 저장", type="primary", width="stretch"):
    save_profile(profile)
    st.toast("data/profile.json에 저장했어요.", icon="✅")
with c2.popover("저장될 내용 미리보기"):
    st.json(asdict(profile), expanded=False)

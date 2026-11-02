from dataclasses import asdict

import streamlit as st

from core import ui
from core.extract import extract_cards
from core.loaders import load_file, load_url
from core.profile import CARD_KINDS, ExperienceCard, load_profile, save_profile

if "profile" not in st.session_state:
    st.session_state.profile = load_profile()
profile = st.session_state.profile

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
    if st.button("텍스트 추출", width="stretch"):
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
        with c1.expander(f"📄 {name} · {len(text):,}자"):
            st.text(text[:3000] + ("…" if len(text) > 3000 else ""))
        if c2.button("✕", key=f"rm_{name}", help="이 자료 빼기"):
            del profile.raw_documents[name]
            st.rerun()

    if profile.raw_documents:
        st.success("자료를 읽었어요. 'AI로 경험 카드 만들기'를 눌러 주세요.")
        if st.button("✨ AI로 경험 카드 만들기", type="primary", width="stretch"):
            with st.spinner("자료를 읽고 경험을 나누는 중..."):
                try:
                    new_cards, questions = extract_cards(profile.raw_documents)
                    profile.cards.extend(new_cards)
                    st.session_state.missing_questions = questions
                    st.rerun()
                except Exception as e:
                    st.error(f"만들지 못했어요: {e}")

# ── 2. 경험 카드 ──────────────────────────────────────────
with st.container(border=True, key="card_cards"):
    questions = st.session_state.get("missing_questions", [])
    ui.tiles([
        ("올린 자료", f"{len(profile.raw_documents)}개"),
        ("경험 카드", f"{len(profile.cards)}개"),
        ("수치 있는 카드", f"{sum(1 for c in profile.cards if c.metrics)}개"),
        ("보완 질문", f"{len(questions)}개"),
    ])
    for q in questions:
        st.info(f"**{q.get('card', '')}** — {q.get('question', '')}")

    with st.expander("기본 인적사항", expanded=not profile.name):
        c1, c2, c3 = st.columns(3)
        profile.name = c1.text_input("이름", profile.name)
        profile.email = c2.text_input("이메일", profile.email)
        profile.phone = c3.text_input("연락처", profile.phone)
        profile.summary = st.text_input("한 줄 소개", profile.summary)
        profile.education = st.text_area("학력", profile.education, height=80)
        roles = st.text_input("희망 직무 (쉼표로 구분)", ", ".join(profile.target_roles))
        profile.target_roles = [r.strip() for r in roles.split(",") if r.strip()]

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

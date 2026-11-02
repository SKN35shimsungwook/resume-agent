from dataclasses import asdict

import streamlit as st

from core.extract import extract_cards
from core.loaders import load_file, load_url
from core.profile import CARD_KINDS, ExperienceCard, load_profile, save_profile

st.title("내 정보·경험 카드")
st.caption(
    "여기 적은 사실만 AI가 글에 쓸 수 있습니다. 모든 자료는 data/ 폴더에만 저장되고 깃에 올라가지 않습니다."
)

if "profile" not in st.session_state:
    st.session_state.profile = load_profile()
profile = st.session_state.profile

# ── 기본 인적사항 ─────────────────────────────────────────
with st.expander("기본 인적사항", expanded=not profile.name):
    col1, col2, col3 = st.columns(3)
    profile.name = col1.text_input("이름", profile.name)
    profile.email = col2.text_input("이메일", profile.email)
    profile.phone = col3.text_input("연락처", profile.phone)
    profile.summary = st.text_input("한 줄 소개", profile.summary)
    profile.education = st.text_area("학력", profile.education, height=80)
    roles = st.text_input("희망 직무 (쉼표로 구분)", ", ".join(profile.target_roles))
    profile.target_roles = [r.strip() for r in roles.split(",") if r.strip()]

# ── 자료 올리기 ───────────────────────────────────────────
st.subheader("자료 올리기")
st.caption("이력서·포트폴리오·경력기술서 등. PDF, DOCX, HWP, HWPX, TXT/MD, 웹페이지 링크를 받습니다.")
files = st.file_uploader(
    "파일", type=["pdf", "docx", "hwp", "hwpx", "txt", "md"], accept_multiple_files=True
)
url = st.text_input("웹페이지 링크 (포트폴리오·GitHub·노션 등)")

if st.button("텍스트 추출"):
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
    with st.expander(f"📄 {name} ({len(text):,}자)"):
        st.text_area("추출한 텍스트", text, height=200, key=f"doc_{name}", disabled=True)
        if st.button("이 자료 빼기", key=f"rm_{name}"):
            del profile.raw_documents[name]
            st.rerun()

if profile.raw_documents and st.button("AI로 경험 카드 초안 뽑기"):
    with st.spinner("자료를 읽고 경험을 나누는 중..."):
        try:
            new_cards, questions = extract_cards(profile.raw_documents)
            profile.cards.extend(new_cards)
            st.session_state.missing_questions = questions
            st.success(f"카드 {len(new_cards)}개를 추가했습니다. 아래에서 확인·수정한 뒤 저장하세요.")
        except Exception as e:
            st.error(f"추출 실패: {e}")

for q in st.session_state.get("missing_questions", []):
    st.info(f"**{q.get('card', '')}** — {q.get('question', '')}")

# ── 경험 카드 ─────────────────────────────────────────────
st.subheader(f"경험 카드 ({len(profile.cards)}개)")
if st.button("➕ 빈 카드 추가"):
    profile.cards.append(ExperienceCard(title="새 경험"))

for idx, card in enumerate(profile.cards):
    with st.expander(f"[{card.id}] {card.kind} · {card.title}"):
        k = card.id
        col1, col2, col3 = st.columns([2, 1, 1])
        card.title = col1.text_input("제목", card.title, key=f"t_{k}")
        card.kind = col2.selectbox(
            "종류", CARD_KINDS,
            index=CARD_KINDS.index(card.kind) if card.kind in CARD_KINDS else 0, key=f"k_{k}",
        )
        card.period = col3.text_input("기간", card.period, key=f"p_{k}")
        col1, col2 = st.columns(2)
        card.organization = col1.text_input("소속·팀", card.organization, key=f"o_{k}")
        card.role = col2.text_input("내 역할", card.role, key=f"r_{k}")
        card.situation = st.text_area("상황 (S)", card.situation, key=f"s_{k}", height=70)
        card.task = st.text_area("과제 (T)", card.task, key=f"ta_{k}", height=70)
        card.action = st.text_area("내가 한 행동 (A) — 가장 자세히", card.action, key=f"a_{k}", height=120)
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

st.divider()
if st.button("💾 전부 저장", type="primary"):
    save_profile(profile)
    st.success("data/profile.json에 저장했습니다.")

with st.expander("저장될 내용 미리보기 (JSON)"):
    st.json(asdict(profile), expanded=False)

import streamlit as st

from core import demo
from core.paths import demo_on, set_demo
from core.profile import load_profile

profile = load_profile()

st.markdown("## 어떤 작업을 할까요?")
st.caption("내 경험을 한 번 정리해 두면, 회사마다 맞춤 이력서와 자기소개서를 만들어 드려요.")

# ── 처음 써 보기 ──────────────────────────────────────────
with st.container(border=True, key="card_demo"):
    if demo_on():
        st.html('<div class="ra-mini-title">🧪 지금은 체험 중이에요 (가상 인물 “김예시”)</div>'
                '<div class="ra-mini-desc">내 실제 정보는 그대로 있어요. 다 해 봤으면 “체험 끝내기”를 누르세요.</div>')
        c1, c2, c3 = st.columns(3)
        if c1.button("▶ 따라하기 이어서", type="primary", width="stretch"):
            st.switch_page("views/guide.py")
        if c2.button("처음부터 다시", width="stretch"):
            demo.build(reset=True)
            st.switch_page("views/guide.py")
        if c3.button("체험 끝내기", width="stretch"):
            set_demo(False)
            st.rerun()
    else:
        c1, c2 = st.columns([3, 1], vertical_alignment="center")
        c1.html('<div class="ra-mini-title">처음이라면 → 하나씩 따라하기</div>'
                '<div class="ra-mini-desc">가상 인물로 9단계를 한 화면에 하나씩 해 봐요. 버튼 누르고 → 결과 보고 → 다음. 내 정보는 건드리지 않아요.</div>')
        if c2.button("▶ 시작", type="primary", width="stretch"):
            demo.build(reset=True)
            set_demo(True)
            st.switch_page("views/guide.py")

CARDS = [
    ("🗂️", "내 경험 정리", "이력서·포트폴리오를 올리면 경험 카드로 나눠서 정리해요",
     "views/profile.py", False),
    ("🏢", "회사 맞춤 작성", "공고를 넣으면 맞춤 초안을 쓰고 검증·수정까지 해요",
     "views/write.py", False),
    ("✅", "결과·인사담당자 평가", "점수순으로 보고, 지적 사항과 면접 질문을 확인해요",
     "views/write.py", False),
]

cols = st.columns(3)
for i, (col, (icon, title, desc, page, soon)) in enumerate(zip(cols, CARDS)):
    with col.container(border=True, key=f"card_task_{i}"):
        soon_tag = '<span class="ra-soon">준비 중</span>' if soon else ""
        st.html(
            f'<div class="ra-card-icon">{icon}</div>'
            f'<div class="ra-card-title">{title}{soon_tag}</div>'
            f'<div class="ra-card-desc">{desc}</div>'
        )
        st.page_link(page, label="시작하기 →")

INFO = [
    ("🔒 사실만 써요", "내가 정리한 경험 카드에 있는 내용만 글에 들어가요."),
    ("🧭 5번 검증", "사실 → 구조 → 직무 적합 → 문장 → 일관성 순서로 고쳐요."),
    ("⚖️ 다른 AI가 평가", "글 쓴 AI와 다른 AI가 인사담당자처럼 채점해요."),
]
cols = st.columns(3)
for i, (col, (title, desc)) in enumerate(zip(cols, INFO)):
    with col.container(border=True, key=f"card_info_{i}"):
        st.html(f'<div class="ra-mini-title">{title}</div><div class="ra-mini-desc">{desc}</div>')

st.write("")
left, right = st.columns([3, 1])
if profile.cards:
    left.caption(f"지금 경험 카드 {len(profile.cards)}개가 정리되어 있어요.")
else:
    left.caption("처음이라면 '내 경험 정리'부터 시작하고, API 키는 설정에서 넣어 주세요.")
right.page_link("views/settings.py", label="설정", icon=":material/settings:")

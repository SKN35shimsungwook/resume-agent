import streamlit as st

from core import demo
from core.paths import demo_on, set_demo
from core.profile import load_profile

profile = load_profile()

st.markdown("## 어떤 작업을 할까요?")
st.caption("내 경험을 한 번 정리해 두면, 회사마다 맞춤 이력서와 자기소개서를 만들어 드려요.")

# ── 체험 모드 ─────────────────────────────────────────────
with st.container(border=True, key="card_demo"):
    if demo_on():
        st.html('<div class="ra-mini-title">🧪 지금은 체험 모드예요</div>'
                '<div class="ra-mini-desc">가상 인물 “김예시”와 가상 회사 3곳의 결과가 미리 들어 있어요. '
                '실제 내 정보는 그대로 보관돼 있고, 체험을 끝내면 돌아가요. '
                '“시작”·“이어서 하기”·“승인하고 계속”을 누르면 그때는 실제 AI를 불러요(무료 한도 사용).</div>')
        c1, c2 = st.columns(2)
        if c1.button("체험 데이터 처음 상태로", width="stretch"):
            demo.build(reset=True)
            st.toast("체험 데이터를 처음 상태로 되돌렸어요.", icon="🔄")
            st.rerun()
        if c2.button("체험 끝내기", type="primary", width="stretch"):
            set_demo(False)
            st.rerun()
    else:
        c1, c2 = st.columns([3, 1], vertical_alignment="center")
        c1.html('<div class="ra-mini-title">✨ 샘플로 체험하기</div>'
                '<div class="ra-mini-desc">가상 인물과 가상 공고로 모든 기능을 눌러 볼 수 있어요. 내 데이터는 건드리지 않아요.</div>')
        if c2.button("체험 시작", type="primary", width="stretch"):
            demo.build(reset=False)
            set_demo(True)
            st.rerun()

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

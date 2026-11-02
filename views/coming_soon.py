import streamlit as st

from core import ui

ui.back_link()
st.markdown("## 🚧 준비 중이에요")
with st.container(border=True, key="card_soon"):
    st.write(
        "다음 단계에서 만들어요: 회사 리서치 → 공고 분석 → 경험↔문항 매칭 → 1차 초안 → "
        "5차 검증 → 인사담당자 평가 → 채용 사이트 입력."
    )
    st.caption("전체 계획은 저장소의 PLAN.md에 있어요.")

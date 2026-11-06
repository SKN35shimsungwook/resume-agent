"""관리자: 시험 데이터 켜고 끄기, 지원 현황 DB 다시 만들기."""
import streamlit as st

from core import db, testdata, ui
from core.paths import demo_on, set_test, test_on, workspace

ui.back_link()
st.markdown("## 🛠️ 관리자")
st.caption(f"지금 쓰는 데이터 폴더: `{workspace()}`")

with st.container(border=True, key="card_testdata"):
    st.markdown("**시험 데이터 보기** (가상 인물 30명 × 실제 공고 30개)")
    st.caption("30명 실사용 시험에서 만든 결과를 앱에서 그대로 둘러봐요. 켜 있는 동안 모든 화면이 시험 데이터를 보여 주고, "
               "끄면 내 실제 데이터로 돌아와요. 내 실제 데이터는 건드리지 않아요. 상태는 화면 확인용으로 모두 '제출'로 되어 있어요.")
    if not testdata.available():
        st.info("시험 결과(data/eval)가 없어서 켤 수 없어요.")
    else:
        on = st.toggle("시험 데이터 보기", value=test_on())
        if on != test_on():
            if on and not (workspace().parent / "data_test" / "runs").exists():
                with st.spinner("시험 데이터를 만드는 중... (AI 호출 없음)"):
                    testdata.build()
            set_test(on)
            st.rerun()
        if demo_on():
            st.caption("지금은 체험 모드예요. 시험 데이터를 켜면 체험 모드는 꺼져요.")
        if st.button("시험 데이터 다시 만들기 (AI 호출 없음)"):
            with st.spinner("시험 결과를 다시 옮기고 근무 조건·보관 PDF를 만드는 중..."):
                n = testdata.build()
            st.toast(f"{n['runs']}개를 옮겼어요 (고친 뒤 {n['v2']}개, 보관 PDF {n['pdf']}개).", icon="✅")
            st.rerun()

with st.container(border=True, key="card_db"):
    st.markdown("**지원 현황 DB**")
    st.caption("지원 현황은 공고 결과 파일에서 자동으로 만들어져요. 목록이 이상하면 다시 만들어 주세요. (AI 호출 없음)")
    if st.button("DB 다시 만들기"):
        st.toast(f"{db.rebuild()}건으로 다시 만들었어요.", icon="✅")

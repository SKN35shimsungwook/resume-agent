import streamlit as st

st.set_page_config(page_title="resume-agent", page_icon="📝", layout="wide")

pages = st.navigation(
    [
        st.Page("views/settings.py", title="설정", icon="⚙️"),
        st.Page("views/profile.py", title="내 정보·경험 카드", icon="🗂️", default=True),
        st.Page("views/coming_soon.py", title="회사·생성·검증 (준비 중)", icon="🚧"),
    ]
)
pages.run()

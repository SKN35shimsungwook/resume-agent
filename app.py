import streamlit as st

from core import ui

st.set_page_config(page_title="맞춤 자소서 에이전트", page_icon="📝", layout="centered")

pages = st.navigation(
    [
        st.Page("views/home.py", title="처음", default=True),
        st.Page("views/profile.py", title="내 경험 정리"),
        st.Page("views/settings.py", title="설정"),
        st.Page("views/write.py", title="회사 맞춤 작성"),
        st.Page("views/coming_soon.py", title="준비 중"),
    ],
    position="hidden",
)
ui.page_setup()
PAGE_KEYS = {"처음": "home", "내 경험 정리": "profile", "설정": "settings", "회사 맞춤 작성": "write"}
ui.tutorial_panel(PAGE_KEYS.get(pages.title, ""))
pages.run()
ui.footer()

import streamlit as st

from core import ui
from core.llm import load_config, save_config

config = load_config()

ui.back_link()
st.markdown("## ⚙️ 설정")
st.caption("API 키와 설정은 data/config.json에만 저장되고, 깃에는 올라가지 않아요.")

with st.container(border=True, key="card_api"):
    st.markdown("**API 키**")
    config["gemini_api_key"] = st.text_input("Gemini API 키", config["gemini_api_key"], type="password")
    config["openai_api_key"] = st.text_input("OpenAI API 키", config["openai_api_key"], type="password")

with st.container(border=True, key="card_model"):
    st.markdown("**모델**")
    st.caption("글 쓰는 AI와 평가하는 AI를 다르게 두면, 자기 글을 후하게 보는 경향이 줄어요.")
    providers = ["gemini", "openai"]
    for role, label in (("writer", "작성"), ("judge", "평가 (검증·인사담당자)")):
        c1, c2 = st.columns([1, 2])
        spec = config[role]
        spec["provider"] = c1.selectbox(
            f"{label} 제공자", providers, index=providers.index(spec["provider"]), key=f"{role}_p"
        )
        spec["model"] = c2.text_input(f"{label} 모델", spec["model"], key=f"{role}_m")
    if config["writer"]["provider"] == config["judge"]["provider"]:
        st.warning("작성과 평가가 같은 제공자예요. 가능하면 다르게 두세요.")

with st.container(border=True, key="card_verify"):
    st.markdown("**검증 방식**")
    config["confirm_each_round"] = st.toggle(
        "5차 검증을 회차마다 멈추고 확인하기", config["confirm_each_round"]
    )

if st.button("저장", type="primary", width="stretch"):
    save_config(config)
    st.toast("저장했어요.", icon="✅")

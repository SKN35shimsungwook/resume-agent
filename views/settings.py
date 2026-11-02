import streamlit as st

from core.llm import load_config, save_config

st.title("설정")
st.caption("API 키와 설정은 data/config.json에만 저장되고, 이 폴더는 깃에 올라가지 않습니다.")

config = load_config()

st.subheader("API 키")
config["gemini_api_key"] = st.text_input("Gemini API 키", config["gemini_api_key"], type="password")
config["openai_api_key"] = st.text_input("OpenAI API 키", config["openai_api_key"], type="password")

st.subheader("모델")
st.caption("글 쓰는 모델과 평가하는 모델을 다르게 두면 자기 글을 후하게 보는 편향이 줄어듭니다.")
providers = ["gemini", "openai"]
for role, label in (("writer", "작성 모델"), ("judge", "평가 모델 (검증·인사담당자)")):
    col1, col2 = st.columns([1, 2])
    spec = config[role]
    spec["provider"] = col1.selectbox(
        f"{label} 제공자", providers, index=providers.index(spec["provider"]), key=f"{role}_p"
    )
    spec["model"] = col2.text_input(f"{label} 이름", spec["model"], key=f"{role}_m")

if config["writer"]["provider"] == config["judge"]["provider"]:
    st.warning("작성 모델과 평가 모델의 제공자가 같습니다. 가능하면 다르게 두세요.")

st.subheader("검증 방식")
config["confirm_each_round"] = st.toggle(
    "5차 검증을 회차마다 멈추고 확인하기", config["confirm_each_round"]
)

if st.button("저장", type="primary"):
    save_config(config)
    st.success("저장했습니다.")

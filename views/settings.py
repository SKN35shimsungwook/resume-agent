import streamlit as st

from core import ui
from core.llm import load_config, save_config, today_usage

config = load_config()

ui.back_link()
st.markdown("## ⚙️ 설정")
st.caption("API 키와 설정은 data/config.json에만 저장되고, 깃에는 올라가지 않아요.")
st.page_link("views/admin.py", label="관리자 메뉴 (시험 데이터 켜고 끄기)", icon=":material/admin_panel_settings:")

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
    if config["writer"]["model"] == config["judge"]["model"]:
        st.warning("작성과 평가가 같은 모델이에요. 가능하면 다른 모델(계열)로 두세요.")
    if "openai" in (config["writer"]["provider"], config["judge"]["provider"]):
        st.info("OpenAI는 유료 크레딧을 써요. 무료 등급(Gemini·Gemma)만 쓰려면 둘 다 gemini로 두세요.")

with st.container(border=True, key="card_privacy"):
    st.markdown("**개인정보 가리기**")
    st.caption("Gemini 무료 등급은 보낸 내용이 서비스 개선에 쓰이고 사람이 볼 수도 있어요. "
               "켜 두면 이름·이메일·전화번호·주민번호를 [이름]·[이메일]처럼 바꿔 보내고, 받은 답에서 다시 원래대로 돌려놓아요. "
               "경력 내용은 그대로 가요.")
    config["mask_personal"] = st.toggle("보내기 전에 개인정보 가리기", config.get("mask_personal", True))
    words = st.text_area("더 가릴 단어 (한 줄에 하나: 집 주소, 출신 학교, 가족 이름 등)",
                         "\n".join(config.get("mask_words", [])), height=90)
    config["mask_words"] = [w.strip() for w in words.splitlines() if w.strip()]

with st.container(border=True, key="card_verify"):
    st.markdown("**검증 방식**")
    config["confirm_each_round"] = st.toggle(
        "검증이 끝날 때마다 멈추고 확인하기 (일반 모드는 검증 뒤 1번, 정밀 모드는 회차마다)", config["confirm_each_round"]
    )
    config["research"] = st.toggle(
        "회사 리서치 하기 (회사별로 처음 한 번만 호출, 이후 저장된 결과 재사용)", config.get("research", True)
    )

with st.container(border=True, key="card_budget"):
    st.markdown("**호출 예산**")
    st.caption("하루 공고 30개를 처리하다 멈추지 않도록, 모델별 하루 상한과 예비 모델을 정해요. 상한은 요금제 한도보다 조금 낮게 두세요.")
    usage = today_usage()
    ui.tiles([
        ("오늘 호출", f"{sum(s['calls'] for s in usage.values())}회"),
        ("성공", f"{sum(s['ok'] for s in usage.values())}회"),
        ("입력 토큰", f"{sum(s['in_tokens'] for s in usage.values()):,}"),
        ("출력 토큰", f"{sum(s['out_tokens'] for s in usage.values()):,}"),
    ])
    limits = config.setdefault("daily_limits", {})
    for model in dict.fromkeys([config["writer"]["model"], config["judge"]["model"], *usage]):
        used = usage.get(model, {}).get("calls", 0)
        limits[model] = st.number_input(
            f"{model} 하루 상한 (오늘 {used}회 사용, 0 = 제한 없음)",
            min_value=0, value=int(limits.get(model, 0)), step=50, key=f"limit_{model}",
        )
    st.caption("예비 모델은 쉼표로 여러 개 적으면 앞에서부터 차례로 써요. 예: gemini-3.5-flash-lite, gemma-4-26b-a4b-it")
    for role, label in (("writer", "작성"), ("judge", "평가")):
        fbs = config.setdefault("fallback", {}).get(role) or []
        fbs = fbs if isinstance(fbs, list) else [fbs]
        names = ", ".join(f.get("model", "") for f in fbs if f.get("model"))
        typed = st.text_input(f"{label} 예비 모델 (주 모델이 한도·장애일 때, 모두 Gemini 키 사용)", names, key=f"fb_{role}")
        config["fallback"][role] = [{"provider": "openai" if m.strip().startswith("gpt") else "gemini", "model": m.strip()}
                                    for m in typed.split(",") if m.strip()]

if st.button("저장", type="primary", width="stretch"):
    save_config(config)
    st.toast("저장했어요.", icon="✅")

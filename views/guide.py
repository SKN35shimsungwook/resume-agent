"""하나씩 따라하기: 한 화면에 한 단계만 보여 주는 체험 안내.

버튼 하나 누르고 → 결과를 보고 → '다음'을 누른다. 가상 인물 '김예시'와 가상 공고로 진행하고,
모든 데이터는 체험 폴더(data_demo/)에만 저장된다.
"""
import json

import streamlit as st

from core import demo, ui
from core.export import to_docx, to_pdf
from core.extract import extract_cards
from core.loaders import load_file
from core.paths import DEMO, demo_on, set_demo
from core.pipeline import char_count, current_answers, load_state, run, set_field
from core.profile import load_profile, save_profile

STATE = DEMO / "guide.json"
POSTING = demo.posting("posting_smartfactory.md")
TOTAL = 9


def load() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"step": 1}


def save(g: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(g, ensure_ascii=False), encoding="utf-8")


def go(step: int) -> None:
    g["step"] = step
    save(g)
    st.rerun()


def nav(can_next: bool = True, next_label: str = "다음 →") -> None:
    st.write("")
    c1, _, c3 = st.columns([1, 2, 1])
    if g["step"] > 1 and c1.button("← 이전", width="stretch"):
        go(g["step"] - 1)
    if can_next and c3.button(next_label, type="primary", width="stretch"):
        go(g["step"] + 1)


def box(text: str) -> None:
    st.html(f'<div style="background:#F4F6FA;border-radius:12px;padding:14px 16px;font-size:.95rem;line-height:1.7">{text}</div>')


# 체험 모드가 아니면 켜고 시작한다 (실제 데이터는 건드리지 않는다)
if not demo_on():
    demo.build(reset=False)
    set_demo(True)
    st.rerun()

g = load()
step = g["step"]

st.page_link("views/home.py", label="처음 화면으로", icon=":material/arrow_back:")
st.markdown("## 🧭 하나씩 따라하기")
st.progress(step / TOTAL, text=f"{step} / {TOTAL} 단계")

with st.container(border=True, key="card_guide"):

    # 1 ─ 이 앱이 하는 일
    if step == 1:
        st.markdown("### 1. 이 앱이 하는 일")
        st.write("회사에 낼 **자기소개서와 이력서**를 대신 써 주고, 이상한 곳이 없는지 **검사**해 주는 앱이에요.")
        ui.tiles([("① 내 경험", "정리"), ("② 공고", "넣기"), ("③ 자소서", "쓰기·검사"), ("④ 파일", "받기")])
        box("지금부터 <b>가상 인물 '김예시'</b>가 되어 처음부터 끝까지 한 번 해 볼 거예요.<br>"
            "버튼 하나 누르고 → 결과를 보고 → <b>다음</b>을 누르면 돼요. 내 실제 정보는 건드리지 않아요.")
        nav(next_label="시작하기 →")

    # 2 ─ 이력서 넣기
    elif step == 2:
        st.markdown("### 2. 이력서 넣기")
        st.write("먼저 **내 이력서**를 앱에 넣어요. 실제로 쓸 때는 내 PDF·한글·워드 파일을 올리면 되고, 지금은 김예시의 이력서를 넣어 볼게요.")
        profile = load_profile()
        name, data = demo.sample_resume()
        if name not in profile.raw_documents:
            if st.button("📄 김예시 이력서 넣기", type="primary"):
                profile.raw_documents[name] = load_file(name, data)
                save_profile(profile)
                st.rerun()
        else:
            st.success("이력서를 넣었어요. 앱이 파일에서 글자를 뽑아냈어요.")
            st.text_area("뽑아낸 글 (앞부분)", profile.raw_documents[name][:600], height=200, disabled=True)
        nav(can_next=name in profile.raw_documents)

    # 3 ─ 경험 카드 만들기
    elif step == 3:
        st.markdown("### 3. 경험 카드 만들기")
        st.write("AI가 이력서를 읽고 경험을 **하나씩 카드로** 나눠요. 나중에 자소서는 **이 카드에 적힌 사실만** 써요. 그래서 지어낸 내용이 들어가지 않아요.")
        profile = load_profile()
        if not g.get("extracted"):
            if st.button("✨ AI로 경험 카드 만들기 (5초쯤)", type="primary"):
                with st.spinner("AI가 이력서를 읽는 중..."):
                    cards, questions = extract_cards(profile.raw_documents)
                profile.cards = cards  # 따라하기에서는 이력서에서 만든 카드로 새로 시작한다
                save_profile(profile)
                g["extracted"] = [c.title for c in cards]
                g["questions"] = questions
                save(g)
                st.rerun()
        else:
            st.success(f"경험 카드 {len(profile.cards)}장이 있어요.")
            for c in profile.cards:
                st.markdown(f"- **{c.title}** — {c.period}")
            if g.get("questions"):
                box("AI가 더 알고 싶은 것도 물어봤어요 (나중에 답하면 자소서가 더 좋아져요):<br>"
                    + "<br>".join(f"• {q.get('question', '')}" for q in g["questions"][:3]))
        nav(can_next=bool(g.get("extracted")))

    # 4 ─ 공고 넣기
    elif step == 4:
        st.markdown("### 4. 지원할 공고 넣기")
        st.write("이제 지원할 회사의 **채용 공고**를 넣어요. 실제로 쓸 때는 공고 링크나 내용을 붙여 넣으면 돼요.")
        with st.expander("넣을 공고 보기 (가상 회사 '사아테크')"):
            st.text(POSTING)
        if not g.get("run_id"):
            if st.button("🏢 이 공고 넣고 분석하기 (3초쯤)", type="primary"):
                with st.spinner("AI가 공고를 읽는 중..."):
                    state = run(POSTING, stop_after="analyze")
                g["run_id"] = state["id"]
                save(g)
                st.rerun()
        else:
            a = load_state(g["run_id"]).get("analysis", {})
            st.success("공고를 분석했어요.")
            ui.tiles([("회사", a.get("company", "")), ("자소서 문항", f"{len(a.get('questions', []))}개"),
                      ("나와 맞는 정도", f"{a.get('fit', {}).get('score', '-')}점"), ("형식", "문항 있음" if a.get("questions") else "이력서만")])
            box(f"<b>왜 이 점수인가요?</b> {a.get('fit', {}).get('why', '')}")
        nav(can_next=bool(g.get("run_id")))

    # 5 ─ 자소서 쓰기
    elif step == 5:
        st.markdown("### 5. 자소서 쓰기")
        st.write("버튼을 누르면 AI가 **자소서를 쓰고 → 스스로 검사하고 → 고치고 → 이력서도 맞춰** 줘요. 1분쯤 걸려요.")
        st.caption("무료 AI 서버가 붐비면 다른 AI로 바꿔서 이어 가느라 1~2분 더 걸릴 수 있어요. 창을 닫지 말고 기다려 주세요.")
        state = load_state(g["run_id"])
        if state.get("status") != "done":
            if st.button("✍️ 자소서 쓰기 시작", type="primary"):
                labels = {"research": "회사 알아보기", "draft": "첫 글 쓰기", "checks": "규칙 검사", "verify_a": "사실 확인",
                          "verify_b": "문항에 맞는지 확인", "revise": "고치기", "resume": "이력서 맞추기",
                          "hr": "인사담당자 눈으로 채점", "revise_2": "한 번 더 고치기", "final_check": "마지막 검사"}
                with st.status("쓰는 중...", expanded=True) as s:
                    result = run(POSTING, on_step=lambda k, _: s.write(f"• {labels.get(k, k)}"))
                    s.update(label="다 썼어요!" if result["status"] == "done" else "잠깐 멈췄어요 — 다시 누르면 이어서 해요",
                             state="complete" if result["status"] == "done" else "error")
                st.rerun()
        else:
            st.success("다 썼어요! 첫 번째 문항 답변이에요.")
            ans = current_answers(state)
            if ans:
                st.markdown(f"**{ans[0]['question']}**")
                box(ans[0]["text"])
        nav(can_next=state.get("status") == "done")

    # 6 ─ 검사 결과
    elif step == 6:
        st.markdown("### 6. 검사 결과 보기")
        st.write("AI가 쓴 글을 **다른 AI와 규칙 검사**가 확인했어요. 쉬운 말로 정리하면 이래요.")
        state = load_state(g["run_id"])
        hr = state.get("hr", {})
        fixed = sum(len(r.get("changes", [])) for r in state.get("revisions", []))
        ui.tiles([("인사담당자 점수", f"{hr.get('total', '-')}점"), ("판정", hr.get("verdict", "-")),
                  ("AI가 고친 곳", f"{fixed}곳"), ("내가 확인할 문장", f"{len(state.get('final_check', []))}개")])
        if hr.get("reasons"):
            box("<b>인사담당자가 한 말</b><br>" + "<br>".join(f"• {x}" for x in hr["reasons"][:3]))
        if hr.get("interview_questions"):
            st.write("")
            box("<b>면접에서 물어볼 만한 질문</b><br>" + "<br>".join(f"• {x}" for x in hr["interview_questions"][:3]))
        nav()

    # 7 ─ 직접 고치기
    elif step == 7:
        st.markdown("### 7. 마음에 안 드는 곳 고치기")
        st.write("AI 글은 초안이에요. 읽어 보고 **고치고 싶은 곳을 직접 고친 뒤 저장**하세요. 그대로 둬도 괜찮아요.")
        state = load_state(g["run_id"])
        answers = current_answers(state)
        for i, a in enumerate(answers):
            n, _ = char_count(a["text"])
            st.text_area(f"{a['question']}  ({n}자)", a["text"], height=180, key=f"g_ans_{i}")
        if st.button("💾 고친 내용 저장"):
            edited = [dict(a, text=st.session_state[f"g_ans_{i}"]) for i, a in enumerate(answers)]
            set_field(g["run_id"], final={"answers": edited, "changes": []},
                      history=state.get("history", []) + [{"label": "직접 수정", "at": "", "answers": edited}])
            st.toast("저장했어요.", icon="✅")
        nav()

    # 8 ─ 파일로 받기
    elif step == 8:
        st.markdown("### 8. 파일로 받기")
        st.write("다 됐으면 **워드(DOCX)나 PDF 파일**로 받아서 회사에 내면 돼요. 아래 버튼을 눌러 받아 보세요.")
        state = load_state(g["run_id"])
        profile = load_profile()
        c1, c2 = st.columns(2)
        c1.download_button("⬇ 워드 파일 받기", to_docx(state, profile), file_name="김예시_사아테크.docx", width="stretch")
        try:
            c2.download_button("⬇ PDF 받기", to_pdf(state, profile), file_name="김예시_사아테크.pdf", width="stretch")
        except Exception as e:
            c2.caption(f"PDF를 만들지 못했어요: {e}")
        box("채용 사이트 지원서에 직접 붙여 넣는 기능도 있어요. 익숙해지면 '회사 맞춤 작성' 화면의 <b>내보내기</b> 탭에서 써 보세요.")
        nav()

    # 9 ─ 끝
    else:
        st.markdown("### 9. 끝! 이제 실제로 써 볼까요?")
        st.write("방금 한 순서가 이 앱을 쓰는 순서 전부예요.")
        ui.tiles([("① 이력서", "넣기"), ("② 카드", "만들기"), ("③ 공고 넣고", "자소서 쓰기"), ("④ 고치고", "파일 받기")])
        box("실제로 쓰려면 <b>체험 끝내기</b>를 누르세요. 내 실제 정보로 돌아가요.<br>"
            "다시 연습하고 싶으면 <b>처음부터 다시</b>를 누르세요.")
        st.write("")
        c1, c2 = st.columns(2)
        if c1.button("처음부터 다시", width="stretch"):
            demo.build(reset=True)
            st.rerun()
        if c2.button("체험 끝내기", type="primary", width="stretch"):
            set_demo(False)
            st.switch_page("views/home.py")
        nav(can_next=False)

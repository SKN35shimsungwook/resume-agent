"""체험 모드 튜토리얼: 실제로 쓰는 순서대로 한 단계씩 안내한다.

화면마다 위쪽에 '지금 할 일'을 띄우고, 데이터로 확인할 수 있는 단계는 자동으로 체크한다.
확인할 수 없는 단계(둘러보기, 다운로드 등)는 '했어요' 버튼으로 넘긴다.
진행 상황은 data_demo/tutorial.json에 저장되고, '체험 데이터 처음 상태로'를 누르면 처음부터 다시 한다.
"""
import json
from dataclasses import dataclass
from typing import Callable

from .paths import DEMO
from .pipeline import list_runs
from .profile import load_profile

STATE_PATH = DEMO / "tutorial.json"
PAGES = {
    "home": ("views/home.py", "처음 화면"),
    "profile": ("views/profile.py", "내 경험 정리"),
    "settings": ("views/settings.py", "설정"),
    "write": ("views/write.py", "회사 맞춤 작성"),
}


def _run(company: str) -> dict:
    return next((r for r in list_runs() if r.get("analysis", {}).get("company") == company), {})


@dataclass
class Step:
    id: str
    page: str
    title: str
    how: str
    check: Callable[[], bool] | None = None  # None이면 '했어요' 버튼으로 넘긴다
    ai: str = ""                            # AI를 부르는 단계면 호출 수 안내


STEPS = [
    Step("look_cards", "profile", "가상 인물의 경험 카드 둘러보기",
         "아래 **경험 카드**를 하나 펼쳐 보세요. 경험이 상황·과제·행동·결과·수치로 나뉘어 있어요. "
         "AI는 여기 적힌 사실만 글에 쓸 수 있어요."),
    Step("upload", "profile", "가상 이력서를 올려 글자 뽑기",
         "이 안내 상자의 **⬇ 가상 이력서 받기**로 파일을 받은 뒤, **자료 올리기**에 끌어다 놓고 **텍스트 추출**을 누르세요. "
         "실제로 쓸 때는 내 이력서(PDF·DOCX·HWP)를 올리면 돼요.",
         lambda: bool(load_profile().raw_documents)),
    Step("extract", "profile", "AI로 경험 카드 만들기",
         "**✨ AI로 경험 카드 만들기**를 누르세요. 올린 이력서를 경험 단위로 나눠 카드를 만들고, "
         "더 물어볼 것을 **확인 질문**으로 보여 줘요. 이미 있는 카드와 겹치는 건 🗑️로 지우고 **💾 전부 저장**을 누르세요.",
         lambda: len(load_profile().cards) > 6, ai="AI 1~2번"),
    Step("roles", "profile", "희망 세부 직무 고르기",
         "**기본 인적사항**을 펼쳐 **희망 세부 직무**에 `스마트팩토리(제조사 DX·IIoT)`를 추가하고 **💾 전부 저장**을 누르세요. "
         "공고 분석이 애매할 때 여기서 고른 직무를 기준으로 써요.",
         lambda: "smart_factory_dx" in load_profile().target_roles),
    Step("settings", "settings", "설정 둘러보기",
         "모델(작성·평가), **호출 예산**(오늘 사용량, 하루 상한), **검증 방식**을 확인해 보세요. "
         "설정은 체험 모드와 실제 모드가 같이 쓰니, 체험 중에는 바꾸지 말고 보기만 하세요."),
    Step("screen", "write", "새 공고를 넣고 적합도만 먼저 보기",
         "**붙여넣기** 탭 → **샘플 공고 넣기 · 사아테크 스마트팩토리**를 누르고, "
         "**적합도만 먼저 보기**를 켠 뒤 **▶ 시작**을 누르세요. 공고 분석과 적합도 점수만 보고 멈춰요.",
         lambda: bool(_run("사아테크")), ai="AI 1번"),
    Step("write_full", "write", "이어서 작성하기",
         "결과 목록의 **🔎 사아테크**를 펼쳐 적합도·강점·부족한 점을 보고 **이어서 작성**을 누르세요. "
         "회사 리서치 → 초안 → 검증 → 수정 → 맞춤 이력서 → 인사담당자 평가까지 한 번에 해요(30초 안팎).",
         lambda: _run("사아테크").get("status") == "done", ai="AI 약 6~8번"),
    Step("read_answer", "write", "최종 답변 읽고 직접 고치기",
         "사아테크 결과의 **최종 답변** 탭을 보세요. 맨 위 노란 경고는 경험 카드에 없을 수 있는 문장이에요. "
         "사실이 아닌 부분을 고친 뒤 **고친 답변 저장**을 누르세요.",
         lambda: any(h.get("label") == "직접 수정" for h in _run("사아테크").get("history", []))),
    Step("evidence", "write", "근거·검증 결과·수정 기록 보기",
         "**근거** 탭에서 문장마다 어떤 카드를 근거로 썼는지, **검증 결과** 탭에서 무엇이 걸렸는지, "
         "**수정 기록** 탭에서 고치기 전후를 보세요. 마음에 안 들면 **이걸로 되돌리기**로 이전 버전으로 돌아갈 수 있어요.",
         lambda: any(h.get("label", "").startswith("되돌림") for r in list_runs() for h in r.get("history", []))),
    Step("answer_q", "write", "확인 질문에 답해서 카드 채우기",
         "**최종 답변** 탭 아래 **확인 질문**에 답을 적고 **카드에 저장**을 누르세요. "
         "다음 공고부터 그 사실을 글에 쓸 수 있어서 답변이 길고 구체적으로 바뀌어요.",
         lambda: any("(추가 확인)" in c.action for c in load_profile().cards)),
    Step("resume_hr", "write", "맞춤 이력서·인사담당자 평가 보기",
         "**이력서** 탭에서 이 공고에 맞게 순서를 바꾼 이력서를, **인사담당자** 탭에서 항목별 점수·지적 사항·면접 예상 질문을, "
         "**회사·공고** 탭에서 직무 판단과 회사 리서치를 확인하세요."),
    Step("approve", "write", "확인 대기 중인 공고 승인하기",
         "**✋ 다라소프트**를 펼치세요. '회차마다 확인' 설정으로 검증 뒤에 멈춘 상태예요. "
         "검증 결과를 보고 **승인하고 계속**을 누르면 수정·이력서·평가를 이어서 해요.",
         lambda: _run("다라소프트").get("status") == "done", ai="AI 약 3~4번"),
    Step("export", "write", "DOCX·PDF로 내보내기",
         "**✅ 가나장비** 결과를 펼쳐 **내보내기** 탭에서 **⬇ DOCX**, **⬇ PDF**를 받아 열어 보세요."),
    Step("site_fill", "write", "채용 사이트 입력칸 채우기",
         "**✅ 가나장비** 결과의 **내보내기** 탭에서 **Edge로 열어서 채우기**를 누르세요. 가짜 지원서 주소가 미리 들어가 있어요(가나장비 문항으로 만든 페이지). "
         "Edge 창에서 문항마다 답변이 채워진 것을 확인하세요. 제출·임시저장 버튼은 앱이 누르지 않아요.",
         lambda: any((DEMO / "runs" / r["id"] / "site_fill.json").exists() for r in list_runs())),
    Step("status", "write", "지원 상태 바꾸기",
         "사아테크 결과의 상태 선택칸을 **제출**로 바꾸세요. 위쪽 숫자 타일의 '제출'이 늘어나요.",
         lambda: _run("사아테크").get("apply_status") == "제출"),
    Step("finish", "home", "체험 끝내고 실제로 쓰기",
         "처음 화면에서 **체험 끝내기**를 누르면 내 실제 데이터로 돌아가요. "
         "실제로 쓸 때도 순서는 같아요: 내 경험 정리 → 공고 넣기 → 결과 확인·수정 → 내보내기·사이트 입력."),
]


def _load() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"done": []}


def _save(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def progress() -> tuple[list[str], Step | None]:
    """완료한 단계 id 목록과 지금 할 단계. 자동 확인 가능한 단계는 여기서 체크한다."""
    state = _load()
    done = set(state["done"])
    for s in STEPS:
        if s.id not in done and s.check:
            try:
                if s.check():
                    done.add(s.id)
            except Exception:
                pass
    if done != set(state["done"]):
        _save({"done": sorted(done)})
    current = next((s for s in STEPS if s.id not in done), None)
    return sorted(done), current


def mark_done(step_id: str) -> None:
    state = _load()
    if step_id not in state["done"]:
        state["done"].append(step_id)
    _save(state)

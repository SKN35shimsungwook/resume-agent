"""체험 모드용 더미 데이터 (가상 인물 '김예시', 가상 회사 3곳).

엑셀 자동화 도구의 '샘플로 체험하기'처럼, AI를 한 번도 부르지 않고도 모든 화면을 눌러 볼 수 있게
결과를 미리 만들어 data_demo/에 넣는다. '이어서 하기'·'승인하고 계속'·'시작'을 누르면 그때는
실제 AI를 부른다(무료 한도를 쓴다).

결과 상태별로 하나씩 준비한다.
- 가나장비(CS 엔지니어): 완료 — 근거·수정 기록·되돌리기·검증·이력서·인사담당자·내보내기·사이트 입력까지
- 다라소프트(프리세일즈): 확인 대기 — '회차마다 확인'으로 검증 뒤에 멈춘 상태
- 마바전기(설비보전): 적합도만 본 상태 — 이력서만 받는 공고
- 가나장비 정밀 모드 사본: 일시 멈춤 — 한도·장애로 멈춘 상태
"""
import json
import shutil
from pathlib import Path

from .paths import DEMO, ROOT
from .pipeline import run_id

EXAMPLES = ROOT / "examples" / "demo"


def posting(name: str) -> str:
    return (EXAMPLES / name).read_text(encoding="utf-8")


def _s(text, *ids):
    return {"text": text, "card_ids": list(ids)}


def _answer(question, *sentences):
    return {"question": question, "text": " ".join(s["text"] for s in sentences), "sentences": list(sentences)}


Q_FSE = ["가나장비와 CS 엔지니어 직무에 지원한 이유를 구체적으로 작성해 주세요.",
         "예상하지 못한 문제를 끝까지 해결한 경험을 작성해 주세요.",
         "고객 또는 동료와 의견이 달랐던 상황에서 어떻게 해결했는지 작성해 주세요."]


def _fse_done() -> dict:
    draft = [
        _answer(Q_FSE[0],
                _s("자동화 라인 시운전 현장에서 센서 120개를 하나씩 점검하며, 장비가 고객 공장에서 처음 돌아가는 순간을 책임지는 일에 끌렸습니다.", "ex_setup"),
                _s("가나장비는 후공정 자동화 장비를 국내외 고객사 공장에 설치하고 안정화하는 회사이고, CS 엔지니어는 그 현장의 첫 담당자입니다.", "posting"),
                _s("저는 귀사에 꼭 필요한 열정을 가진 인재로 최선을 다하겠습니다.")),
        _answer(Q_FSE[1],
                _s("시운전 일정이 2주 앞당겨졌을 때 센서 입출력 점검표를 맡았습니다.", "ex_setup"),
                _s("선임과 함께 센서 입출력을 하나씩 점검하고 점검표를 엑셀로 정리해 매일 공유했습니다.", "ex_setup"),
                _s("그 결과 불량률을 30% 줄였습니다.", "ex_setup")),
        _answer(Q_FSE[2],
                _s("고객센터에서 배송 지연 문의가 몰렸을 때 상담원마다 안내가 달랐습니다.", "ex_cs"),
                _s("자주 오는 문의를 정리해 답변 예시 20개를 만들어 팀에 공유했습니다.", "ex_cs")),
    ]
    revised = json.loads(json.dumps(draft, ensure_ascii=False))
    revised[0] = _answer(Q_FSE[0],
                         _s("자동화 라인 시운전 현장에서 센서 120개를 하나씩 점검하며, 장비가 고객 공장에서 처음 돌아가는 순간을 책임지는 일에 끌렸습니다.", "ex_setup"),
                         _s("가나장비는 후공정 자동화 장비를 국내외 고객사 공장에 설치하고 안정화하는 회사이고, CS 엔지니어는 그 현장의 첫 담당자입니다.", "posting"),
                         _s("시운전 때 만든 점검표처럼 기록을 남기는 습관으로, 고객사 장비의 셋업과 PM 이력을 다음 엔지니어가 이어받을 수 있게 정리하겠습니다.", "ex_setup", "posting"))
    revised[1] = _answer(Q_FSE[1],
                         _s("시운전 일정이 2주 앞당겨졌을 때 센서 입출력 점검표를 맡았습니다.", "ex_setup"),
                         _s("선임과 함께 센서 입출력을 하나씩 점검하고 점검표를 엑셀로 정리해 매일 공유했습니다.", "ex_setup"),
                         _s("점검표는 시운전 회의 자료로 쓰였고, 기록을 남겨야 다음 사람이 이어받을 수 있다는 것을 배웠습니다.", "ex_setup"))
    changes = [
        {"rule": "WR-3", "before": "저는 귀사에 꼭 필요한 열정을 가진 인재로 최선을 다하겠습니다.",
         "after": "시운전 때 만든 점검표처럼 기록을 남기는 습관으로, 고객사 장비의 셋업과 PM 이력을 다음 엔지니어가 이어받을 수 있게 정리하겠습니다.",
         "why": "근거 없는 다짐을 카드의 실제 행동과 공고 업무로 바꿨다."},
        {"rule": "FA-2", "before": "그 결과 불량률을 30% 줄였습니다.",
         "after": "점검표는 시운전 회의 자료로 쓰였고, 기록을 남겨야 다음 사람이 이어받을 수 있다는 것을 배웠습니다.",
         "why": "'30%'는 경험 카드에 없는 숫자라 지우고, 카드에 있는 결과로 바꿨다."},
    ]
    analysis = {
        "company": "가나장비", "position": "CS 엔지니어 (신입)", "subrole": "fse_cs",
        "subrole_why": "고객사 공장에서 장비 셋업·시운전·트러블슈팅을 하는 장비사 CS 직무다.",
        "format": "multi_questions", "must": ["전문학사 이상", "전기·전자·기계·제어 전공", "출장 가능", "운전면허 1종보통"],
        "nice": ["PLC·HMI", "로봇 티칭", "해외 현장", "영어", "전기기능사"],
        "keywords": ["Set-up", "시운전", "트러블슈팅", "PM", "고객사 대응"], "talent": ["끝까지 원인을 찾는 사람", "고객의 말을 먼저 듣는 사람"],
        "duties": ["장비 설치·시운전·안정화", "알람·에러 트러블슈팅", "고객사 엔지니어 대응"],
        "questions": [{"question": Q_FSE[0], "limit": 700, "intent": "회사·직무 이해와 지원 근거"},
                      {"question": Q_FSE[1], "limit": 800, "intent": "끈기와 문제 해결 과정"},
                      {"question": Q_FSE[2], "limit": 600, "intent": "고객 소통과 조율"}],
        "hard_filters": [{"item": "운전면허 1종보통", "required": True}], "homepage": "",
        "fit": {"score": 78, "strengths": ["시운전 현장 경험", "고객 응대 1년"], "gaps": ["해외 현장·영어 경험 없음"],
                "why": "셋업 현장과 고객 응대를 둘 다 해 봤지만 해외 경험은 없다."},
    }
    return {
        "id": run_id(posting("posting_fse.md")), "created": "2026-11-03T10:00:00", "posting": posting("posting_fse.md"),
        "mode": "normal", "status": "done", "apply_status": "제출",
        "done": ["analyze", "research", "draft", "checks", "verify_a", "verify_b", "revise", "resume", "hr", "revise_2"],
        "analysis": analysis,
        "research": {"summary": "(체험용 가상 회사) 후공정 자동화 장비를 만들어 국내외 고객 공장에 공급한다.",
                     "business": ["후공정 자동화 장비"], "products": [], "recent": [],
                     "talent": ["끝까지 원인을 찾는 사람"],
                     "role_challenges": [{"challenge": "고객 공장에서 장비를 일정 안에 안정화하고 기록을 남기는 것", "source": "공고"}],
                     "sources": ["공고 원문"]},
        "draft": {"assignments": [{"question": Q_FSE[0], "card_ids": ["ex_setup"], "why": "셋업 현장 경험"},
                                  {"question": Q_FSE[1], "card_ids": ["ex_setup"], "why": "일정 압박 속 점검"},
                                  {"question": Q_FSE[2], "card_ids": ["ex_cs"], "why": "고객 응대"}],
                  "answers": draft,
                  "missing_questions": [{"card_id": "ex_setup", "question": "시운전 중에 직접 원인을 찾은 고장·알람이 있었나요? 있었다면 어떤 순서로 점검했나요?"},
                                        {"card_id": "ex_cs", "question": "답변 예시를 공유한 뒤 문의 처리 시간이나 재문의가 줄었나요?"}]},
        "code_violations": [
            {"rule": "FA-2", "question": Q_FSE[1], "sentence": "30", "why": "숫자 '30'이 경험 카드에 없다. 지어낸 수치일 수 있다."},
            {"rule": "WR-3", "question": Q_FSE[0], "sentence": "최선을 다하겠습니다", "why": "근거 없는 자기평가·상투 표현이다.", "fix_hint": "행동과 결과로 바꿔 쓴다."},
            {"rule": "MA-1", "question": f"{Q_FSE[0]} / {Q_FSE[1]}", "sentence": "ex_setup", "why": "카드 'ex_setup'가 여러 문항의 주 경험으로 겹친다."},
            {"rule": "FC-4", "question": Q_FSE[2], "sentence": "", "why": "88자로 제한 600자의 70%에 못 미친다.", "fix_hint": "공고와 연결하는 문장으로 채운다."},
        ],
        "verify_a": {"score": 70, "violations": [{"rule": "FA-1", "question": Q_FSE[1], "sentence": "그 결과 불량률을 30% 줄였습니다.",
                                                   "why": "카드에는 점검표가 회의 자료로 쓰였다는 결과만 있다.", "fix_hint": "카드의 결과로 바꾼다."}]},
        "verify_b": {"score": 65, "violations": [{"rule": "CF-1", "question": Q_FSE[0], "sentence": "저는 귀사에 꼭 필요한 열정을 가진 인재로 최선을 다하겠습니다.",
                                                   "why": "회사명을 바꿔도 성립하는 문장이다.", "fix_hint": "가나장비의 업무와 연결한다."},
                                                  {"rule": "WR-9", "question": Q_FSE[2], "sentence": "", "why": "의견이 달랐던 상대와 어떻게 합의했는지가 없다."}]},
        "revisions": [{"after": "revise", "changes": changes}],
        "final": {"answers": revised, "changes": changes},
        "history": [{"label": "초안", "at": "2026-11-03T10:01:00", "answers": draft},
                    {"label": "revise", "at": "2026-11-03T10:06:00", "answers": revised}],
        "resume": {"summary": "자동화 라인 시운전 보조와 고객센터 상담을 해 본, 현장과 고객을 함께 아는 신입",
                   "sections": [{"title": "경력", "items": [_s("가상 자동화 주식회사 · 시운전 보조 (2025.03~2025.05) — 센서 120개 입출력 점검, 점검표 작성·공유", "ex_setup"),
                                                           _s("가상 커머스 · 고객센터 상담 (2023, 1년) — 주문·배송 문의 응대, 답변 예시 20개 작성", "ex_cs")]},
                                {"title": "프로젝트", "items": [_s("공정 불량 대시보드 (2026.08) — Python·Streamlit, 동기 5명 시연 후 2회 수정", "ex_dash")]},
                                {"title": "학력·면허", "items": [_s("가나폴리텍 자동화과 전문학사 (2025.02)", "ex_school"),
                                                              _s("운전면허 1종보통", "ex_license")]}]},
        "hr": {"scores": [{"item": "직무 연관 현장 경험", "max": 25, "score": 17, "evidence": "시운전 보조 3개월, 센서 점검"},
                          {"item": "트러블슈팅 서술 구체성", "max": 20, "score": 9, "evidence": "직접 원인을 찾은 장면이 없다"},
                          {"item": "기본 요건", "max": 15, "score": 14, "evidence": "전공·1종보통 충족"},
                          {"item": "협업·고객 소통", "max": 15, "score": 11, "evidence": "고객센터 1년"},
                          {"item": "자격증", "max": 5, "score": 2, "evidence": "없음"},
                          {"item": "안전 의식", "max": 5, "score": 2, "evidence": "언급 없음"},
                          {"item": "정확성", "max": 5, "score": 5, "evidence": "오류 없음"},
                          {"item": "어학", "max": 10, "score": 3, "evidence": "공인 점수 없음"}],
               "total": 63, "verdict": "보류",
               "reasons": ["트러블슈팅 장면이 '점검했다'에서 끝나 원인 판단이 보이지 않는다.", "갈등 문항에 상대와의 합의 과정이 없다."],
               "violations": [], "interview_questions": ["시운전 중 가장 오래 걸린 점검은 무엇이었고, 왜 오래 걸렸나요?",
                                                        "고객사 엔지니어가 장비 탓을 할 때 어떻게 대응하겠습니까?"]},
    }


Q_PRE = ["다라소프트 프리세일즈 엔지니어에 지원한 이유와 입사 후 하고 싶은 일을 작성해 주세요.",
         "기술적인 내용을 기술을 잘 모르는 사람에게 설명해 이해시킨 경험을 작성해 주세요."]


def _presales_waiting() -> dict:
    draft = [
        _answer(Q_PRE[0],
                _s("실습실의 종이 불량 기록을 대시보드로 바꿔 동기 5명에게 시연했을 때, 기술보다 '그래서 뭐가 편해지는지'를 먼저 물어 온다는 걸 알았습니다.", "ex_dash"),
                _s("다라소프트가 중소 제조 공장에 생산 현황 대시보드를 제공한다는 점에서, 현장 사람에게 설명하는 일을 직무로 하고 싶어 지원했습니다.", "posting")),
        _answer(Q_PRE[1],
                _s("팀 프로젝트에서 팀원마다 결과를 보는 기준이 달라 평가 항목 5개로 된 표를 만들어 합의했습니다.", "ex_team"),
                _s("최종 발표를 맡아 세 가지 방식 중 하나를 고른 이유를 표로 설명했습니다.", "ex_team")),
    ]
    return {
        "id": run_id(posting("posting_presales.md")), "created": "2026-11-03T10:20:00", "posting": posting("posting_presales.md"),
        "mode": "normal", "status": "waiting", "waiting_at": "verify_b", "apply_status": "준비",
        "done": ["analyze", "research", "draft", "checks", "verify_a", "verify_b"],
        "analysis": {"company": "다라소프트", "position": "프리세일즈 엔지니어 (신입)", "subrole": "presales",
                     "subrole_why": "데모·PoC·기술 Q&A가 중심인 직무다.", "format": "multi_questions",
                     "must": ["운전면허"], "nice": ["제조 현장 경험", "고객 응대", "Python·시각화"],
                     "keywords": ["데모", "PoC", "제안서", "요구사항"], "talent": [], "duties": ["데모 시연", "PoC 준비", "기술 Q&A"],
                     "questions": [{"question": Q_PRE[0], "limit": 800, "intent": "지원 이유와 입사 후 계획"},
                                   {"question": Q_PRE[1], "limit": 700, "intent": "설명력"}],
                     "hard_filters": [{"item": "운전면허", "required": True}], "homepage": "",
                     "fit": {"score": 82, "strengths": ["시연 경험", "고객 응대", "제조 현장"], "gaps": ["영업 동행 경험 없음"], "why": "우대사항 세 가지를 모두 경험했다."}},
        "research": {"summary": "(체험용 가상 회사) 중소 제조 공장용 생산 현황 대시보드·AI 품질 점검 SaaS.",
                     "role_challenges": [{"challenge": "현장 담당자가 이해하는 말로 데모를 보여 주는 것", "source": "공고"}], "sources": ["공고 원문"]},
        "draft": {"answers": draft, "missing_questions": [{"card_id": "ex_dash", "question": "시연 뒤 받은 의견 중 가장 크게 바꾼 화면은 무엇이었나요?"}]},
        "code_violations": [{"rule": "FC-4", "question": Q_PRE[1], "sentence": "", "why": "96자로 제한 700자의 70%에 못 미친다."}],
        "verify_a": {"score": 95, "violations": []},
        "verify_b": {"score": 72, "violations": [{"rule": "WR-4", "question": Q_PRE[1], "sentence": "", "why": "상대가 무엇을 몰랐고 어떻게 이해했는지가 없다."}]},
        "history": [{"label": "초안", "at": "2026-11-03T10:21:00", "answers": draft}],
    }


def _screened() -> dict:
    return {
        "id": run_id(posting("posting_resume_only.md")), "created": "2026-11-03T10:30:00", "posting": posting("posting_resume_only.md"),
        "mode": "normal", "status": "screened", "apply_status": "준비", "done": ["analyze"],
        "analysis": {"company": "마바전기", "position": "설비보전 사원", "subrole": "factory_electrical",
                     "subrole_why": "수배전·전동기 점검과 교대 근무가 있는 공장 전기 보전 직무다.", "format": "resume_only",
                     "must": ["운전면허"], "nice": ["전기 전공", "전기기능사"], "keywords": ["수배전", "전동기", "인버터", "2교대"],
                     "talent": [], "duties": ["설비 점검·보전", "고장 1차 대응"], "questions": [],
                     "hard_filters": [{"item": "전기기능사", "required": False}], "homepage": "",
                     "fit": {"score": 64, "strengths": ["PLC·시퀀스 전공"], "gaps": ["수배전 실무 없음", "전기기능사 없음"],
                             "why": "전공은 맞지만 보전 실무 경험이 적다."}},
    }


def _paused() -> dict:
    text = posting("posting_fse.md") + "\n\n(정밀 모드 체험용 사본)"
    base = _fse_done()
    return {
        "id": run_id(text), "created": "2026-11-03T10:40:00", "posting": text, "mode": "precise",
        "status": "paused", "apply_status": "준비",
        "error": "모든 모델 호출에 실패했습니다: gemma-4-26b-a4b-it 호출 실패(504): DEADLINE_EXCEEDED (체험용 예시 — '이어서 하기'를 누르면 실제 AI로 이어서 해요)",
        "done": ["analyze", "research", "draft", "checks", "v1_fact", "revise_v1_fact"],
        "analysis": base["analysis"], "research": base["research"], "draft": base["draft"],
        "code_violations": base["code_violations"], "v1_fact": base["verify_a"],
        "history": base["history"][:1],
    }


ANGLES = """# (체험용) 이야기 각도

<!-- group: common -->
## 공통
- 한 줄 서사: 설비 현장과 고객 응대를 둘 다 해 본 신입
- 쓰지 않는 표현: 카드에 없는 성과 수치

<!-- group: field_equipment -->
## 현장 설비
- 시운전 보조 3개월을 '현장 경험이 있는 신입'의 근거로

<!-- group: tech_sales -->
## 기술영업
- 대시보드 시연과 고객센터 상담을 '설명력'의 근거로
"""

REFERENCE = """(체험용 참고 글 — 표절·획일성 점검이 어떻게 걸리는지 보여 주는 가짜 예시 자소서)
자동화 라인 시운전 현장에서 센서 120개를 하나씩 점검하며, 장비가 고객 공장에서 처음 돌아가는 순간을 책임지는 일에 끌렸습니다.
저는 귀사에 꼭 필요한 열정을 가진 인재로 최선을 다하겠습니다.
"""


def build(reset: bool = False) -> Path:
    """data_demo/를 만든다. reset=True면 지우고 처음부터."""
    if reset and DEMO.exists():
        shutil.rmtree(DEMO)
    DEMO.mkdir(parents=True, exist_ok=True)
    shutil.copy(EXAMPLES / "profile.json", DEMO / "profile.json")
    (DEMO / "angles.md").write_text(ANGLES, encoding="utf-8")
    (DEMO / "reference").mkdir(exist_ok=True)
    (DEMO / "reference" / "예시_자소서.txt").write_text(REFERENCE, encoding="utf-8")
    fse = _fse_done()
    (DEMO / "base_resumes").mkdir(exist_ok=True)
    (DEMO / "base_resumes" / "fse_cs.json").write_text(json.dumps(fse["resume"], ensure_ascii=False, indent=2), encoding="utf-8")
    (DEMO / "research_cache").mkdir(exist_ok=True)
    (DEMO / "research_cache" / "가나장비.json").write_text(json.dumps(fse["research"], ensure_ascii=False, indent=2), encoding="utf-8")
    for state in (fse, _presales_waiting(), _screened(), _paused()):
        d = DEMO / "runs" / state["id"]
        d.mkdir(parents=True, exist_ok=True)
        state["updated"] = state["created"]
        (d / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return DEMO


def demo_postings() -> dict[str, str]:
    return {"가나장비 CS 엔지니어 (문항 3개)": posting("posting_fse.md"),
            "다라소프트 프리세일즈 (문항 2개)": posting("posting_presales.md"),
            "마바전기 설비보전 (이력서만)": posting("posting_resume_only.md")}


def apply_form_url() -> str:
    return (EXAMPLES / "apply_form.html").as_uri()

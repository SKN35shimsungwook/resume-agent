"""가짜 AI로 파이프라인과 사실 검사를 시험한다 (API 호출 0번).

python -m pytest tests -q
"""
import json

import pytest

from core import pipeline, research
from core.checks import grounding_violations, length_violations, sentence_violations
from core.profile import ExperienceCard, Profile, save_profile

POSTING = "가나장비 CS 엔지니어 채용\n자기소개서 문항 1. 지원 동기를 작성해 주세요 (최대 300자)"
CARDS = [
    ExperienceCard(title="인도 폭스콘 설비 셋업", kind="경력", id="c1", action="PC 제어로 로봇 티칭과 센서 점검을 했다.",
                   metrics="31일 중 30일 현장 투입"),
    ExperienceCard(title="LangChain 마이그레이션 챗봇", kind="프로젝트", id="c2", action="평가 기준과 시험 세트 30개를 만들었다.",
                   result="통과율 0%→57%"),
]
GOOD = "인도 폭스콘 현장에서 31일 중 30일 투입되어 PC 제어로 로봇 티칭과 센서 점검을 했습니다. " * 3


def answer(text, sentences):
    return {"answers": [{"question": "지원 동기를 작성해 주세요", "text": text, "sentences": sentences}]}


class FakeLLM:
    """단계 이름(step)마다 정해 둔 답을 돌려준다. fail_once에 든 단계는 첫 호출에서 한 번 실패한다."""

    def __init__(self, draft=None, hr_total=80, fail_once=()):
        self.calls, self.fail_once = [], set(fail_once)
        self.draft = draft or answer(GOOD, [{"text": GOOD, "card_ids": ["c1"]}])
        self.hr_total = hr_total

    def __call__(self, role, system, prompt, config=None, temperature=None, step=""):
        self.calls.append(step)
        if step in self.fail_once:
            self.fail_once.discard(step)
            raise RuntimeError("모든 모델 호출에 실패했습니다: 503")
        if step == "analyze":
            return {"company": "가나장비", "position": "CS 엔지니어", "subrole": "fse_cs", "format": "multi_questions",
                    "questions": [{"question": "지원 동기를 작성해 주세요", "limit": 300}], "fit": {"score": 80}}
        if step == "research":
            return {"summary": "장비 회사", "sources": []}
        if step == "draft" or step.startswith("revise"):
            return json.loads(json.dumps(self.draft)) | {"changes": []}
        if step == "verify_a":
            return {"claims": [{"question": "q", "sentence": "s", "claim": "c", "quote": "PC 제어로 로봇 티칭과 센서 점검을 했다."}]}
        if step == "hr":
            reasons = ["트러블슈팅 순서가 드러나지 않음"] if self.hr_total < 70 else []
            return {"total": self.hr_total, "verdict": "합격", "reasons": reasons, "violations": []}
        return {"score": 90, "violations": []}


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("RA_WORKSPACE", str(tmp_path))
    save_profile(Profile(name="시험", target_roles=["fse_cs"], cards=list(CARDS)))
    return tmp_path


def use(monkeypatch, fake):
    monkeypatch.setattr(pipeline, "ask_json", fake)
    monkeypatch.setattr(research, "ask_json", fake)
    monkeypatch.setattr(pipeline, "load_config", lambda: {"research": True, "confirm_each_round": False})


def test_full_run_goes_through_every_step_in_order(ws, monkeypatch):
    fake = FakeLLM()
    use(monkeypatch, fake)
    state = pipeline.run(POSTING)
    assert state["status"] == "done"
    assert state["done"] == pipeline.steps_for("normal")
    assert state["schema"] == pipeline.SCHEMA_VERSION
    assert state["fact_report"]["no_card"] == 0
    assert "revise_2" not in fake.calls  # 80점이면 다시 고치지 않는다


def test_low_hr_score_triggers_second_revision(ws, monkeypatch):
    fake = FakeLLM(hr_total=50)
    use(monkeypatch, fake)
    pipeline.run(POSTING)
    assert "revise_2" in fake.calls


def test_paused_run_resumes_without_repeating_finished_steps(ws, monkeypatch):
    fake = FakeLLM(fail_once={"verify_b"})
    use(monkeypatch, fake)
    first = pipeline.run(POSTING)
    assert first["status"] == "paused"
    second = pipeline.run(POSTING)
    assert second["status"] == "done"
    assert fake.calls.count("analyze") == 1 and fake.calls.count("draft") == 1


def test_confirm_each_round_waits_at_gate(ws, monkeypatch):
    fake = FakeLLM()
    use(monkeypatch, fake)
    state = pipeline.run(POSTING, config={"research": True, "confirm_each_round": True})
    assert state["status"] == "waiting" and state["waiting_at"] == "verify_b"


def test_sentence_without_evidence_is_blocked_and_sent_to_revision(ws, monkeypatch):
    made_up = "저는 3년간 장비 회사에서 팀장으로 일하며 고객사를 관리했습니다."
    fake = FakeLLM(draft=answer(GOOD + made_up, [{"text": GOOD, "card_ids": ["c1"]}, {"text": made_up, "card_ids": []}]))
    use(monkeypatch, fake)
    state = pipeline.run(POSTING)
    rules = [v["rule"] for v in state["code_violations"]]
    assert "FA-3" in rules  # 근거 카드 없는 사실 문장
    assert "revise" in fake.calls  # 위반이 수정 단계로 넘어간다


def test_number_must_come_from_the_cited_card():
    s = "마이그레이션 챗봇으로 31일 만에 통과율을 높였습니다."  # 31은 c1에만 있는 숫자
    found = sentence_violations(answer(s, [{"text": s, "card_ids": ["c2"]}])["answers"], CARDS, POSTING)
    assert any(v["rule"] == "FA-2" and "31" in v["why"] for v in found)
    ok = "마이그레이션 챗봇의 통과율을 0%에서 57%로 높였습니다."
    assert not [v for v in sentence_violations(answer(ok, [{"text": ok, "card_ids": ["c2"]}])["answers"], CARDS, POSTING)
                if v["rule"] == "FA-2"]


def test_pledge_sentence_needs_no_card():
    s = "입사 후에는 고객사 현장에서 장비를 빠르게 안정화하는 엔지니어가 되겠습니다."
    assert not sentence_violations(answer(s, [{"text": s, "card_ids": []}])["answers"], CARDS, POSTING)


def test_evidence_list_must_cover_the_answer_text():
    found = sentence_violations(answer(GOOD * 3, [{"text": GOOD[:30], "card_ids": ["c1"]}])["answers"], CARDS, POSTING)
    assert any(v["rule"] == "FA-4" for v in found)


def test_quote_not_in_source_is_a_violation():
    claims = [{"question": "q", "sentence": "s", "claim": "c", "quote": "설비 가동률을 20% 올렸다"}]
    found, score = grounding_violations(claims, "PC 제어로 로봇 티칭과 센서 점검을 했다.")
    assert found and score < 100


def test_length_limit_is_checked_by_code():
    analysis = {"questions": [{"question": "지원 동기를 작성해 주세요", "limit": 300}]}
    assert any("넘었다" in v["why"] for v in length_violations(analysis, answer("가" * 320, [])["answers"]))
    assert any("못 미친다" in v["why"] for v in length_violations(analysis, answer("가" * 100, [])["answers"]))


def test_self_view_sentence_needs_no_card():
    for s in ["기술의 가치를 고객의 언어로 전달하는 것이 저의 직업관입니다.",
              "저의 차별화된 역량은 평가 기준을 설계하고 문제를 진단하는 기획력입니다.",
              "저의 가장 큰 장점은 현장에서 끝까지 임무를 완수하는 끈기입니다."]:
        assert not sentence_violations(answer(s, [{"text": s, "card_ids": []}])["answers"], CARDS, POSTING), s


def test_made_up_habit_is_still_blocked():
    s = "이를 보완하기 위해 현재는 이상 징후가 감지되면 즉시 선임에게 공유하는 습관을 들이고 있습니다."
    found = sentence_violations(answer(s, [{"text": s, "card_ids": []}])["answers"], CARDS, POSTING)
    assert any(v["rule"] == "FA-3" for v in found)


def test_lack_of_experience_as_weakness_is_flagged():
    s = "보완해야 할 약점은 수주 실적을 낸 정규 경력이 아직 부족하다는 점입니다."
    found = sentence_violations(answer(s, [{"text": s, "card_ids": []}])["answers"], CARDS, POSTING)
    assert any(v["rule"] == "WR-6" for v in found)
    ok = "제 단점은 혼자 해결하려다 공유가 늦어지는 점입니다."
    assert not [v for v in sentence_violations(answer(ok, [{"text": ok, "card_ids": []}])["answers"], CARDS, POSTING)
                if v["rule"] == "WR-6"]

"""에이전트별 시스템 프롬프트를 조립한다.

모든 프롬프트는 같은 틀을 따른다 (docs/agent-design.md 3장):
역할 → 금지 규칙 → 공통 작성 원칙 → 직무군 기준 → (작성 단계만) 내 이야기 각도 → 출력 형식.
세부 직무가 정해지면 "이 세부 직무 열/행을 기준으로 삼으라"고 지시한다.
"""
from .knowledge import angle, group_of, group_part, principles

BASE_RULES = """\
- 경험 카드([id]가 붙은 사실)에 없는 사실·수치·기간·직함은 절대 만들지 않는다.
- 다른 사람의 예시·합격 자소서 문장, 공고·홈페이지 문구를 그대로 가져오지 않는다.
- 아래 기준표와 실제 공고가 다르면 **실제 공고가 우선**이다.
- 채점표 배점은 추정치다. 절대 점수가 아니라 항목 간 우선순위로 쓴다.
- 반드시 JSON으로만 답한다."""

ROLES = {
    "matcher": "너는 채용 서류 전략가다. 지원자의 경험 카드와 공고를 비교해 문항마다 쓸 경험을 고르고, 부족한 정보와 하드 필터를 찾는다.",
    "writer": "너는 지원자 본인의 목소리로 쓰는 서류 작가다. 경험 카드의 사실만으로, 이 직무군이 인정하는 증거 문법에 맞춰 쓴다.",
    "resume": "너는 이력서 편집자다. 같은 경험 카드를 이 세부 직무에 맞는 순서와 강조로 재배치한다. 사실은 바꾸지 않는다.",
    "judge": "너는 이 직무군에서 10년 넘게 서류를 본 인사담당자다. 칭찬보다 탈락 사유를 먼저 찾고, 채점표 항목별로 근거를 들어 채점한다.",
}

# 에이전트마다 넣을 공통 원칙 단계와 직무군 부분
PLAN = {
    "matcher": (("analyze", "match"), ("overview", "hard_filters", "matcher")),
    "writer": (("write", "fact"), ("overview", "writer")),
    "resume": (("resume", "fact"), ("overview", "resume")),
    "judge": (("company_fit", "final_check"), ("overview", "hard_filters", "judge", "writer")),
}

OUTPUT = {
    "matcher": '{"hard_filter_checks": [{"item": "", "status": "충족|미충족|확인 필요", "note": ""}], '
               '"assignments": [{"question": "", "card_ids": [], "why": ""}], '
               '"missing_questions": [{"card_id": "", "question": ""}]}',
    "writer": '{"answers": [{"question": "", "text": "", "sentences": [{"text": "", "card_ids": []}]}]}',
    "resume": '{"summary": "", "sections": [{"title": "", "items": [{"text": "", "card_ids": []}]}]}',
    "judge": '{"scores": [{"item": "", "max": 0, "score": 0, "evidence": ""}], "total": 0, '
             '"verdict": "합격|보류|탈락", "reasons": [], "violations": [{"rule": "", "sentence": "", "why": ""}], '
             '"interview_questions": []}',
}


def build_system_prompt(agent: str, subrole: str) -> str:
    """agent: matcher | writer | resume | judge, subrole: knowledge/groups/README.md의 세부 직무 id"""
    group = group_of(subrole)
    stages, parts = PLAN[agent]
    blocks = [
        ROLES[agent],
        f"## 지켜야 할 규칙\n{BASE_RULES}",
        f"## 공통 작성 원칙\n{principles(*stages)}",
        f"## 직무군 기준 (세부 직무: `{subrole}`)\n"
        f"표에 세부 직무별 열·행이 있으면 `{subrole}`에 해당하는 것을 기준으로 삼는다.\n\n"
        f"{group_part(group, *parts)}",
    ]
    if agent in ("matcher", "writer", "resume"):
        my_angle = angle(group)
        if my_angle:
            blocks.append(f"## 지원자 이야기 각도 (본인이 정한 방향, 사실 확인용 아님)\n{my_angle}")
    blocks.append(f"## 출력 형식 (JSON)\n{OUTPUT[agent]}")
    return "\n\n".join(blocks)

"""에이전트별 시스템 프롬프트를 조립한다.

모든 프롬프트는 같은 틀을 따른다 (docs/agent-design.md 3장):
역할 → 금지 규칙 → 공통 작성 원칙 → 직무군 기준 → (작성 단계만) 내 이야기 각도 → 출력 형식.
세부 직무가 정해지면 "이 세부 직무 열/행을 기준으로 삼으라"고 지시한다.
"""
from .knowledge import GROUPS, SUBROLE_LABELS, angle, group_of, group_part, principles

BASE_RULES = """\
- 경험 카드([id]가 붙은 사실)에 없는 사실·수치·기간·직함은 절대 만들지 않는다.
- 직무군의 증거 문법(예: 증상→원인→점검 순서→조치→재발 방지)을 채우려고 **카드에 없는 세부 장면을 지어내지 않는다.**
  원인 진단, 점검 순서, 해결 결과, 공유·재발 방지처럼 카드에 적히지 않은 단계는 쓰지 말고 missing_questions로 지원자에게 묻는다.
  사실이 부족해 문법이 비면, 빈 채로 두는 것이 지어내는 것보다 낫다.
- 공고에 적힌 회사·직무 사실(사업, 업무, 인재상)은 지원동기·포부 문장의 근거로 쓸 수 있다. 이런 문장의 card_ids는 ["posting"]으로 단다.
- 답변 본문에 [보유 자격 사항: …] 같은 괄호 메모, 편집 메모, 설명문을 넣지 않는다. 자격·면허는 문항이 직접 물을 때만 쓴다.
- 문항마다 '분량 목표'를 지킨다. 제한이 있으면 제한의 80~100%, 제한이 없으면 600~800자(공백 포함)다. 제한을 넘기지 않는다.
  분량은 지어내서 채우지 말고, 카드의 행동·배운 점을 더 자세히 풀고 공고 업무·회사 리서치와 연결하는 문장으로 채운다.
- 다른 사람의 예시·합격 자소서 문장, 공고·홈페이지 문구를 그대로 가져오지 않는다.
- 아래 기준표와 실제 공고가 다르면 **실제 공고가 우선**이다.
- 채점표 배점은 추정치다. 절대 점수가 아니라 항목 간 우선순위로 쓴다.
- 하드 필터(자격증·면허·학력 등)를 못 채워도 **지원을 막지 않는다**. 지원자는 요건이 부족해도 지원한다.
- 서류에서 없는 자격·요건을 먼저 꺼내 약점을 강조하지 않는다. 가진 강점을 앞에 둔다.
  양식에 자격 칸이 있어 꼭 써야 할 때만 "취득 준비 중"처럼 짧게 쓰고, 보유한 것처럼 꾸미지는 않는다.
- 단, 문항이 약점·단점·보완할 점을 **직접 물으면 피하지 않고 답한다.** 직무에 치명적이지 않고 고칠 수 있는 성향·습관 수준의 약점 하나를 고르고,
  그것을 고치려고 한 행동(카드 사실)과 달라진 점을 함께 쓴다. 자격증·경력 부족을 약점으로 고르지 않는다.
- 문항 하나에 ①② 같은 소문항이 있으면 한 답변 안에서 소문항 순서대로 모두 답한다.
- 반드시 JSON으로만 답한다."""

ROLES = {
    "matcher": "너는 채용 서류 전략가다. 지원자의 경험 카드와 공고를 비교해 문항마다 쓸 경험을 고르고, 부족한 정보와 하드 필터를 찾는다.",
    "writer": "너는 지원자 본인의 목소리로 쓰는 서류 작가다. 경험 카드의 사실만으로, 이 직무군이 인정하는 증거 문법에 맞춰 쓴다.",
    "resume": "너는 이력서 편집자다. 같은 경험 카드를 이 세부 직무에 맞는 순서와 강조로 재배치한다. 사실은 바꾸지 않는다.",
    "judge": "너는 이 직무군에서 10년 넘게 서류를 본 인사담당자다. 칭찬보다 탈락 사유를 먼저 찾고, 채점표 항목별로 근거를 들어 채점한다.",
    # 일반 모드(docs/call-budget.md): 매칭과 작성을 한 번에, 검증 5관점을 A·B 두 번에 묶는다
    "drafter": "너는 채용 서류 전략가이자 지원자 본인의 목소리로 쓰는 작가다. 문항마다 쓸 경험 카드를 고르고(문항끼리 주 경험이 겹치지 않게), 그 카드의 사실만으로 답변을 쓴다.",
    "verify_a": "너는 서류 사실 검증관이다. 답변을 문장 단위로 보고, 각 문장을 더 쪼갤 수 없는 사실 주장(claim)으로 나눈다. "
                "주장마다 그 근거가 되는 경험 카드 또는 공고 원문의 문구를 **한 글자도 바꾸지 말고 그대로 복사**해 quote에 넣는다. "
                "근거 문구가 없으면 quote는 빈 문자열로 둔다. 원인 판단·점검 순서·결과·성과·감정 묘사도 모두 주장이다. "
                "**동사 하나당 주장 하나**로 나눈다. 예: '예비 PC로 업데이트해 설비를 정상 가동시켰다'는 '예비 PC로 업데이트했다'와 '설비를 정상 가동시켰다' 두 주장이다. "
                "다짐·포부(앞으로 ~하겠다)와 약점·성향에 대한 자기 서술(저는 ~한 편입니다)은 주장이 아니니 넣지 않는다. "
                "숫자·기간·회사명이 문서 안에서 서로 맞는지도 본다.",
    "verify_b": "너는 자소서 컨설턴트다. 2차 문항 적합·구조, 3차 직무·회사 적합, 4차 문장 품질만 본다. 문장을 고치지 말고 문제와 고칠 방향만 찾는다.",
    # 정밀 모드: 5차 검증을 관점별로 따로 (docs/call-budget.md 3장)
    "v1_fact": "너는 1차 사실성 검증관이다. 답변 문장을 하나씩 근거 카드 원문과 대조해 카드에 없는 원인·과정·결과·수치·감정 묘사를 모두 FA 위반으로 잡는다. 문제만 찾는다.",
    "v2_structure": "너는 2차 문항 적합·구조 검증관이다. 문항이 묻는 것에 답하는지, 두괄식인지, 문항당 핵심 메시지가 하나인지, 행동 서술이 충분한지만 본다. 문제만 찾는다.",
    "v3_fit": "너는 3차 직무·회사 적합 검증관이다. 공고 필수요건 대응, 회사명 바꾸기 테스트, 회사 조사 내용이 직무 과제로 연결되는지만 본다. 문제만 찾는다.",
    "v4_style": "너는 4차 문장 품질 검증관이다. 상투어, 근거 없는 자기평가, 맞춤법, 문장 길이, 문체 통일만 본다. 문제만 찾는다.",
    "v5_consistency": "너는 5차 일관성 검증관이다. 답변끼리, 그리고 경험 카드와 숫자·기간·회사명·직함이 맞는지, 문항 간 경험이 겹치는지만 본다. 문제만 찾는다.",
    "researcher": "너는 기업 분석가다. 주어진 회사 자료(공고·홈페이지·기사 원문)에 적힌 사실만 정리하고, 지원 직무가 풀어야 할 과제로 번역한다. 자료에 없는 내용은 쓰지 않는다.",
    "reviser": "너는 서류 수정자다. 검증에서 나온 위반만 고치고, 위반이 없는 문장은 그대로 둔다. 고치면서 새 사실을 만들지 않는다. "
               "사실 위반(FA)은 문장을 지우지 말고 **같은 자리에서 카드에 있는 사실로 바꿔 쓴다** "
               "(지어낸 결과·원인을 빼고 카드의 행동·배운 점이나 공고 업무와의 연결로 채운다). "
               "고친 뒤 각 답변은 수정 전보다 짧아지지 않아야 하고 분량 목표를 채워야 한다. "
               "분량이 모자라다는 위반(FC-4)은 아직 쓰지 않은 카드 사실과 공고·리서치 연결 문장을 더해 늘리고, 제한을 넘었으면 줄인다.",
}

# 에이전트마다 넣을 공통 원칙 단계와 직무군 부분
PLAN = {
    "matcher": (("analyze", "match"), ("overview", "hard_filters", "matcher")),
    "writer": (("write", "fact"), ("overview", "writer")),
    "resume": (("resume", "fact"), ("overview", "resume")),
    "judge": (("company_fit", "final_check"), ("overview", "hard_filters", "judge", "writer")),
    "drafter": (("match", "write", "fact"), ("overview", "matcher", "writer")),
    "verify_a": (("fact", "final_check"), ("overview",)),
    "verify_b": (("write", "company_fit"), ("overview", "writer")),
    "reviser": (("write", "fact"), ("overview", "writer")),
    "v1_fact": (("fact",), ("overview",)),
    "v2_structure": (("write",), ("overview", "writer")),
    "v3_fit": (("company_fit",), ("overview", "matcher")),
    "v4_style": (("write",), ("writer",)),
    "v5_consistency": (("final_check", "match"), ("overview",)),
    "researcher": (("analyze",), ("overview",)),
}

OUTPUT = {
    "matcher": '{"hard_filter_checks": [{"item": "", "status": "충족|미충족|확인 필요", "note": "미충족이면 강점으로 보완할 방법"}], '
               '"assignments": [{"question": "", "card_ids": [], "why": ""}], '
               '"missing_questions": [{"card_id": "", "question": ""}]}',
    "writer": '{"answers": [{"question": "", "text": "", "sentences": [{"text": "", "card_ids": []}]}]}',
    "resume": '{"summary": "", "sections": [{"title": "", "items": [{"text": "", "card_ids": []}]}]}',
    "judge": '{"scores": [{"item": "", "max": 0, "score": 0, "evidence": ""}], "total": 0, '
             '"verdict": "합격|보류|탈락", "reasons": [], "violations": [{"rule": "", "sentence": "", "why": ""}], '
             '"interview_questions": []}',
    "drafter": '{"assignments": [{"question": "", "card_ids": [], "why": ""}], '
               '"answers": [{"question": "", "text": "", "sentences": [{"text": "", "card_ids": []}]}], '
               '"missing_questions": [{"card_id": "", "question": ""}]}',
    "verify_a": '{"claims": [{"question": "", "sentence": "", "claim": "", "quote": "카드·공고 원문 그대로 또는 빈 문자열"}], '
                '"violations": [{"rule": "FC-2 같은 일관성 문제만", "question": "", "sentence": "", "why": ""}]}',
    "verify_b": '{"score": 0, "violations": [{"rule": "WR-1 같은 규칙 id", "question": "", "sentence": "", "why": "", "fix_hint": ""}]}',
    "v1_fact": '{"score": 0, "violations": [{"rule": "", "question": "", "sentence": "", "why": "", "fix_hint": ""}]}',
    "v2_structure": '{"score": 0, "violations": [{"rule": "", "question": "", "sentence": "", "why": "", "fix_hint": ""}]}',
    "v3_fit": '{"score": 0, "coverage": "필수요건 반영률 %", "violations": [{"rule": "", "question": "", "sentence": "", "why": "", "fix_hint": ""}]}',
    "v4_style": '{"score": 0, "violations": [{"rule": "", "question": "", "sentence": "", "why": "", "fix_hint": ""}]}',
    "v5_consistency": '{"score": 0, "violations": [{"rule": "", "question": "", "sentence": "", "why": "", "fix_hint": ""}]}',
    "researcher": '{"summary": "", "business": [], "products": [], "recent": [], "talent": [], '
                  '"role_challenges": [{"challenge": "이 직무가 풀어야 할 과제", "source": "근거 URL 또는 공고"}], "sources": []}',
    "reviser": '{"answers": [{"question": "", "text": "", "sentences": [{"text": "", "card_ids": []}]}], '
               '"changes": [{"rule": "", "before": "", "after": "", "why": ""}]}',
}

ANALYZER_OUTPUT = (
    '{"company": "", "position": "", "subrole": "아래 목록의 id 하나", "subrole_why": "", '
    '"format": "resume_only|free_one|multi_questions", '
    '"must": [], "nice": [], "keywords": [], "talent": [], "duties": [], '
    '"questions": [{"question": "", "limit": 0, "intent": ""}], '
    '"hard_filters": [{"item": "", "required": true}], '
    '"homepage": "공고에 회사 홈페이지 주소가 있으면", '
    '"fit": {"score": 0, "strengths": [], "gaps": [], "why": ""}}'
)


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
    if agent in ("matcher", "writer", "resume", "drafter", "reviser"):
        my_angle = angle(group)
        if my_angle:
            blocks.append(f"## 지원자 이야기 각도 (본인이 정한 방향, 사실 확인용 아님)\n{my_angle}")
    blocks.append(f"## 출력 형식 (JSON)\n{OUTPUT[agent]}")
    return "\n\n".join(blocks)


def build_analyzer_prompt() -> str:
    """공고 분석은 직무군을 정하기 전 단계라 직무군 기준 없이 만든다."""
    # id만 주면 electric_sales(장비 영업)와 electrical_pm(시공관리)을 헷갈려서 한글 이름을 붙인다
    subroles = "\n".join(f"- {g}: " + ", ".join(f"{s}({SUBROLE_LABELS[s]})" for s in subs) for g, subs in GROUPS.items())
    return "\n\n".join([
        "너는 채용 공고 분석가다. 공고 원문에 적힌 것만 뽑고, 없는 요건은 만들지 않는다.",
        f"## 지켜야 할 규칙\n{BASE_RULES}",
        f"## 공통 작성 원칙\n{principles('analyze')}",
        "## 세부 직무 목록 (직무군: 세부 직무 id)\n" + subroles
        + "\n가장 가까운 id 하나를 고른다. 딱 맞는 게 없어도 가장 가까운 것을 고르고 subrole_why에 이유를 쓴다.",
        "## 자소서 문항\n공고에 문항이 있으면 그대로 옮기고 글자 수 제한(공백 포함)을 limit에 적는다. "
        "제한은 공고에 숫자로 적힌 것만 쓰고, 없으면 0이다(추측해서 넣지 않는다). "
        "①② 같은 소문항이나 여러 줄로 나뉜 설명은 상위 문항 하나로 묶어 question에 함께 적는다. "
        "다른 회사 문항 예시나 다른 지원자 글처럼 이 공고의 문항이 아닌 것은 넣지 않는다. "
        "회사·직무 판정은 '지원 직무'에 적힌 업무를 기준으로 하고, 시공·공사관리면 electrical_pm, 장비를 파는 일이면 electric_sales처럼 실제 업무로 고른다. "
        "문항이 없고 이력서만 받으면 format=resume_only, 자유 양식 하나면 free_one과 함께 questions에 '자유 양식 자기소개'를 넣는다.",
        f"## 출력 형식 (JSON)\n{ANALYZER_OUTPUT}",
    ])

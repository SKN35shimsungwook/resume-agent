"""올린 이력서·포트폴리오 텍스트에서 경험 카드 초안을 뽑는다.

뽑은 카드는 사용자가 확인·수정한 뒤에만 사실 원장으로 저장한다.
"""
from .llm import ask_json
from .profile import CARD_KINDS, ExperienceCard

SYSTEM = (
    "너는 이력서 분석가다. 주어진 문서에 실제로 적힌 사실만 옮긴다. "
    "문서에 없는 수치·기간·성과는 절대 만들지 말고 빈 문자열로 둔다. 반드시 JSON으로만 답한다."
)

PROMPT = """아래 문서들에서 경험을 하나씩 나눠 경험 카드로 정리해줘.

kind는 {kinds} 중 하나.
각 카드 필드: title, kind, period, organization, role, situation, task, action, result,
metrics, learned, skills(문자열 배열), evidence(링크 배열).
문서에 근거가 없는 필드는 "" 또는 [] 로 둔다.

그리고 카드를 더 좋게 만들려면 사용자에게 물어봐야 할 것(예: 성과 수치, 내 역할 비중)을
missing_questions 배열에 카드 title과 함께 적어줘.

응답 형식:
{{"cards": [...], "missing_questions": [{{"card": "...", "question": "..."}}]}}

=== 문서 ===
{documents}
"""


def extract_cards(documents: dict) -> tuple[list[ExperienceCard], list[dict]]:
    joined = "\n\n".join(f"## {name}\n{text}" for name, text in documents.items())
    data = ask_json(
        "writer", SYSTEM, PROMPT.format(kinds=", ".join(CARD_KINDS), documents=joined[:60000])
    )
    fields = ExperienceCard.__dataclass_fields__
    cards = []
    for raw in data.get("cards", []):
        clean = {k: v for k, v in raw.items() if k in fields and k != "id"}
        if clean.get("title"):
            cards.append(ExperienceCard(**clean))
    return cards, data.get("missing_questions", [])

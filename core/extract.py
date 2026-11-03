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


CHUNK = 40000  # 한 번에 보낼 글자 수. 넘으면 문서를 나눠 여러 번 추출한 뒤 합친다.


def _chunks(documents: dict) -> list[str]:
    parts, current = [], ""
    for name, text in documents.items():
        for start in range(0, max(1, len(text)), CHUNK):
            label = f" (부분 {start // CHUNK + 1})" if len(text) > CHUNK else ""
            piece = f"## {name}{label}\n{text[start:start + CHUNK]}"
            if current and len(current) + len(piece) > CHUNK:
                parts.append(current)
                current = ""
            current += ("\n\n" if current else "") + piece
    if current:
        parts.append(current)
    return parts


def extract_cards(documents: dict) -> tuple[list[ExperienceCard], list[dict]]:
    fields = ExperienceCard.__dataclass_fields__
    cards, questions, seen = [], [], set()
    for chunk in _chunks(documents):
        # 추출은 창작이 아니라 옮겨 적기라서 온도를 낮춘다.
        data = ask_json("writer", SYSTEM, PROMPT.format(kinds=", ".join(CARD_KINDS), documents=chunk),
                        temperature=0.2, step="extract")
        for raw in data.get("cards", []):
            clean = {k: v for k, v in raw.items() if k in fields and k != "id"}
            key = (clean.get("title", ""), clean.get("period", ""))
            if clean.get("title") and key not in seen:  # 나눠 보낸 조각끼리 겹친 카드는 하나만
                seen.add(key)
                cards.append(ExperienceCard(**clean))
        questions += data.get("missing_questions", [])
    return cards, questions

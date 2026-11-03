"""LLM 없이 코드로 하는 검사 (호출 0회, docs/call-budget.md 2장 ①).

검증 원칙(knowledge/writing_principles.md)의 규칙 id로 위반을 돌려준다.
"""
import re
from collections import Counter

# WR-3: 근거 없이 쓰이는 자기평가·상투 표현 (조사 보고서의 금지 패턴 기반, 계속 늘린다)
CLICHES = [
    "역량을 기를 수 있었습니다", "역량을 키울 수 있었습니다", "성장할 수 있었습니다",
    "많은 것을 배울 수 있었습니다", "소중한 경험이었습니다", "최선을 다하겠습니다",
    "귀사", "열정을 가지고", "꼼꼼한 성격", "성실한 성격", "책임감이 강한", "소통을 잘",
    "시너지", "혁신적인 인재", "글로벌 인재",
]

NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?\s*(?:%|퍼센트)?")


def _numbers(text: str) -> set[str]:
    return {re.sub(r"[,\s]|퍼센트", "", m.group()).rstrip("%") for m in NUMBER.finditer(text)}


def run_checks(analysis: dict, draft: dict, cards: list, cards_text: str, other_companies: list[str]) -> list[dict]:
    """draft는 drafter/reviser 출력({answers: [...]})."""
    violations = []
    card_ids = {c.id for c in cards}
    allowed_numbers = _numbers(cards_text)
    answers = draft.get("answers", [])
    asked = [q.get("question", "") for q in analysis.get("questions", [])]

    # FC-4: 문항 누락
    answered = {a.get("question", "") for a in answers}
    for q in asked:
        if q and q not in answered and not any(q[:15] in a for a in answered):
            violations.append({"rule": "FC-4", "question": q, "sentence": "", "why": "이 문항의 답변이 없다."})

    limits = {q.get("question", ""): q.get("limit", 0) for q in analysis.get("questions", [])}
    main_cards = {}
    for a in answers:
        q, text = a.get("question", ""), a.get("text", "")
        # FC-4: 글자 수 (공백 포함)
        limit = limits.get(q, 0)
        if limit and len(text) > limit:
            violations.append({"rule": "FC-4", "question": q, "sentence": "",
                               "why": f"{len(text)}자로 제한 {limit}자를 넘었다.", "fix_hint": f"{len(text) - limit}자 이상 줄인다."})
        # FA-1: 근거 카드 id
        used = Counter()
        for s in a.get("sentences", []):
            ids = s.get("card_ids") or []
            unknown = [i for i in ids if i not in card_ids]
            if unknown:
                violations.append({"rule": "FA-1", "question": q, "sentence": s.get("text", ""),
                                   "why": f"없는 카드 id {unknown}를 근거로 달았다."})
            used.update(i for i in ids if i in card_ids)
        if used:
            main_cards[q] = used.most_common(1)[0][0]
        # FA-2: 카드에 없는 숫자
        for n in sorted(_numbers(text) - allowed_numbers):
            if len(n) >= 2 or n not in "0123456789":  # 한 자리 순서 숫자(1, 2…)는 넘어간다
                violations.append({"rule": "FA-2", "question": q, "sentence": n,
                                   "why": f"숫자 '{n}'이 경험 카드에 없다. 지어낸 수치일 수 있다."})
        # FC-3: 다른 회사명
        for other in other_companies:
            if other and other != analysis.get("company") and other in text:
                violations.append({"rule": "FC-3", "question": q, "sentence": other,
                                   "why": f"다른 회사 이름 '{other}'이 들어 있다."})
        # WR-3: 상투어
        for c in CLICHES:
            if c in text:
                violations.append({"rule": "WR-3", "question": q, "sentence": c,
                                   "why": "근거 없는 자기평가·상투 표현이다.", "fix_hint": "행동과 결과로 바꿔 쓴다."})

    # MA-1: 문항 간 주 경험 중복
    dup = [cid for cid, n in Counter(main_cards.values()).items() if n > 1]
    for cid in dup:
        qs = [q for q, c in main_cards.items() if c == cid]
        violations.append({"rule": "MA-1", "question": " / ".join(qs), "sentence": cid,
                           "why": f"카드 '{cid}'가 여러 문항의 주 경험으로 겹친다."})
    return violations

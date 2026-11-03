"""LLM 없이 코드로 하는 검사 (호출 0회, docs/call-budget.md 2장 ①).

검증 원칙(knowledge/writing_principles.md)의 규칙 id로 위반을 돌려준다.
"""
import json
import re
from collections import Counter
from pathlib import Path

# 표절·획일성 점검용 참고 글 모음 (예시·합격 자소서 등). 사용자가 .txt로 넣는다. 비공개 폴더.
from .paths import reference_dir
SIMILAR_LIMIT = 0.35  # 5글자 조각 겹침 비율이 이보다 높으면 경고

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


def _shingles(text: str, n: int = 5) -> set[str]:
    t = re.sub(r"\s+", "", text)
    return {t[i:i + n] for i in range(max(0, len(t) - n + 1))}


def similarity(a: str, b: str) -> float:
    """두 글이 얼마나 겹치는지 (내 답변 기준 5글자 조각 비율, 0~1)."""
    sa, sb = _shingles(a), _shingles(b)
    return len(sa & sb) / len(sa) if sa else 0.0


def _references() -> list[tuple[str, str]]:
    if not reference_dir().exists():
        return []
    return [(p.name, p.read_text(encoding="utf-8", errors="replace")) for p in reference_dir().glob("*.txt")]


def length_target(limit: int) -> tuple[int, int]:
    """문항의 분량 목표 (공백 포함). 제한이 없으면 600~800자: 30명 시험에서 제한 없는 문항이 200~400자로 끝났다."""
    return (int(limit * 0.8), limit) if limit else (600, 800)


def _limit_of(analysis: dict, question: str) -> int:
    for q in analysis.get("questions", []):
        text = q.get("question", "")
        if text == question or (text[:15] and text[:15] in question):
            return q.get("limit", 0) or 0
    return 0


def length_violations(analysis: dict, answers: list) -> list[dict]:
    """FC-4: 제한을 넘었거나 분량 목표에 크게 못 미친 답변."""
    found = []
    for a in answers:
        q, n = a.get("question", ""), len(a.get("text", ""))
        limit = _limit_of(analysis, q)
        lo, hi = length_target(limit)
        if limit and n > limit:
            found.append({"rule": "FC-4", "question": q, "sentence": "",
                          "why": f"{n}자로 제한 {limit}자를 넘었다.", "fix_hint": f"{n - lo}자쯤 줄여 {lo}~{limit}자로 맞춘다."})
        elif n < lo * 0.85:
            found.append({"rule": "FC-4", "question": q, "sentence": "",
                          "why": f"{n}자로 분량 목표 {lo}~{hi}자에 못 미친다.",
                          "fix_hint": "아직 쓰지 않은 카드 사실과 공고 업무·회사 리서치 연결 문장으로 늘린다(사실은 지어내지 않는다)."})
    return found


def _sentences(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[다요])[.!?]\s*", text) if len(x.strip()) >= 25]


def repeated_sentences(answers: list) -> list[dict]:
    """PL-2: 분량을 채우려고 같은 경험 문장을 되풀이한 곳 (고친 뒤 시험에서 '이러한 ~ 경험과' 반복이 생겼다)."""
    found, seen = [], []
    for a in answers:
        for sent in _sentences(a.get("text", "")):
            if any(similarity(sent, prev) >= 0.6 for prev in seen):
                found.append({"rule": "PL-2", "question": a.get("question", ""), "sentence": sent,
                              "why": "앞에서 쓴 문장과 거의 같은 내용을 되풀이했다.",
                              "fix_hint": "반복을 지우고, 그 자리를 아직 쓰지 않은 카드 사실이나 공고 업무와의 연결로 채운다."})
            seen.append(sent)
    return found


def run_checks(analysis: dict, draft: dict, cards: list, cards_text: str, other_companies: list[str],
               other_texts: list[str] | None = None) -> list[dict]:
    """draft는 drafter/reviser 출력({answers: [...]})."""
    violations = []
    card_ids = {c.id for c in cards} | {"posting"}  # posting = 공고에 적힌 회사·직무 사실
    allowed_numbers = _numbers(cards_text)
    answers = draft.get("answers", [])
    asked = [q.get("question", "") for q in analysis.get("questions", [])]

    # FC-4: 문항 누락
    answered = {a.get("question", "") for a in answers}
    for q in asked:
        if q and q not in answered and not any(q[:15] in a for a in answered):
            violations.append({"rule": "FC-4", "question": q, "sentence": "", "why": "이 문항의 답변이 없다."})

    violations += length_violations(analysis, answers) + repeated_sentences(answers)
    main_cards = {}
    for a in answers:
        q, text = a.get("question", ""), a.get("text", "")
        # 본문에 들어간 괄호 메모
        for memo in re.findall(r"\[[^\]]{2,40}\]", text):
            violations.append({"rule": "WR-2", "question": q, "sentence": memo,
                               "why": "답변 본문에 괄호 메모가 들어 있다.", "fix_hint": "메모를 지운다."})
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

    # PL-1: 표절·획일성 — 참고 글(예시 자소서)이나 다른 회사에 낸 내 답변과 너무 겹치는지
    refs = _references() + [(f"다른 공고 답변 {i + 1}", t) for i, t in enumerate(other_texts or []) if t]
    for a in answers:
        text = a.get("text", "")
        if len(text) < 100:
            continue
        for name, ref in refs:
            sim = similarity(text, ref)
            if sim >= SIMILAR_LIMIT:
                violations.append({"rule": "PL-1", "question": a.get("question", ""), "sentence": name,
                                   "why": f"'{name}'와 {sim:.0%} 겹친다. 회사명만 바꾼 글처럼 읽힐 수 있다.",
                                   "fix_hint": "이 회사의 사업·직무 과제와 연결된 문장으로 바꾼다."})

    # FA-1 보조: 카드·공고에 없는 낱말이 몰린 문장
    violations += novel_sentences(answers, cards_text + "\n" + json.dumps(analysis, ensure_ascii=False))

    # MA-1: 문항 간 주 경험 중복
    dup = [cid for cid, n in Counter(main_cards.values()).items() if n > 1]
    for cid in dup:
        qs = [q for q, c in main_cards.items() if c == cid]
        violations.append({"rule": "MA-1", "question": " / ".join(qs), "sentence": cid,
                           "why": f"카드 '{cid}'가 여러 문항의 주 경험으로 겹친다."})
    return violations


def _norm(text: str) -> str:
    return re.sub(r"[\s\"'“”‘’.,·()\[\]-]", "", text)


def grounding_violations(claims: list[dict], source_text: str) -> tuple[list[dict], int]:
    """검증 모델이 낸 주장별 근거 문구(quote)가 경험 카드·공고 원문에 실제로 있는지 글자 그대로 대조한다.

    모델이 '근거 있다'고 말해도 문구가 원문에 없으면 위반으로 잡는다 (모델 성능에 덜 기대려는 장치).
    돌려주는 값: (위반 목록, 사실성 점수 0~100)
    """
    src = _norm(source_text)
    violations, ok = [], 0
    for c in claims:
        quote = (c.get("quote") or "").strip()
        # 모델이 카드의 여러 항목을 이어 붙여 인용할 때가 있어서, 문장 조각마다 따로 대조한다
        pieces = [_norm(x) for x in re.split(r"[.。/|\n]|(?<=다)\s", quote)]
        pieces = [x for x in pieces if len(x) >= 4]
        if pieces and all(x in src for x in pieces):
            ok += 1
            continue
        why = ("근거 문구가 없다 — 경험 카드에 없는 내용일 수 있다." if not quote
               else f"근거로 든 문구 '{quote[:40]}'가 경험 카드·공고에 그대로 없다.")
        violations.append({"rule": "FA-1", "question": c.get("question", ""), "sentence": c.get("sentence", ""),
                           "why": f"주장 '{c.get('claim', '')[:60]}': {why}",
                           "fix_hint": "카드에 있는 사실로 바꾸거나, 없으면 지우고 확인 질문으로 돌린다."})
    score = round(100 * ok / len(claims)) if claims else 100
    return violations, score


# FA-1 보조: 카드·공고에 없는 낱말이 몰린 문장 (모델 판단과 상관없이 코드로)
_FUTURE = ("겠습니다", "하고자", "싶습니다", "지원했습니다", "지원합니다", "지원하였습니다", "되겠습니다")
_COMMON = set("""이 그 저 제 저는 제가 당시 이후 이어 또한 그리고 이에 이러한 이런 이와 같은 같이 통해 위해 대해 함께 바탕 바탕으로
경험 경험을 과정 과정에서 상황 상황에서 업무 업무를 직무 직무에 현장 현장에서 회사 고객 고객사 수행 수행했습니다 했습니다 있습니다
되었습니다 됐습니다 있었습니다 약 중 및 등 더 먼저 다시 직접 정확하게 차분히 문제 문제를 해결 해결했습니다 대응 대응했습니다
포기하지 않고 이를 겪고 달라고 요구할 따라 실시 통한 활용하여 활용해 위한 때 동안 이후에 단순히""".split())
_JOSA = ("으로써", "으로서", "에서는", "에서", "으로", "에게", "까지", "부터", "처럼", "보다", "라는", "이라는", "하며", "하고",
         "했고", "했으며", "하여", "해서", "을", "를", "이", "가", "은", "는", "의", "에", "와", "과", "도", "로", "만")


def _stem(word: str) -> str:
    w = re.sub(r"[^\w가-힣]", "", word)
    for j in _JOSA:
        if w.endswith(j) and len(w) > len(j) + 1:
            return w[: -len(j)]
    return w


def novel_sentences(answers: list, source_text: str, min_novel: int = 3, min_ratio: float = 0.2) -> list[dict]:
    src = re.sub(r"\s", "", source_text)
    found = []
    for a in answers:
        for s in a.get("sentences") or [{"text": x} for x in re.split(r"(?<=다\.)\s*", a.get("text", "")) if x]:
            text = s.get("text", "")
            if any(f in text for f in _FUTURE):
                continue  # 포부·다짐 문장은 사실 주장이 아니라서 넘어간다
            words = [w for w in (_stem(x) for x in text.split()) if len(w) >= 2 and w not in _COMMON]
            novel = [w for w in words if w[:2] not in src]
            if len(novel) >= min_novel and len(novel) / max(1, len(words)) >= min_ratio:
                found.append({"rule": "FA-1", "question": a.get("question", ""), "sentence": text,
                              "why": f"경험 카드·공고에 없는 낱말이 많다: {', '.join(novel[:6])}",
                              "fix_hint": "카드에 있는 사실로 바꾸거나 지우고, 필요하면 확인 질문으로 돌린다."})
    return found


INFO_FIELDS = {"employment": "고용 형태", "deadline": "마감일", "salary": "급여", "location": "근무지",
               "hours": "근무 시간", "benefits": "복지", "headcount": "모집 인원"}


def ground_info(info: dict, posting_text: str) -> dict:
    """공고 근무 조건을 근거 문구로 검사한다. 근거가 공고 원문에 글자 그대로 없으면 값을 비우고 dropped에 남긴다.

    링커리어 페이지에는 다른 회사 예시가 섞여 있어(30명 시험: 남의 '최대 800자'를 가져옴),
    근거 문구가 있어도 원문 안에 있는지만 볼 뿐 어느 회사 것인지는 사람이 확인해야 한다.
    """
    src = re.sub(r"\s", "", posting_text)
    out = {}
    for key in INFO_FIELDS:
        item = info.get(key) or {}
        if not isinstance(item, dict):
            item = {"value": str(item), "quote": ""}
        value, quote = str(item.get("value") or "").strip(), str(item.get("quote") or "").strip()
        if value and (not quote or re.sub(r"\s", "", quote) not in src):
            out[key] = {"value": "", "quote": "", "dropped": value}
        else:
            out[key] = {"value": value, "quote": quote}
    return out

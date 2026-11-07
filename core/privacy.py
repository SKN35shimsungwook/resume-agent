"""AI에 보내기 직전에 개인정보를 가리고, 받은 답에서 다시 되돌린다.

Gemini 무료 등급은 약관상 입력이 서비스 개선에 쓰이고 사람이 검토할 수 있다.
그래서 이름·이메일·전화번호·주민등록번호, 그리고 설정에 적은 단어(주소·학교 등)는
[이름]·[이메일] 같은 자리표시로 바꿔 보내고, 답이 오면 원래 값으로 되돌린다.
경력 내용 자체는 그대로 간다 (그걸 가리면 글을 쓸 수 없다).
"""
import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
PHONE = re.compile(r"(?<!\d)(01[016789]|0\d{1,2})[-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)")
RRN = re.compile(r"(?<!\d)\d{6}[-\s]?[1-4]\d{6}(?!\d)")  # 주민등록번호


def build_rules(profile=None, extra: list[str] | None = None) -> list[tuple[str, str]]:
    """(원래 값, 자리표시) 목록. 긴 값부터 바꿔야 겹치는 값이 덜 깨진다."""
    rules = []
    if profile is not None:
        name = (getattr(profile, "name", "") or "").strip()
        if len(name) >= 2:
            rules.append((name, "[이름]"))
            if " " in name:
                rules.append((name.replace(" ", ""), "[이름]"))
        for value, tag in ((getattr(profile, "email", ""), "[이메일]"), (getattr(profile, "phone", ""), "[전화]")):
            if (value or "").strip():
                rules.append((value.strip(), tag))
    for i, word in enumerate(w.strip() for w in (extra or []) if w and w.strip()):
        if len(word) >= 2:
            rules.append((word, f"[가림{i + 1}]"))
    return sorted(rules, key=lambda r: -len(r[0]))


def mask(text: str, rules: list[tuple[str, str]], found: dict) -> str:
    """text를 가린다. found에는 자리표시 → 원래 값을 모은다 (되돌릴 때 쓴다)."""
    if not text:
        return text
    for value, tag in rules:
        if value in text:
            text = text.replace(value, tag)
            found.setdefault(tag, value)
    # 프로필에 없는 연락처(이력서 속 다른 번호·메일)도 가린다
    for pattern, kind in ((RRN, "주민번호"), (EMAIL, "이메일"), (PHONE, "전화")):
        def _sub(m, kind=kind):
            value = m.group(0)
            for tag, old in found.items():
                if old == value:
                    return tag
            tag = f"[{kind}{sum(1 for t in found if t.startswith('[' + kind)) + 1}]"
            found[tag] = value
            return tag
        text = pattern.sub(_sub, text)
    return text


def unmask(data, found: dict):
    """AI 답(dict·list·str) 안의 자리표시를 원래 값으로 되돌린다. 주민번호는 되돌리지 않는다."""
    if not found:
        return data
    if isinstance(data, str):
        for tag, value in found.items():
            if not tag.startswith("[주민번호"):
                data = data.replace(tag, value)
        return data
    if isinstance(data, list):
        return [unmask(x, found) for x in data]
    if isinstance(data, dict):
        return {k: unmask(v, found) for k, v in data.items()}
    return data

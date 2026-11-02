"""knowledge/ 아래 마크다운을 잘라 프롬프트에 넣는다.

- writing_principles.md: `<!-- stage: 이름 -->` 로 나뉜 공통 작성 원칙
- groups/<직무군>.md: `<!-- part: 이름 -->` 로 나뉜 직무군 기준
- data/angles.md(비공개): `<!-- group: 이름 -->` 로 나뉜 내 이야기 각도
"""
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRINCIPLES_PATH = ROOT / "knowledge" / "writing_principles.md"
GROUPS_DIR = ROOT / "knowledge" / "groups"
ANGLES_PATH = ROOT / "data" / "angles.md"

# 직무군 id → 세부 직무 id 목록 (knowledge/groups/README.md와 같아야 한다)
GROUPS = {
    "ai_consulting": ["ax_external", "ax_manufacturing", "dx_inhouse"],
    "tech_sales": ["it_sales", "presales", "electric_sales", "b2b_sales"],
    "field_equipment": ["fse_cs", "production_equipment", "factory_electrical"],
    "smart_factory": ["smart_factory_dx", "mes", "manufacturing_ax"],
    "electrical_construction": ["electrician", "interior_electric", "electrical_pm"],
    "startup_dev": ["fullstack", "backend", "ai_app"],
}


def _split(text: str, marker: str) -> dict[str, str]:
    parts = re.split(rf"<!-- {marker}: (\w+) -->", text)
    # parts = [머리말, 이름1, 본문1, 이름2, 본문2, ...]
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}


@lru_cache(maxsize=1)
def _sections() -> dict[str, str]:
    return _split(PRINCIPLES_PATH.read_text(encoding="utf-8"), "stage")


def principles(*stages: str) -> str:
    """원하는 단계의 규칙표만 이어 붙여 돌려준다. 예: principles("write", "fact")"""
    sections = _sections()
    missing = [s for s in stages if s not in sections]
    if missing:
        raise KeyError(f"없는 단계: {missing}")
    return "\n\n".join(sections[s] for s in stages)


def group_of(subrole: str) -> str:
    for group, subroles in GROUPS.items():
        if subrole in subroles:
            return group
    raise KeyError(f"없는 세부 직무: {subrole}")


@lru_cache(maxsize=None)
def _group_parts(group: str) -> dict[str, str]:
    return _split((GROUPS_DIR / f"{group}.md").read_text(encoding="utf-8"), "part")


def group_part(group: str, *parts: str) -> str:
    """직무군 파일에서 원하는 부분만. 예: group_part("tech_sales", "matcher", "hard_filters")"""
    sections = _group_parts(group)
    missing = [p for p in parts if p not in sections]
    if missing:
        raise KeyError(f"{group}에 없는 부분: {missing}")
    return "\n\n".join(sections[p] for p in parts)


def angle(group: str) -> str:
    """내 이야기 각도(공통 + 해당 직무군). 비공개 파일이 없으면 빈 문자열."""
    if not ANGLES_PATH.exists():
        return ""
    sections = _split(ANGLES_PATH.read_text(encoding="utf-8"), "group")
    return "\n\n".join(s for s in (sections.get("common", ""), sections.get(group, "")) if s)

"""경험 카드(사실 원장) 스키마와 저장.

AI는 이 카드에 적힌 사실만 근거로 글을 쓸 수 있다. 문장마다 근거 카드 id를 달게 해서
1차 검증(사실성)에서 근거 없는 문장을 걸러낸다.
"""
import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .paths import profile_path

CARD_KINDS = ["경력", "프로젝트", "교육", "수상·자격", "대외활동", "기타"]


@dataclass
class ExperienceCard:
    title: str
    kind: str = "프로젝트"
    period: str = ""            # 예: 2026.08 ~ 2026.09
    organization: str = ""      # 회사·기관·팀
    role: str = ""              # 내가 맡은 역할
    situation: str = ""         # S: 상황·배경
    task: str = ""              # T: 과제·목표
    action: str = ""            # A: 내가 한 행동 (가장 자세히)
    result: str = ""            # R: 결과
    metrics: str = ""           # 수치로 된 성과
    learned: str = ""           # V/L: 가치관·배운 점
    skills: list = field(default_factory=list)
    evidence: list = field(default_factory=list)  # GitHub·포트폴리오 링크
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


@dataclass
class Profile:
    name: str = ""
    email: str = ""
    phone: str = ""
    target_roles: list = field(default_factory=list)
    summary: str = ""           # 한 줄 소개
    education: str = ""
    raw_documents: dict = field(default_factory=dict)  # 파일 이름 → 추출한 텍스트
    cards: list = field(default_factory=list)          # ExperienceCard 목록


def load_profile(path: Path | None = None) -> Profile:
    path = path or profile_path()
    if not path.exists():
        return Profile()
    data = json.loads(path.read_text(encoding="utf-8"))
    cards = [ExperienceCard(**c) for c in data.pop("cards", [])]
    return Profile(**data, cards=cards)


def save_profile(profile: Profile, path: Path | None = None) -> None:
    path = path or profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(profile), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def cards_as_context(profile: Profile) -> str:
    """LLM 프롬프트에 넣을 사실 원장 텍스트. 카드마다 [id]를 붙인다."""
    blocks = []
    for c in profile.cards:
        lines = [f"[{c.id}] {c.kind} · {c.title} ({c.period}, {c.organization})"]
        for label, value in (
            ("역할", c.role), ("상황", c.situation), ("과제", c.task),
            ("행동", c.action), ("결과", c.result), ("수치", c.metrics),
            ("배운 점", c.learned), ("기술", ", ".join(c.skills)),
        ):
            if value:
                lines.append(f"  - {label}: {value}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)

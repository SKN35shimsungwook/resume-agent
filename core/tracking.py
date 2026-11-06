"""지원 후 관리: 발표·시험·면접 일정과 할 일 체크리스트, 메모 (공고 결과 state.json의 tracking에 저장)."""
from datetime import date

from .pipeline import load_state, save_state

DATE_LABELS = ["서류 발표", "인적성·과제", "면접", "최종 발표"]
DEFAULT_TODO = [
    "제출 확인 (접수 완료 화면·메일 저장)",
    "서류 발표일 확인",
    "인적성·코딩테스트 준비",
    "예상 면접 질문 연습 (인사담당자 첨삭 화면)",
    "회사 최근 소식 확인",
    "면접 장소·시간·복장 확인",
]


def get(state: dict) -> dict:
    t = state.get("tracking") or {}
    return {"dates": {k: (t.get("dates") or {}).get(k, "") for k in DATE_LABELS},
            "todo": t.get("todo") or [{"text": x, "done": False} for x in DEFAULT_TODO],
            "memo": t.get("memo", "")}


def save(rid: str, tracking: dict) -> None:
    state = load_state(rid)
    state["tracking"] = tracking
    save_state(rid, state)


def upcoming(states: list[dict], days: int = 14) -> list[dict]:
    """오늘부터 days일 안의 일정 (지난 일정·탈락·포기한 지원은 빼고)."""
    today, out = date.today(), []
    for s in states:
        if any(w in s.get("apply_status", "") for w in ("탈락", "포기", "최종 합격")):
            continue
        for label, value in get(s)["dates"].items():
            try:
                d = date.fromisoformat(value)
            except ValueError:
                continue
            if 0 <= (d - today).days <= days:
                a = s.get("analysis", {})
                out.append({"date": value, "d": (d - today).days, "what": label, "company": a.get("company", ""),
                            "position": a.get("position", ""), "rid": s["id"]})
    return sorted(out, key=lambda x: x["date"])

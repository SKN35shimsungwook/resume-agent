"""일반 모드 파이프라인 (docs/call-budget.md 3장).

분석 1 → 초안 1 → 코드 검사 0 → 검증 A 1 → 검증 B 1 → 수정 0~1 → 인사담당자 1 (+수정 1)
= 공고 1개에 AI 호출 5~7번.

단계마다 결과를 data/runs/<id>/state.json에 저장한다. 중간에 멈추면(한도·장애)
같은 공고로 다시 부르면 끝난 단계는 건너뛰고 멈춘 단계부터 이어서 한다.
"""
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from .checks import run_checks
from .knowledge import GROUPS
from .llm import ask_json, load_config
from .profile import cards_as_context, load_profile
from .prompts import build_analyzer_prompt, build_system_prompt

RUNS_DIR = Path(__file__).resolve().parent.parent / "data" / "runs"
STEPS = ["analyze", "draft", "checks", "verify_a", "verify_b", "revise", "hr", "revise_2"]
REVISE_2_BELOW = 70  # 인사담당자 점수가 이보다 낮으면 한 번 더 고친다


def run_id(posting_text: str) -> str:
    return hashlib.sha1(posting_text.strip().encode("utf-8")).hexdigest()[:10]


def load_state(rid: str) -> dict:
    path = RUNS_DIR / rid / "state.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_state(rid: str, state: dict) -> None:
    path = RUNS_DIR / rid / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated"] = datetime.now().isoformat(timespec="seconds")
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def list_runs() -> list[dict]:
    if not RUNS_DIR.exists():
        return []
    runs = [load_state(p.name) | {"id": p.name} for p in RUNS_DIR.iterdir() if (p / "state.json").exists()]
    return sorted(runs, key=lambda r: r.get("updated", ""), reverse=True)


def _other_companies(current_rid: str) -> list[str]:
    return [r.get("analysis", {}).get("company", "") for r in list_runs() if r["id"] != current_rid]


def _answers_text(draft: dict) -> str:
    return "\n\n".join(f"### {a.get('question', '')}\n{a.get('text', '')}" for a in draft.get("answers", []))


def _payload(state: dict, cards_text: str, draft: dict | None = None, extra: str = "") -> str:
    parts = [
        f"## 공고 분석\n{json.dumps(state['analysis'], ensure_ascii=False)}",
        f"## 경험 카드 (사실 원장)\n{cards_text}",
    ]
    if draft is not None:
        parts.append(f"## 현재 답변\n{_answers_text(draft)}\n\n(문장별 근거)\n"
                     f"{json.dumps(draft.get('answers', []), ensure_ascii=False)}")
    if extra:
        parts.append(extra)
    return "\n\n".join(parts)


def run(posting_text: str, on_step=None, config: dict | None = None) -> dict:
    """공고 하나를 일반 모드로 처리한다. on_step(step, state)는 진행 표시용."""
    config = config or load_config()
    rid = run_id(posting_text)
    state = load_state(rid) or {"id": rid, "created": datetime.now().isoformat(timespec="seconds"),
                                "posting": posting_text, "done": [], "status": "running"}
    profile = load_profile()
    if not profile.cards:
        raise ValueError("경험 카드가 없습니다. '내 경험 정리'에서 먼저 카드를 만들어 주세요.")
    cards_text = cards_as_context(profile)

    def step(name, fn):
        if name in state["done"]:
            return
        if on_step:
            on_step(name, state)
        fn()
        state["done"].append(name)
        save_state(rid, state)

    def analyze():
        state["analysis"] = ask_json("writer", build_analyzer_prompt(),
                                     f"## 공고 원문\n{posting_text[:30000]}", config=config,
                                     temperature=0.2, step="analyze")

    def draft():
        state["draft"] = ask_json("writer", build_system_prompt("drafter", state["analysis"]["subrole"]),
                                  _payload(state, cards_text), config=config, step="draft")

    def checks():
        state["code_violations"] = run_checks(state["analysis"], state["draft"], profile.cards,
                                              cards_text, _other_companies(rid))

    def verify(kind):
        def _go():
            state[kind] = ask_json("judge", build_system_prompt(kind, state["analysis"]["subrole"]),
                                   _payload(state, cards_text, state["draft"]), config=config, step=kind)
        return _go

    def violations() -> list:
        return (state.get("code_violations", []) + state.get("verify_a", {}).get("violations", [])
                + state.get("verify_b", {}).get("violations", []))

    def revise(source_key, out_key):
        def _go():
            found = violations() if source_key == "verify" else state["hr"].get("violations", []) + [
                {"rule": "HR", "why": r} for r in state["hr"].get("reasons", [])]
            if not found:
                return  # 위반이 없으면 호출하지 않는다
            extra = f"## 고칠 것 (이것만 고친다)\n{json.dumps(found, ensure_ascii=False)}"
            state["final"] = ask_json("writer", build_system_prompt("reviser", state["analysis"]["subrole"]),
                                      _payload(state, cards_text, state.get("final", state["draft"]), extra),
                                      config=config, temperature=0.4, step=out_key)
            state.setdefault("revisions", []).append({"after": out_key, "changes": state["final"].get("changes", [])})
        return _go

    def hr():
        current = state.get("final", state["draft"])
        state["hr"] = ask_json("judge", build_system_prompt("judge", state["analysis"]["subrole"]),
                               _payload(state, cards_text, current), config=config, step="hr")

    def revise_2():
        if (state["hr"].get("total") or 0) < REVISE_2_BELOW:
            revise("hr", "revise_2")()

    state["status"] = "running"
    state.pop("error", None)
    try:
        step("analyze", analyze)
        step("draft", draft)
        step("checks", checks)
        step("verify_a", verify("verify_a"))
        step("verify_b", verify("verify_b"))
        step("revise", revise("verify", "revise"))
        step("hr", hr)
        step("revise_2", revise_2)
        state["status"] = "done"
    except Exception as e:  # 한도·장애로 멈추면 저장해 두고 다음에 이어서 한다
        state["status"] = "paused"
        state["error"] = str(e)[:500]
    save_state(rid, state)
    return state


def final_answers(state: dict) -> list[dict]:
    return state.get("final", state.get("draft", {})).get("answers", [])


def char_count(text: str) -> tuple[int, int]:
    """(공백 포함, 공백 제외) 글자 수"""
    return len(text), len(re.sub(r"\s", "", text))

"""공고 하나를 처리하는 파이프라인 (docs/call-budget.md 3장).

일반 모드: 분석(+적합도) → 회사 리서치(회사별 1회, 이후 재사용) → 초안 → 코드 검사 → 검증 A → 검증 B
          → 수정 → 맞춤 이력서 → 인사담당자 → (점수 낮으면) 추가 수정
정밀 모드: 초안 뒤 5차 검증을 관점별로 하나씩, 회차마다 위반이 있으면 바로 수정

공고 종류별 처리:
- resume_only(이력서만): 자소서 단계를 건너뛰고 맞춤 이력서 + 인사담당자만
- free_one / multi_questions: 전체 흐름

단계마다 data/runs/<id>/state.json에 저장한다. 한도·장애로 멈추면(paused) 또는
"회차마다 확인" 설정으로 멈추면(waiting) 같은 공고로 다시 부를 때 멈춘 단계부터 이어서 한다.
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
from .research import research

from .paths import base_resume_dir, runs_dir
REVISE_2_BELOW = 70  # 인사담당자 점수가 이보다 낮으면 한 번 더 고친다
PRECISE_ROUNDS = ["v1_fact", "v2_structure", "v3_fit", "v4_style", "v5_consistency"]
ESSAY_STEPS = {"draft", "checks", "verify_a", "verify_b", "revise", "revise_2", *PRECISE_ROUNDS,
               *[f"revise_{r}" for r in PRECISE_ROUNDS]}
APPLY_STATUSES = ["준비", "제출", "서류 합격", "서류 탈락", "면접", "최종 합격", "포기"]


class WaitForApproval(Exception):
    """'회차마다 확인' 설정으로 사람 확인을 기다린다."""


def steps_for(mode: str) -> list[str]:
    head = ["analyze", "research", "draft", "checks"]
    if mode == "precise":
        middle = [x for r in PRECISE_ROUNDS for x in (r, f"revise_{r}")]
    else:
        middle = ["verify_a", "verify_b", "revise"]
    return head + middle + ["resume", "hr", "revise_2"]


def run_id(posting_text: str) -> str:
    return hashlib.sha1(posting_text.strip().encode("utf-8")).hexdigest()[:10]


def load_state(rid: str) -> dict:
    path = runs_dir() / rid / "state.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_state(rid: str, state: dict) -> None:
    path = runs_dir() / rid / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated"] = datetime.now().isoformat(timespec="seconds")
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def list_runs() -> list[dict]:
    if not runs_dir().exists():
        return []
    runs = [load_state(p.name) | {"id": p.name} for p in runs_dir().iterdir() if (p / "state.json").exists()]
    return sorted(runs, key=lambda r: r.get("updated", ""), reverse=True)


def _other_runs(current_rid: str) -> list[dict]:
    return [r for r in list_runs() if r["id"] != current_rid]


def _answers_text(answers: list) -> str:
    return "\n\n".join(f"### {a.get('question', '')}\n{a.get('text', '')}" for a in answers)


def resume_text(resume: dict) -> str:
    lines = [resume.get("summary", "")]
    for sec in resume.get("sections", []):
        lines.append(f"\n[{sec.get('title', '')}]")
        lines += [f"- {it.get('text', '')}" for it in sec.get("items", [])]
    return "\n".join(lines).strip()


def current_answers(state: dict) -> list[dict]:
    return state.get("final", state.get("draft", {})).get("answers", [])


final_answers = current_answers  # 이전 이름 호환


def _payload(state: dict, cards_text: str, answers: list | None = None, extra: str = "") -> str:
    parts = [f"## 공고 분석\n{json.dumps(state['analysis'], ensure_ascii=False)}"]
    if state.get("research"):
        parts.append(f"## 회사 리서치 (출처 있는 사실)\n{json.dumps(state['research'], ensure_ascii=False)}")
    parts.append(f"## 경험 카드 (사실 원장)\n{cards_text}")
    if answers is not None:
        parts.append(f"## 현재 답변\n{_answers_text(answers)}\n\n(문장별 근거)\n{json.dumps(answers, ensure_ascii=False)}")
    if state.get("resume"):
        parts.append(f"## 맞춤 이력서\n{resume_text(state['resume'])}")
    if extra:
        parts.append(extra)
    return "\n\n".join(parts)


def _snapshot(state: dict, label: str) -> None:
    state.setdefault("history", []).append({
        "label": label, "at": datetime.now().isoformat(timespec="seconds"),
        "answers": json.loads(json.dumps(current_answers(state), ensure_ascii=False)),
    })


def restore(rid: str, index: int) -> dict:
    """수정 기록의 index번째 답변으로 되돌린다."""
    state = load_state(rid)
    snap = state["history"][index]
    state["final"] = {"answers": snap["answers"], "changes": []}
    _snapshot(state, f"되돌림 → {snap['label']}")
    save_state(rid, state)
    return state


def set_field(rid: str, **fields) -> None:
    state = load_state(rid)
    state.update(fields)
    save_state(rid, state)


def approve(rid: str) -> None:
    state = load_state(rid)
    state.setdefault("approvals", []).append(state.get("waiting_at", ""))
    state["status"] = "running"
    save_state(rid, state)


def base_resume(subrole: str) -> dict | None:
    path = base_resume_dir() / f"{subrole}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def build_base_resume(subrole: str, config: dict | None = None) -> dict:
    """세부 직무별 기본 이력서. 한 번 만들어 두고 공고마다 살짝 고쳐 쓴다 (호출 1번)."""
    profile = load_profile()
    resume = ask_json("writer", build_system_prompt("resume", subrole),
                      f"## 목표\n특정 회사가 아니라 `{subrole}` 직무 전반에 내는 기본 이력서를 만든다.\n\n"
                      f"## 지원자\n이름: {profile.name}\n학력: {profile.education}\n한 줄 소개: {profile.summary}\n\n"
                      f"## 경험 카드 (사실 원장)\n{cards_as_context(profile)}",
                      config=config, temperature=0.3, step="base_resume")
    base_resume_dir().mkdir(parents=True, exist_ok=True)
    (base_resume_dir() / f"{subrole}.json").write_text(json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8")
    return resume


def run(posting_text: str, on_step=None, config: dict | None = None, mode: str | None = None,
        extra_urls: list[str] | None = None, stop_after: str | None = None) -> dict:
    """공고 하나를 처리한다. on_step(step, state)는 진행 표시용. stop_after="analyze"면 적합도만 보고 멈춘다."""
    config = config or load_config()
    rid = run_id(posting_text)
    state = load_state(rid) or {"id": rid, "created": datetime.now().isoformat(timespec="seconds"),
                                "posting": posting_text, "done": [], "apply_status": "준비"}
    state["mode"] = mode or state.get("mode") or "normal"
    if extra_urls:
        state["extra_urls"] = extra_urls
    profile = load_profile()
    if not profile.cards:
        raise ValueError("경험 카드가 없습니다. '내 경험 정리'에서 먼저 카드를 만들어 주세요.")
    cards_text = cards_as_context(profile)
    subrole = lambda: state["analysis"]["subrole"]  # noqa: E731

    def is_resume_only() -> bool:
        return state.get("analysis", {}).get("format") == "resume_only"

    def step(name, fn, gate: bool = False):
        if name in state["done"]:
            return
        if name in ESSAY_STEPS and is_resume_only():
            state["done"].append(name)  # 이력서만 받는 공고는 자소서 단계를 건너뛴다
            return
        if on_step:
            on_step(name, state)
        fn()
        state["done"].append(name)
        save_state(rid, state)
        if gate and config.get("confirm_each_round") and name not in state.get("approvals", []):
            state["status"], state["waiting_at"] = "waiting", name
            raise WaitForApproval(name)

    def analyze():
        titles = "\n".join(f"- [{c.id}] {c.kind} · {c.title} ({c.period})" for c in profile.cards)
        analysis = ask_json("writer", build_analyzer_prompt(),
                            f"## 공고 원문\n{posting_text[:30000]}\n\n## 지원자 경험 요약 (적합도용)\n{titles}",
                            config=config, temperature=0.2, step="analyze")
        valid = {s for subs in GROUPS.values() for s in subs}
        if analysis.get("subrole") not in valid:  # 목록 밖 id면 내 희망 직무 첫 번째로
            analysis["subrole_why"] = (f"(분석 결과 '{analysis.get('subrole')}'가 목록에 없어 기본값 사용) "
                                       + str(analysis.get("subrole_why", "")))
            analysis["subrole"] = (profile.target_roles or ["ax_external"])[0]
        state["analysis"] = analysis

    def do_research():
        if config.get("research", True):
            state["research"] = research(state["analysis"], posting_text, state.get("extra_urls"), config)

    def draft():
        state["draft"] = ask_json("writer", build_system_prompt("drafter", subrole()),
                                  _payload(state, cards_text), config=config, step="draft")
        _snapshot(state, "초안")

    def checks():
        others = _other_runs(rid)
        state["code_violations"] = run_checks(
            state["analysis"], {"answers": current_answers(state)}, profile.cards, cards_text,
            [r.get("analysis", {}).get("company", "") for r in others],
            [a.get("text", "") for r in others for a in current_answers(r)])

    def verify(kind):
        def _go():
            state[kind] = ask_json("judge", build_system_prompt(kind, subrole()),
                                   _payload(state, cards_text, current_answers(state)), config=config, step=kind)
        return _go

    def revise(found_fn, label):
        def _go():
            found = found_fn()
            if not found:
                return  # 위반이 없으면 호출하지 않는다
            extra = f"## 고칠 것 (이것만 고친다)\n{json.dumps(found, ensure_ascii=False)}"
            state["final"] = ask_json("writer", build_system_prompt("reviser", subrole()),
                                      _payload(state, cards_text, current_answers(state), extra),
                                      config=config, temperature=0.4, step=label)
            state.setdefault("revisions", []).append({"after": label, "changes": state["final"].get("changes", [])})
            _snapshot(state, label)
        return _go

    def normal_violations():
        return (state.get("code_violations", []) + state.get("verify_a", {}).get("violations", [])
                + state.get("verify_b", {}).get("violations", []))

    def tailored_resume():
        base = base_resume(subrole())
        extra = (f"## 기본 이력서 (순서·강조만 이 공고에 맞게 고친다)\n{json.dumps(base, ensure_ascii=False)}"
                 if base else "## 기본 이력서 없음 — 경험 카드로 이 공고용 이력서를 새로 만든다.")
        extra += ("\n\n## 이력서 규칙\n- 이력서만 만든다. 자기소개서 답변이나 문항을 이력서 안에 넣지 않는다.\n"
                  "- 항목은 짧은 사실 문장으로 쓰고, 카드에 없는 결과(복구했다, 안정화했다 등)를 붙이지 않는다.")
        state["resume"] = ask_json("writer", build_system_prompt("resume", subrole()),
                                   _payload(state, cards_text, extra=extra), config=config,
                                   temperature=0.3, step="resume")

    def hr():
        state["hr"] = ask_json("judge", build_system_prompt("judge", subrole()),
                               _payload(state, cards_text, current_answers(state)), config=config, step="hr")

    def revise_2():
        if (state["hr"].get("total") or 0) < REVISE_2_BELOW:
            revise(lambda: state["hr"].get("violations", []) + [{"rule": "HR", "why": r} for r in state["hr"].get("reasons", [])],
                   "revise_2")()

    state["status"] = "running"
    state.pop("error", None)
    try:
        step("analyze", analyze)
        if stop_after == "analyze":
            state["status"] = "screened"
            save_state(rid, state)
            return state
        step("research", do_research)
        step("draft", draft)
        step("checks", checks)
        if state["mode"] == "precise":
            for r in PRECISE_ROUNDS:
                step(r, verify(r), gate=True)
                step(f"revise_{r}", revise(lambda r=r: state.get(r, {}).get("violations", [])
                                           + (state.get("code_violations", []) if r == "v1_fact" else []),
                                           f"revise_{r}"))
        else:
            step("verify_a", verify("verify_a"))
            step("verify_b", verify("verify_b"), gate=True)
            step("revise", revise(normal_violations, "revise"))
        step("resume", tailored_resume)
        step("hr", hr)
        step("revise_2", revise_2)
        state["status"] = "done"
        state.pop("waiting_at", None)
    except WaitForApproval:
        pass
    except Exception as e:  # 한도·장애로 멈추면 저장해 두고 다음에 이어서 한다
        state["status"] = "paused"
        state["error"] = str(e)[:500]
    save_state(rid, state)
    return state


def char_count(text: str) -> tuple[int, int]:
    """(공백 포함, 공백 제외) 글자 수"""
    return len(text), len(re.sub(r"\s", "", text))

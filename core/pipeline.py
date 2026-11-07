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
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .checks import (_norm, fact_report, grounding_violations, length_target, length_violations, merge_info,
                     novel_sentences, repeated_sentences, run_checks)
from .knowledge import GROUPS
from .llm import ask_json, load_config
from .profile import cards_as_context, load_profile
from .prompts import HR_PERSPECTIVES, build_analyzer_prompt, build_system_prompt
from .research import research

from .paths import base_resume_dir, runs_dir
REVISE_2_BELOW = 70  # 인사담당자 점수가 이보다 낮으면 한 번 더 고친다
PRECISE_ROUNDS = ["v1_fact", "v2_structure", "v3_fit", "v4_style", "v5_consistency"]
ESSAY_STEPS = {"draft", "checks", "verify_a", "verify_b", "revise", "revise_2", "final_check", *PRECISE_ROUNDS,
               *[f"revise_{r}" for r in PRECISE_ROUNDS]}
# 탈락은 단계마다 따로 둔다 (어디서 떨어졌는지 나중에 모아 보려고)
APPLY_STATUSES = ["준비", "제출", "서류 합격", "서류 탈락", "인적성·과제", "인적성·과제 탈락", "면접", "면접 탈락",
                  "최종 합격", "최종 탈락", "포기"]


class WaitForApproval(Exception):
    """'회차마다 확인' 설정으로 사람 확인을 기다린다."""


def steps_for(mode: str) -> list[str]:
    head = ["analyze", "research", "draft", "checks"]
    if mode == "precise":
        middle = [x for r in PRECISE_ROUNDS for x in (r, f"revise_{r}")]
    else:
        middle = ["verify_a", "verify_b", "revise"]
    return head + middle + ["resume", "hr", "revise_2", "final_check"]


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
    from . import db  # 저장할 때마다 지원 현황 DB도 맞춘다 (파일이 원본, DB는 찾아보기용 색인)
    db.sync(state)


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
        # 회사 정보 표·공고 비교는 나무위키 같은 참고용 자료가 섞일 수 있어 글쓰기에는 넘기지 않는다
        facts = {k: v for k, v in state["research"].items() if k not in ("company_profile", "compare")}
        parts.append(f"## 회사 리서치 (출처 있는 사실)\n{json.dumps(facts, ensure_ascii=False)}")
    parts.append(f"## 경험 카드 (사실 원장)\n{cards_text}")
    targets = []
    for q in state["analysis"].get("questions", []):
        lo, hi = length_target(q.get("limit") or 0)
        targets.append(f"- {q.get('question', '')[:60]} → {lo}~{hi}자" + ("" if q.get("limit") else " (제한 없음, 기본 목표)"))
    if targets:
        parts.append("## 분량 목표 (공백 포함)\n" + "\n".join(targets))
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


def _save_and_archive(rid: str, state: dict) -> None:
    save_state(rid, state)
    try:
        from .archive import save as save_archive
        save_archive(rid)
    except Exception:
        pass  # 보관 PDF가 실패해도 첨삭 결과는 남긴다


def _posting_block(state: dict) -> str:
    """인사담당자는 공고 문장을 그대로 인용해야 해서 분석 요약이 아니라 공고 원문을 같이 넘긴다."""
    return f"## 공고 원문 (posting_quote·requirement는 여기서 그대로 옮긴다)\n{state.get('posting', '')[:12000]}"


def _quoted(quote: str, source: str) -> bool:
    """인용 문구가 원문에 글자 그대로 있는지. 공백·문장부호 차이와 모델이 붙이는 '…'만 봐준다."""
    q = _norm(quote.replace("…", "")).replace("/", "")
    return bool(q) and q in source.replace("/", "")


def finding_key(f: dict) -> str:
    """'버리기' 체크를 같은 지적에 붙이려고 쓰는 짧은 열쇠."""
    return hashlib.sha1(f"{f.get('my_quote', '')}|{f.get('fix', '')}".encode("utf-8")).hexdigest()[:10]


def finish_hr(state: dict) -> dict:
    """인사담당자 결과 후처리 (호출 0번).

    - 7관점이 빠지면 '결과 없음'으로 채우고, 순서를 프롬프트의 관점 순서로 맞춘다
    - 내 서류 문장·공고 문장 인용이 원문에 실제로 있는지 코드가 대조해 *_ok로 남긴다
    - 먼저 고칠 3가지가 모자라면 지적 순서대로 채운다
    - 관점 지적을 violations에도 넣어 본문 노란 표시와 '지적대로 고치기'가 그대로 돌아가게 한다
    """
    hr = state.get("hr") or {}
    if "perspectives" not in hr:
        return state  # 예전 형식 결과는 건드리지 않는다
    mine = _norm(_answers_text(current_answers(state)) + "\n" + resume_text(state.get("resume") or {}))
    posting = _norm(state.get("posting", ""))
    by_name = {p.get("name", ""): p for p in hr.get("perspectives") or []}
    ordered = []
    for name, _ in HR_PERSPECTIVES:
        p = by_name.get(name) or {"name": name, "result": "결과 없음", "findings": []}
        p["findings"] = [f for f in p.get("findings") or [] if f.get("problem") or f.get("fix")]
        if p.get("result") != "결과 없음":
            p["result"] = "고칠 것 있음" if p["findings"] else "고칠 것 없음"
        for f in p["findings"]:
            f["my_ok"] = _quoted(f.get("my_quote", ""), mine)
            f["posting_ok"] = _quoted(f.get("posting_quote", ""), posting) if f.get("posting_quote") else None
            f["key"] = finding_key(f)
        ordered.append(p)
    hr["perspectives"] = ordered
    a = state.get("analysis") or {}
    hr["posting_match"] = [m for m in hr.get("posting_match") or [] if not m.get("from_analysis")]
    listed = _norm(" ".join(m.get("requirement", "") for m in hr["posting_match"]))
    for kind, items in (("자격요건", a.get("must") or []), ("우대사항", a.get("nice") or [])):
        for item in items:  # 모델이 빠뜨린 요건도 표에 남긴다 (빠진 걸 모르는 게 더 위험하다)
            words = [w for w in re.split(r"[\s·,/]+", item) if len(w) >= 2]
            if words and not all(_norm(w) in listed for w in words):
                hr.setdefault("posting_match", []).append(
                    {"requirement": item, "kind": kind, "status": "AI가 안 봄", "my_quote": "", "from_analysis": True})
    for m in hr.get("posting_match") or []:
        if m.get("from_analysis"):
            m["requirement_ok"] = None  # 분석 요약에서 온 항목이라 원문 대조를 하지 않는다
            continue
        m["requirement_ok"] = _quoted(m.get("requirement", ""), posting)
        m["my_ok"] = _quoted(m.get("my_quote", ""), mine) if m.get("my_quote") else None

    all_findings = [f | {"perspective": p["name"]} for p in ordered for f in p["findings"]]
    top = [t for t in hr.get("top3") or [] if t.get("fix") or t.get("my_quote")][:3]
    for t in top:  # 모델이 고른 항목을 관점 지적과 이어 붙여 인용 확인·버리기 열쇠를 같이 쓴다
        same = next((f for f in all_findings if f.get("my_quote") and f["my_quote"] == t.get("my_quote")), None)
        t["key"] = same["key"] if same else finding_key(t)
        t["my_ok"] = same["my_ok"] if same else _quoted(t.get("my_quote", ""), mine)
        if not t.get("problem"):
            t["problem"] = (same or {}).get("problem", "")
    for f in all_findings:
        if len(top) >= 3:
            break
        if f["key"] not in {t["key"] for t in top}:
            top.append({"perspective": f["perspective"], "my_quote": f.get("my_quote", ""), "fix": f.get("fix", ""),
                        "problem": f.get("problem", ""), "why_first": "", "key": f["key"], "my_ok": f["my_ok"]})
    hr["top3"] = top

    seen = {(v.get("sentence") or "") for v in hr.get("violations") or []}
    for f in all_findings:
        if f.get("my_quote") and f["my_quote"] not in seen:
            hr.setdefault("violations", []).append({"rule": f["perspective"], "question": f.get("question", ""),
                                                    "sentence": f["my_quote"], "why": f.get("problem", ""),
                                                    "fix_hint": f.get("fix", ""), "key": f["key"]})
            seen.add(f["my_quote"])
    for t in top:  # 먼저 고칠 3가지를 버리면 같은 문장의 기존 위반도 같이 빠지게 열쇠를 붙인다
        for v in hr.get("violations") or []:
            if t.get("my_quote") and v.get("sentence") == t["my_quote"]:
                v.setdefault("key", t["key"])
    state["hr"] = hr
    return state


def set_discarded(rid: str, keys: list[str]) -> None:
    """첨삭 화면에서 '내 경험과 달라 버리기'로 고른 지적을 저장한다."""
    state = load_state(rid)
    state["hr_discarded"] = sorted(set(keys))
    save_state(rid, state)


def rescore(rid: str, config: dict | None = None) -> dict:
    """인사담당자 첨삭 화면의 '다시 채점' (호출 1번). 직접 고친 뒤 점수가 어떻게 바뀌는지 본다."""
    state = load_state(rid)
    cards_text = cards_as_context(load_profile())
    state.setdefault("hr_history", []).append({k: state.get("hr", {}).get(k) for k in ("total", "verdict")}
                                              | {"at": datetime.now().isoformat(timespec="seconds")})
    state["hr"] = ask_json("judge", build_system_prompt("judge", state["analysis"]["subrole"]),
                           _payload(state, cards_text, current_answers(state), _posting_block(state)),
                           config=config, step="hr_rescore")
    finish_hr(state)
    state.pop("hr_applied", None)
    state.pop("hr_discarded", None)  # 새 결과에는 새로 고른다
    _save_and_archive(rid, state)
    return state


def apply_hr_feedback(rid: str, config: dict | None = None) -> dict:
    """인사담당자 첨삭 화면의 '지적대로 고치기' (호출 1번). 지적 사항만 고치고 새 사실은 만들지 않는다."""
    state = load_state(rid)
    hr = state.get("hr") or {}
    discarded = set(state.get("hr_discarded") or [])  # 화면에서 '내 경험과 달라 버리기'를 고른 지적
    found = [v for v in hr.get("violations", []) if v.get("key") not in discarded]
    found += [{"rule": "HR", "why": r} for r in hr.get("reasons", [])]
    if not found:
        return state
    cards_text = cards_as_context(load_profile())
    extra = (f"## 고칠 것 (인사담당자 지적, 이것만 고친다)\n{json.dumps(found, ensure_ascii=False)}\n\n"
             "## 첨삭 반영 규칙\n- 경험 카드에 없는 성과·수치·기간은 지어내지 말고 그 자리에 [확인 필요]를 그대로 남긴다. "
             "지원자가 나중에 직접 채운다.\n- 지원자가 버린 지적은 목록에 없다. 목록에 없는 문장은 고치지 않는다.")
    state["final"] = ask_json("writer", build_system_prompt("reviser", state["analysis"]["subrole"]),
                              _payload(state, cards_text, current_answers(state), extra),
                              config=config, temperature=0.4, step="hr_apply")
    state.setdefault("revisions", []).append({"after": "hr_apply", "changes": state["final"].get("changes", [])})
    _snapshot(state, "인사담당자 첨삭 반영")
    state["final_check"] = novel_sentences(current_answers(state), cards_text + "\n" + state["posting"])
    state["hr_applied"] = True  # 점수는 '다시 채점'을 눌러야 바뀐다
    _save_and_archive(rid, state)
    return state


# ── 단계 함수 ────────────────────────────────────────────────
# 단계마다 (state, ctx)를 받아 state를 고친다. LLM 호출은 모두 ask_json 하나를 거친다.
# 같은 입력이면 같은 경로로 가고, 단계 하나만 따로 시험하거나 나중에 그래프 노드로 감쌀 수 있다.
SCHEMA_VERSION = 2  # state.json 형식 버전 (형식이 바뀌면 올린다)


@dataclass
class Ctx:
    profile: object
    cards_text: str
    config: dict
    rid: str


def _subrole(state: dict) -> str:
    return state["analysis"]["subrole"]


def step_analyze(state: dict, ctx: Ctx) -> dict:
    titles = "\n".join(f"- [{c.id}] {c.kind} · {c.title} ({c.period})" for c in ctx.profile.cards)
    analysis = ask_json("writer", build_analyzer_prompt(),
                        f"## 공고 원문\n{state['posting'][:30000]}\n\n## 지원자 경험 요약 (적합도용)\n{titles}",
                        config=ctx.config, temperature=0.2, step="analyze")
    valid = {s for subs in GROUPS.values() for s in subs}
    if analysis.get("subrole") not in valid:  # 목록 밖 id면 내 희망 직무 첫 번째로
        analysis["subrole_why"] = (f"(분석 결과 '{analysis.get('subrole')}'가 목록에 없어 기본값 사용) "
                                   + str(analysis.get("subrole_why", "")))
        analysis["subrole"] = (ctx.profile.target_roles or ["ax_external"])[0]
    analysis["info"] = merge_info(analysis.get("info") or {}, state["posting"])
    state["analysis"] = analysis
    return state


def step_research(state: dict, ctx: Ctx) -> dict:
    if ctx.config.get("research", True):
        state["research"] = research(state["analysis"], state["posting"], state.get("extra_urls"), ctx.config,
                                     extra_text=state.get("extra_text", ""))
    return state


def step_draft(state: dict, ctx: Ctx) -> dict:
    state["draft"] = ask_json("writer", build_system_prompt("drafter", _subrole(state)),
                              _payload(state, ctx.cards_text), config=ctx.config, step="draft")
    _snapshot(state, "초안")
    return state


def step_checks(state: dict, ctx: Ctx) -> dict:
    others = _other_runs(ctx.rid)
    state["code_violations"] = run_checks(
        state["analysis"], {"answers": current_answers(state)}, ctx.profile.cards, ctx.cards_text,
        [r.get("analysis", {}).get("company", "") for r in others],
        [a.get("text", "") for r in others for a in current_answers(r)])
    return state


def step_verify(kind: str):
    def _go(state: dict, ctx: Ctx) -> dict:
        result = ask_json("judge", build_system_prompt(kind, _subrole(state)),
                          _payload(state, ctx.cards_text, current_answers(state)), config=ctx.config, step=kind)
        if kind == "verify_a":  # 사실성은 근거 문구를 코드가 원문과 글자 그대로 대조해서 판정한다
            found, score = grounding_violations(result.get("claims", []), ctx.cards_text + "\n" + state["posting"])
            result["violations"] = found + result.get("violations", [])
            result["score"] = score
        state[kind] = result
        return state
    return _go


def revise_with(state: dict, ctx: Ctx, found: list, label: str) -> dict:
    """위반 목록만 고친다. 위반이 없으면 호출하지 않는다."""
    if not found:
        return state
    before = {a.get("question", ""): len(a.get("text", "")) for a in current_answers(state)}
    extra = f"## 고칠 것 (이것만 고친다)\n{json.dumps(found, ensure_ascii=False)}"
    state["final"] = ask_json("writer", build_system_prompt("reviser", _subrole(state)),
                              _payload(state, ctx.cards_text, current_answers(state), extra),
                              config=ctx.config, temperature=0.4, step=label)
    # 수정 모델이 문장을 고치지 않고 지워서 글이 줄어드는 일이 많았다 (30명 시험 평균 -31%).
    # 15% 넘게 줄었거나 분량·제한을 못 맞추거나 같은 문장을 되풀이하면 한 번만 더 고친다.
    again = length_violations(state["analysis"], current_answers(state)) + repeated_sentences(current_answers(state))
    for a in current_answers(state):
        old = before.get(a.get("question", ""), 0)
        if old and len(a.get("text", "")) < old * 0.85 and not any(v["question"] == a.get("question") for v in again):
            again.append({"rule": "FC-4", "question": a.get("question", ""), "sentence": "",
                          "why": f"수정 전 {old}자에서 {len(a.get('text', ''))}자로 줄었다. 지운 자리를 카드 사실로 다시 채운다."})
    if again:
        first = state["final"].get("changes", [])
        state["final"] = ask_json("writer", build_system_prompt("reviser", _subrole(state)),
                                  _payload(state, ctx.cards_text, current_answers(state),
                                           f"## 고칠 것 (분량·반복만 맞춘다)\n{json.dumps(again, ensure_ascii=False)}"),
                                  config=ctx.config, temperature=0.4, step=f"{label}_length")
        state["final"]["changes"] = first + state["final"].get("changes", [])
    state.setdefault("revisions", []).append({"after": label, "changes": state["final"].get("changes", [])})
    _snapshot(state, label)
    return state


def step_revise(state: dict, ctx: Ctx) -> dict:
    found = (state.get("code_violations", []) + state.get("verify_a", {}).get("violations", [])
             + state.get("verify_b", {}).get("violations", []))
    return revise_with(state, ctx, found, "revise")


def step_revise_round(r: str):
    def _go(state: dict, ctx: Ctx) -> dict:
        found = state.get(r, {}).get("violations", []) + (state.get("code_violations", []) if r == "v1_fact" else [])
        return revise_with(state, ctx, found, f"revise_{r}")
    return _go


def step_resume(state: dict, ctx: Ctx) -> dict:
    base = base_resume(_subrole(state))
    extra = (f"## 기본 이력서 (순서·강조만 이 공고에 맞게 고친다)\n{json.dumps(base, ensure_ascii=False)}"
             if base else "## 기본 이력서 없음 — 경험 카드로 이 공고용 이력서를 새로 만든다.")
    extra += ("\n\n## 이력서 규칙\n- 이력서만 만든다. 자기소개서 답변이나 문항을 이력서 안에 넣지 않는다.\n"
              "- 항목은 짧은 사실 문장으로 쓰고, 카드에 없는 결과(복구했다, 안정화했다 등)를 붙이지 않는다.")
    state["resume"] = ask_json("writer", build_system_prompt("resume", _subrole(state)),
                               _payload(state, ctx.cards_text, extra=extra), config=ctx.config,
                               temperature=0.3, step="resume")
    return state


def step_hr(state: dict, ctx: Ctx) -> dict:
    state["hr"] = ask_json("judge", build_system_prompt("judge", _subrole(state)),
                           _payload(state, ctx.cards_text, current_answers(state), _posting_block(state)),
                           config=ctx.config, step="hr")
    return finish_hr(state)


def step_revise_2(state: dict, ctx: Ctx) -> dict:
    if (state["hr"].get("total") or 0) >= REVISE_2_BELOW:
        return state
    found = state["hr"].get("violations", []) + [{"rule": "HR", "why": r} for r in state["hr"].get("reasons", [])]
    return revise_with(state, ctx, found, "revise_2")


def step_final_check(state: dict, ctx: Ctx) -> dict:
    """최종본 코드 검사 (호출 0번). 남은 의심 문장은 화면에 표시해 사람이 확인하고, 사실 지표를 남긴다."""
    state["final_check"] = novel_sentences(current_answers(state), ctx.cards_text + "\n" + state["posting"])
    state["fact_report"] = fact_report(state, ctx.profile.cards)
    return state


STEP_FUNCS = {
    "analyze": step_analyze, "research": step_research, "draft": step_draft, "checks": step_checks,
    "verify_a": step_verify("verify_a"), "verify_b": step_verify("verify_b"), "revise": step_revise,
    "resume": step_resume, "hr": step_hr, "revise_2": step_revise_2, "final_check": step_final_check,
    **{r: step_verify(r) for r in PRECISE_ROUNDS}, **{f"revise_{r}": step_revise_round(r) for r in PRECISE_ROUNDS},
}
GATES = {"verify_b", *PRECISE_ROUNDS}  # '회차마다 확인'을 켜면 여기서 멈춘다


def run(posting_text: str, on_step=None, config: dict | None = None, mode: str | None = None,
        extra_urls: list[str] | None = None, stop_after: str | None = None,
        source_url: str = "", extra_text: str = "") -> dict:
    """공고 하나를 처리한다. on_step(step, state)는 진행 표시용. stop_after="analyze"면 적합도만 보고 멈춘다."""
    config = config or load_config()
    rid = run_id(posting_text)
    state = load_state(rid) or {"id": rid, "created": datetime.now().isoformat(timespec="seconds"),
                                "posting": posting_text, "done": [], "apply_status": "준비"}
    state["schema"] = SCHEMA_VERSION
    state["mode"] = mode or state.get("mode") or "normal"
    if extra_urls:
        state["extra_urls"] = extra_urls
    if source_url:
        state["source_url"] = source_url
    if extra_text.strip():
        state["extra_text"] = extra_text.strip()
    profile = load_profile()
    if not profile.cards:
        raise ValueError("경험 카드가 없습니다. '내 경험 정리'에서 먼저 카드를 만들어 주세요.")
    ctx = Ctx(profile=profile, cards_text=cards_as_context(profile), config=config, rid=rid)

    state["status"] = "running"
    state.pop("error", None)
    try:
        for name in steps_for(state["mode"]):
            if name in state["done"]:
                continue
            if name in ESSAY_STEPS and state.get("analysis", {}).get("format") == "resume_only":
                state["done"].append(name)  # 이력서만 받는 공고는 자소서 단계를 건너뛴다
                continue
            if on_step:
                on_step(name, state)
            state = STEP_FUNCS[name](state, ctx)
            state["done"].append(name)
            save_state(rid, state)
            if name == "analyze" and stop_after == "analyze":
                state["status"] = "screened"
                save_state(rid, state)
                return state
            if name in GATES and config.get("confirm_each_round") and name not in state.get("approvals", []):
                state["status"], state["waiting_at"] = "waiting", name
                raise WaitForApproval(name)
        state["status"] = "done"
        state.pop("waiting_at", None)
    except WaitForApproval:
        pass
    except Exception as e:  # 한도·장애로 멈추면 저장해 두고 다음에 이어서 한다
        state["status"] = "paused"
        state["error"] = str(e)[:500]
    save_state(rid, state)
    if state["status"] == "done":
        try:  # 다 쓰면 보관 PDF를 바로 남긴다 (실패해도 결과는 그대로 둔다)
            from .archive import save as save_archive
            save_archive(rid)
            state = load_state(rid)
        except Exception as e:
            state["archive_error"] = str(e)[:200]
    return state


def char_count(text: str) -> tuple[int, int]:
    """(공백 포함, 공백 제외) 글자 수"""
    return len(text), len(re.sub(r"\s", "", text))

"""관리자 메뉴의 '시험 데이터': 30명 실사용 시험 결과를 앱에서 둘러보는 폴더(data_test/)를 만든다.

AI를 다시 부르지 않는다 (호출 0번). 시험 때 저장한 결과를 그대로 옮기고,
근무 조건만 공고 원문의 고정 칸(접수기간·채용형태·급여·근무지역)을 코드로 읽어 채운다.
원본: data/eval/ws/<번호>/ (고친 뒤 2차) → 없거나 덜 끝났으면 data/eval/ws_v1/<번호>/ (1차)
"""
import json
import shutil
from pathlib import Path

from .paths import REAL, TEST

EVAL = REAL / "eval"


def available() -> bool:
    return (EVAL / "ws").exists()


def _pick(key: str) -> tuple[Path | None, str]:
    for folder, label in (("ws", "고친 뒤 (2차)"), ("ws_v1", "1차")):
        for f in (EVAL / folder / key / "runs").glob("*/state.json"):
            if json.loads(f.read_text(encoding="utf-8")).get("status") == "done":
                return f, label
    return None, ""


def build() -> dict:
    """data_test/를 새로 만든다. 돌려주는 값: {'runs': 개수, 'v2': 2차 개수, 'pdf': 보관 PDF 개수}"""
    from . import archive, db
    from .checks import merge_info
    from .paths import set_test

    if not available():
        raise FileNotFoundError("data/eval 시험 결과가 없어요. 30명 시험을 먼저 돌려야 해요.")
    if TEST.exists():
        shutil.rmtree(TEST)
    (TEST / "runs").mkdir(parents=True)
    personas = {p["pid"]: p for p in json.loads((EVAL / "ws" / "personas.json").read_text(encoding="utf-8"))}
    index = json.loads((EVAL / "postings" / "index.json").read_text(encoding="utf-8"))

    # 경험 카드는 인물마다 다르지만 화면에는 하나만 둘 수 있어, 첫 인물의 카드를 대표로 둔다
    profile = json.loads((EVAL / "ws" / index[0]["key"] / "profile.json").read_text(encoding="utf-8"))
    profile["name"] = "가상 인물 30명 (시험 데이터)"
    (TEST / "profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=1), encoding="utf-8")

    count = {"runs": 0, "v2": 0, "pdf": 0}
    set_test(True)  # 아래 저장·PDF·DB가 모두 data_test/로 가게 한다
    for p in index:
        src, label = _pick(p["key"])
        if not src:
            continue
        state = json.loads(src.read_text(encoding="utf-8"))
        state["analysis"]["info"] = merge_info(state["analysis"].get("info") or {}, state["posting"])
        if p["source"] == "lk":
            state["source_url"] = f"https://linkareer.com/activity/{p['id']}"
        else:
            state["source_url"] = f"https://www.haijob.co.kr/posting/{p['id']}"
        persona = personas.get(p["key"], {})
        state["test_note"] = f"{p['key']} · {persona.get('name', '')} · {label}"
        state["apply_status"] = "제출"  # 지원 현황 화면을 시험하려고 모두 제출로 둔다 (실제 제출 아님)
        state["applied_on"] = (state.get("created") or "")[:10]
        state.pop("pdf_path", None)
        d = TEST / "runs" / state["id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        db.sync(state)
        if archive.save(state["id"]):
            count["pdf"] += 1
        count["runs"] += 1
        count["v2"] += label.startswith("고친")
    return count

"""채용 사이트 지원서의 자소서 입력칸을 채운다 (PLAN 5단계).

    python -m core.site_filler <run_id> <지원서 URL>

원칙 (PLAN.md '채용 사이트 입력 자동화 원칙'):
- Windows 기본 Edge를 띄운다. 로그인·CAPTCHA·본인인증은 사용자가 그 창에서 직접 한다.
- 입력칸 주변 글(라벨·안내문)과 문항을 비교해 가장 비슷한 칸에만 채운다.
- 이미 내용이 있는 칸은 덮어쓰지 않는다.
- **제출·임시저장 같은 버튼은 절대 누르지 않는다.** 확인하고 누르는 것은 사용자 몫이다.
- 사이트마다 구조가 달라서 범용 방식(라벨 매칭)만 쓴다. 결과는 data/runs/<id>/site_fill.json에 남긴다.
"""
import json
import os
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

from core.paths import REAL, runs_dir

PROFILE_DIR = REAL / "browser_profile"  # 브라우저 로그인은 체험 모드에서도 실제 폴더
MATCH_MIN = 0.3
WAIT_LOGIN_SEC = 600
HEADLESS = os.getenv("RA_HEADLESS") == "1"  # 시험용: 창을 띄우지 않고 닫힐 때까지 기다리지 않는다

FIELDS_JS = """
() => [...document.querySelectorAll('textarea, input[type=text]:not([readonly])')]
  .filter(el => el.offsetParent !== null)
  .map((el, i) => {
    el.setAttribute('data-ra-idx', i);
    const byFor = el.id ? document.querySelector(`label[for="${el.id}"]`) : null;
    let ctx = [el.getAttribute('aria-label'), el.placeholder, el.name, byFor && byFor.innerText];
    let p = el.parentElement;
    for (let d = 0; d < 4 && p; d++, p = p.parentElement) {
      // 다른 입력칸까지 감싸는 상자에 닿으면 멈춘다 (남의 문항 글을 읽지 않게)
      if (p.querySelectorAll('textarea, input[type=text]').length > 1) break;
      const t = (p.innerText || '').trim();
      if (t.length > 4) { ctx.push(t.slice(0, 300)); break; }
    }
    return {idx: i, tag: el.tagName.toLowerCase(), value: el.value || '',
            maxlength: el.maxLength > 0 ? el.maxLength : 0,
            context: ctx.filter(Boolean).join(' | ')};
  })
"""


def _score(question: str, context: str) -> float:
    q, c = question[:80], context[:300]
    return max(SequenceMatcher(None, q, c).ratio(),
               SequenceMatcher(None, q[:25], c).find_longest_match(0, min(25, len(q)), 0, len(c)).size / max(1, min(25, len(q))))


def fill(run_id: str, url: str) -> dict:
    from playwright.sync_api import sync_playwright

    state = json.loads((runs_dir() / run_id / "state.json").read_text(encoding="utf-8"))
    answers = state.get("final", state.get("draft", {})).get("answers", [])
    report = {"url": url, "filled": [], "skipped": [], "not_found": []}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), channel="msedge", headless=HEADLESS)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url)
        print("브라우저에서 로그인하고 자기소개서 입력 화면까지 이동해 주세요. 입력칸이 보이면 자동으로 채웁니다.")
        deadline = time.time() + WAIT_LOGIN_SEC
        fields, frame_of = [], {}
        while time.time() < deadline:
            fields, frame_of = [], {}
            for frame in page.frames:
                try:
                    for f in frame.evaluate(FIELDS_JS):
                        f["key"] = f"{len(frame_of)}:{f['idx']}"
                        frame_of[f["key"]] = (frame, f["idx"])
                        fields.append(f)
                except Exception:
                    continue
            if any(f["tag"] == "textarea" for f in fields):
                break
            time.sleep(3)
        used = set()
        for ans in answers:
            q, text = ans.get("question", ""), ans.get("text", "")
            # 자소서 답변은 여러 줄 칸(textarea)에만 넣는다. 짧은 답만 한 줄 칸도 후보로 본다.
            pool = [f for f in fields if f["key"] not in used and (f["tag"] == "textarea" or len(text) < 150)]
            ranked = sorted(pool, key=lambda f: -_score(q, f["context"]))
            best = ranked[0] if ranked else None
            if not best or _score(q, best["context"]) < MATCH_MIN:
                report["not_found"].append(q)
                continue
            if best["value"].strip():
                report["skipped"].append({"question": q, "why": "이미 내용이 있어 덮어쓰지 않음"})
                used.add(best["key"])
                continue
            if best["maxlength"] and len(text) > best["maxlength"]:
                report["skipped"].append({"question": q, "why": f"칸 제한 {best['maxlength']}자 초과({len(text)}자)"})
                continue
            frame, idx = frame_of[best["key"]]
            frame.locator(f"[data-ra-idx='{idx}']").fill(text)
            used.add(best["key"])
            report["filled"].append({"question": q, "field": best["context"][:80]})
        (runs_dir() / run_id / "site_fill.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print("채운 내용을 확인하고, 임시저장·제출은 직접 눌러 주세요. 다 끝나면 브라우저를 닫으면 됩니다.")
        if not HEADLESS:
            try:
                page.wait_for_event("close", timeout=0)
            except Exception:
                pass
        ctx.close()
    return report


if __name__ == "__main__":
    fill(sys.argv[1], sys.argv[2])

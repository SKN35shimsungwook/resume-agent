"""작성 모델과 평가 모델을 나눠 부르는 래퍼.

같은 모델이 자기 글을 평가하면 점수를 후하게 주는 경향이 있어서, 글쓰기(writer)와
검증·인사담당자 평가(judge)를 서로 다른 제공자로 돌리는 것을 기본으로 한다.

하루 공고 30개를 처리하다 멈추지 않도록(docs/call-budget.md):
- 호출마다 시간 제한, 429·5xx·시간 초과는 점점 길게 기다리며 재시도
- 호출마다 data/usage.jsonl에 사용량 기록, 모델별 하루 상한을 넘기 전에 멈춤
- 한도가 차거나 계속 실패하면 설정한 예비 모델로 넘김
"""
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CONFIG_PATH = DATA_DIR / "config.json"
USAGE_PATH = DATA_DIR / "usage.jsonl"

DEFAULT_CONFIG = {
    # 기본은 무료 등급만 쓴다. 작성은 Gemini 3.5 Flash Lite, 평가는 세대가 다른 3.1 Flash Lite.
    # (Gemma 4 26B는 분당 토큰 1.6만이라 호출당 2~4분 걸려 예비로 내렸다 — 2026-11-03 비교)
    "writer": {"provider": "gemini", "model": "gemini-3.5-flash-lite"},
    "judge": {"provider": "gemini", "model": "gemini-3.1-flash-lite"},
    # 주 모델이 한도에 걸리거나 계속 실패할 때 넘길 모델 (비워 두면 넘기지 않음).
    # 유료 모델(OpenAI)은 자동으로 넘기지 않는다 — 크레딧을 아끼기 위해 직접 고를 때만 쓴다.
    "fallback": {
        "writer": {"provider": "gemini", "model": "gemini-3.1-flash-lite"},
        "judge": [{"provider": "gemini", "model": "gemini-3.5-flash-lite"},   # 빠른 예비 (혼잡할 때)
                  {"provider": "gemini", "model": "gemma-4-26b-a4b-it"}],     # 느리지만 한도가 넉넉한 예비
    },
    # 모델별 하루 호출 상한. 0이면 제한 없음. 실제 요금제 한도보다 조금 낮게 둔다.
    "daily_limits": {},
    # 모델별 분당 호출 상한. 넘을 것 같으면 호출 전에 기다린다 (Gemini 무료 등급 대비).
    "rpm_limits": {},
    "timeout_sec": 90,
    # 모델별 시간 제한(초). Gemma는 긴 입력에 90초를 넘길 때가 있다(504 실제 발생).
    "timeouts": {"gemma-4-26b-a4b-it": 240},
    "max_retries": 4,
    "gemini_api_key": "",
    "openai_api_key": "",
    "confirm_each_round": False,
}

RETRYABLE_CODES = {408, 429, 500, 502, 503, 504}


class BudgetExceeded(RuntimeError):
    """오늘 이 모델의 호출 상한에 도달했다."""


def load_config() -> dict:
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if CONFIG_PATH.exists():
        config.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    return config


def save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def _api_key(config: dict, provider: str) -> str:
    key = config.get(f"{provider}_api_key") or os.getenv(
        "GEMINI_API_KEY" if provider == "gemini" else "OPENAI_API_KEY", ""
    )
    if not key:
        raise ValueError(f"{provider} API 키가 없습니다. 설정 페이지에서 입력해주세요.")
    return key


# ── 사용량 기록 ───────────────────────────────────────────

def _log_usage(entry: dict) -> None:
    USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with USAGE_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def today_usage() -> dict:
    """오늘 모델별 {calls, ok, in_tokens, out_tokens}."""
    today = datetime.now().strftime("%Y-%m-%d")
    stats: dict[str, dict] = {}
    if not USAGE_PATH.exists():
        return stats
    for line in USAGE_PATH.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("date") != today or e.get("counted") is False:  # JSON 깨짐 기록은 호출 수에서 뺀다
            continue
        s = stats.setdefault(e["model"], {"calls": 0, "ok": 0, "in_tokens": 0, "out_tokens": 0})
        s["calls"] += 1
        s["ok"] += int(e.get("ok", False))
        s["in_tokens"] += e.get("in_tokens") or 0
        s["out_tokens"] += e.get("out_tokens") or 0
    return stats


def _check_budget(config: dict, model: str) -> None:
    limit = (config.get("daily_limits") or {}).get(model, 0)
    if limit and today_usage().get(model, {}).get("calls", 0) >= limit:
        raise BudgetExceeded(f"{model} 오늘 호출 상한({limit}회)에 도달했습니다.")


_recent_calls: dict[str, list[float]] = {}


def _wait_for_rpm(config: dict, model: str) -> None:
    """최근 60초 호출 수가 분당 상한에 닿았으면 자리가 날 때까지 기다린다."""
    limit = (config.get("rpm_limits") or {}).get(model, 0)
    if not limit:
        return
    calls = _recent_calls.setdefault(model, [])
    while True:
        now = time.time()
        calls[:] = [t for t in calls if now - t < 60]
        if len(calls) < limit:
            calls.append(now)
            return
        time.sleep(60 - (now - calls[0]) + 0.5)


# ── 호출 ──────────────────────────────────────────────────

def ask_json(
    role: str, system: str, prompt: str, config: dict | None = None,
    temperature: float | None = None, step: str = "",
) -> dict:
    """role은 'writer' 또는 'judge'. 응답은 JSON 객체로 받는다.

    temperature를 안 주면 작성은 0.6(문장 다양성), 평가는 0.2(채점 일관성).
    step은 사용량 기록에 남길 단계 이름(예: "extract", "verify_a").
    """
    config = config or load_config()
    if temperature is None:
        temperature = 0.6 if role == "writer" else 0.2
    specs = [config[role]]
    fallback = (config.get("fallback") or {}).get(role) or []
    for fb in (fallback if isinstance(fallback, list) else [fallback]):  # 예비는 하나 또는 여러 개(순서대로)
        if fb.get("provider") and fb.get("model") and fb != config[role]:
            specs.append(fb)

    last_error: Exception | None = None
    for spec in specs:
        try:
            # 무료 모델은 가끔 JSON을 깨뜨려 보낸다 → 같은 모델로 2번까지 다시 요청
            for parse_try in range(3):
                _check_budget(config, spec["model"])
                text = _call_with_retry(config, role, spec, system, prompt, temperature, step)
                try:
                    return _extract_json(text)
                except json.JSONDecodeError as e:
                    _log_usage({"ts": datetime.now().isoformat(timespec="seconds"),
                                "date": datetime.now().strftime("%Y-%m-%d"), "role": role, "step": step,
                                "provider": spec["provider"], "model": spec["model"], "ok": False,
                                "counted": False, "error": f"JSON 깨짐: {str(e)[:120]}"})
                    last_error = e
            raise RuntimeError(f"{spec['model']} 응답 JSON이 3번 연속 깨졌습니다: {last_error}")
        except (BudgetExceeded, RuntimeError) as e:
            last_error = e  # 다음(예비) 모델로 넘어간다
    raise RuntimeError(f"모든 모델 호출에 실패했습니다: {last_error}")


def _call_with_retry(config, role, spec, system, prompt, temperature, step) -> str:
    key = _api_key(config, spec["provider"])
    timeout = (config.get("timeouts") or {}).get(spec["model"], config.get("timeout_sec", 90))
    retries = config.get("max_retries", 4)
    for attempt in range(retries + 1):
        _wait_for_rpm(config, spec["model"])
        started = time.time()
        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "role": role, "step": step, "provider": spec["provider"], "model": spec["model"],
            "attempt": attempt,
        }
        try:
            if spec["provider"] == "gemini":
                text, usage = _ask_gemini(key, spec["model"], system, prompt, temperature, timeout)
            elif spec["provider"] == "openai":
                text, usage = _ask_openai(key, spec["model"], system, prompt, temperature, timeout)
            else:
                raise ValueError(f"알 수 없는 제공자: {spec['provider']}")
            _log_usage({**entry, "ok": True, "secs": round(time.time() - started, 1), **usage})
            return text
        except Exception as e:  # noqa: BLE001 — 제공자마다 예외 종류가 달라 코드로 판단한다
            code = _error_code(e)
            _log_usage({**entry, "ok": False, "secs": round(time.time() - started, 1),
                        "error": f"{code} {str(e)[:200]}"})
            # 시간 초과(504·408)·서버 혼잡(503)·서버 오류(500)는 같은 모델로 1번만 더 해 보고 예비 모델로 넘긴다
            if code not in RETRYABLE_CODES or attempt == retries or (code in (408, 500, 503, 504) and attempt >= 1):
                raise RuntimeError(f"{spec['model']} 호출 실패({code}): {str(e)[:300]}") from e
            # 2, 4, 8, 16초… 한도 초과(429)는 더 길게 쉰다
            time.sleep((2 ** (attempt + 1)) * (3 if code == 429 else 1))
    raise RuntimeError("재시도 횟수를 넘었습니다.")


def _error_code(e: Exception) -> int:
    for attr in ("code", "status_code"):
        value = getattr(e, attr, None)
        if isinstance(value, int):
            return value
    name = type(e).__name__.lower()
    if "timeout" in name or "timed out" in str(e).lower():
        return 408
    if "connection" in name:
        return 503
    return 0


def _ask_gemini(key, model, system, prompt, temperature, timeout) -> tuple[str, dict]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=timeout * 1000))
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            temperature=temperature,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )
    if response.candidates and str(response.candidates[0].finish_reason).endswith("MAX_TOKENS"):
        raise ValueError("AI 응답이 출력 길이 제한에 걸려 중간에 잘렸습니다. 다시 시도해주세요.")
    u = response.usage_metadata
    usage = {
        "in_tokens": getattr(u, "prompt_token_count", None),
        "out_tokens": (getattr(u, "candidates_token_count", 0) or 0) + (getattr(u, "thoughts_token_count", 0) or 0),
    }
    return response.text, usage


def _ask_openai(key, model, system, prompt, temperature, timeout) -> tuple[str, dict]:
    from openai import OpenAI

    client = OpenAI(api_key=key, timeout=timeout, max_retries=0)  # 재시도는 위에서 직접 한다
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=temperature,
    )
    usage = {"in_tokens": response.usage.prompt_tokens, "out_tokens": response.usage.completion_tokens}
    return response.choices[0].message.content, usage


def _extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            text = brace.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 문자열 안에 이스케이프 안 된 개행이 들어오는 경우가 있어 완화 모드로 재시도.
        return json.loads(text, strict=False)

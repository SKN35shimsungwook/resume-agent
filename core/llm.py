"""작성 모델과 평가 모델을 나눠 부르는 래퍼.

같은 모델이 자기 글을 평가하면 점수를 후하게 주는 경향이 있어서, 글쓰기(writer)와
검증·인사담당자 평가(judge)를 서로 다른 제공자로 돌리는 것을 기본으로 한다.
"""
import json
import os
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CONFIG_PATH = DATA_DIR / "config.json"

DEFAULT_CONFIG = {
    "writer": {"provider": "gemini", "model": "gemini-2.5-flash"},
    "judge": {"provider": "openai", "model": "gpt-4o-mini"},
    "gemini_api_key": "",
    "openai_api_key": "",
    "confirm_each_round": False,
}


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


def ask_json(role: str, system: str, prompt: str, config: dict | None = None) -> dict:
    """role은 'writer' 또는 'judge'. 응답은 JSON 객체로 받는다."""
    config = config or load_config()
    spec = config[role]
    key = _api_key(config, spec["provider"])
    if spec["provider"] == "gemini":
        text = _ask_gemini(key, spec["model"], system, prompt)
    elif spec["provider"] == "openai":
        text = _ask_openai(key, spec["model"], system, prompt)
    else:
        raise ValueError(f"알 수 없는 제공자: {spec['provider']}")
    return _extract_json(text)


def _ask_gemini(key: str, model: str, system: str, prompt: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            temperature=0.6,
        ),
    )
    if response.candidates and str(response.candidates[0].finish_reason).endswith("MAX_TOKENS"):
        raise ValueError("AI 응답이 출력 길이 제한에 걸려 중간에 잘렸습니다. 다시 시도해주세요.")
    return response.text


def _ask_openai(key: str, model: str, system: str, prompt: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    return response.choices[0].message.content


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

"""회사 리서치 (공고당 최대 1호출, 회사별 저장해 재사용).

무료 등급에서는 Gemini 3 이상 모델의 검색 그라운딩 한도가 0이라(AI Studio 확인) 검색 엔진을 쓰지 않는다.
대신 출처가 분명한 페이지만 읽는다: 공고 원문 + 공고에 적힌 홈페이지 + 사용자가 넣은 링크(회사 소개·기사·IR).
검색 엔진 결과를 긁지 않는 것은 약관·차단 문제를 피하려는 선택이다.
"""
import json
import re
from pathlib import Path
from urllib.parse import quote

from .llm import ask_json
from .loaders import load_url
from .prompts import build_system_prompt

from .paths import research_cache_dir


def _slug(company: str) -> str:
    return re.sub(r"[^\w가-힣]+", "_", company).strip("_") or "unknown"


def search_links(company: str) -> dict[str, str]:
    """사용자가 직접 열어 볼 검색 링크 (앱이 긁지는 않는다)."""
    q = quote(company)
    return {
        "네이버 뉴스": f"https://search.naver.com/search.naver?where=news&query={q}",
        "구글": f"https://www.google.com/search?q={q}+%ED%9A%8C%EC%82%AC+%EC%86%8C%EA%B0%9C",
        "잡플래닛": f"https://www.jobplanet.co.kr/search?query={q}",
        "DART 공시": f"https://dart.fss.or.kr/dsab007/main.do?textCrpNm={q}",
    }


def cached(company: str) -> dict | None:
    path = research_cache_dir() / f"{_slug(company)}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def research(analysis: dict, posting_text: str, extra_urls: list[str] | None = None,
             config: dict | None = None, refresh: bool = False) -> dict:
    company = analysis.get("company") or "unknown"
    if not refresh and (hit := cached(company)):
        return hit
    sources = [("공고 원문", posting_text[:12000])]
    urls = [u for u in [analysis.get("homepage", ""), *(extra_urls or [])] if u and u.startswith("http")]
    for url in dict.fromkeys(urls):
        try:
            sources.append((url, load_url(url)[:8000]))
        except Exception as e:  # 열리지 않는 페이지는 건너뛴다
            sources.append((url, f"(열지 못함: {str(e)[:80]})"))
    body = "\n\n".join(f"## 출처: {name}\n{text}" for name, text in sources)
    result = ask_json("writer", build_system_prompt("researcher", analysis["subrole"]),
                      f"## 회사: {company}\n## 지원 직무: {analysis.get('position', '')}\n\n{body}",
                      config=config, temperature=0.2, step="research")
    result["sources"] = list(dict.fromkeys([*(result.get("sources") or []), *[n for n, _ in sources]]))
    research_cache_dir().mkdir(parents=True, exist_ok=True)
    (research_cache_dir() / f"{_slug(company)}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result

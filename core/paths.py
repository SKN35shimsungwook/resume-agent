"""데이터 폴더 위치. 체험 모드에서는 가상 데이터 폴더(data_demo/)를 쓴다.

체험 모드를 켜도 API 키·설정(data/config.json), 사용량 기록(data/usage.jsonl),
브라우저 로그인(data/browser_profile)은 실제 폴더를 그대로 쓴다. 무료 한도는 하나라서다.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REAL = ROOT / "data"
DEMO = ROOT / "data_demo"
FLAG = REAL / ".demo_mode"


def demo_on() -> bool:
    # 시험 스크립트는 RA_WORKSPACE=real(실제 폴더) 또는 폴더 경로로 체험 모드 여부와 상관없이 그 폴더를 쓴다
    if os.getenv("RA_WORKSPACE"):
        return False
    return FLAG.exists()


def set_demo(on: bool) -> None:
    REAL.mkdir(parents=True, exist_ok=True)
    if on:
        FLAG.write_text("on", encoding="utf-8")
    elif FLAG.exists():
        FLAG.unlink()


def workspace() -> Path:
    ws = os.getenv("RA_WORKSPACE")
    if ws and ws != "real":
        return Path(ws)
    return DEMO if demo_on() else REAL


def runs_dir() -> Path:
    return workspace() / "runs"


def base_resume_dir() -> Path:
    return workspace() / "base_resumes"


def profile_path() -> Path:
    return workspace() / "profile.json"


def research_cache_dir() -> Path:
    return workspace() / "research_cache"


def reference_dir() -> Path:
    return workspace() / "reference"


def angles_path() -> Path:
    return workspace() / "angles.md"

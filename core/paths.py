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
TEST = ROOT / "data_test"  # 관리자 메뉴의 '시험 데이터 보기' (가상 인물 30명 × 실제 공고 30개)
TEST_FLAG = REAL / ".test_mode"


def demo_on() -> bool:
    # 시험 스크립트는 RA_WORKSPACE=real(실제 폴더) 또는 폴더 경로로 체험 모드 여부와 상관없이 그 폴더를 쓴다
    if os.getenv("RA_WORKSPACE"):
        return False
    return FLAG.exists()


def set_demo(on: bool) -> None:
    REAL.mkdir(parents=True, exist_ok=True)
    if on:
        if TEST_FLAG.exists():
            TEST_FLAG.unlink()
        FLAG.write_text("on", encoding="utf-8")
    elif FLAG.exists():
        FLAG.unlink()


def test_on() -> bool:
    return not os.getenv("RA_WORKSPACE") and TEST_FLAG.exists()


def set_test(on: bool) -> None:
    REAL.mkdir(parents=True, exist_ok=True)
    if on:
        set_demo(False)  # 체험과 시험 데이터는 동시에 켜지 않는다
        TEST_FLAG.write_text("on", encoding="utf-8")
    elif TEST_FLAG.exists():
        TEST_FLAG.unlink()


def workspace() -> Path:
    ws = os.getenv("RA_WORKSPACE")
    if ws and ws != "real":
        return Path(ws)
    if test_on():
        return TEST
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

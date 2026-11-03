"""지원 현황 DB (SQLite, data/resume.db).

원본은 공고마다의 state.json이고, 이 DB는 날짜·회사로 찾아보기 위한 색인이다.
state를 저장할 때마다 sync()가 회사·공고·지원 기록 세 표를 맞춘다. 지워져도 rebuild()로 다시 만든다.
나중에 다른 기기에서 보려고 서버 DB(TiDB 등)로 옮길 때는 이 파일만 바꾸면 된다.
"""
import json
import sqlite3
from datetime import date

from .paths import workspace

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    name TEXT PRIMARY KEY, industry TEXT, size TEXT, founded TEXT, locations TEXT,
    homepage TEXT, summary TEXT, profile_json TEXT, compare_json TEXT, sources TEXT, updated TEXT
);
CREATE TABLE IF NOT EXISTS postings (
    run_id TEXT PRIMARY KEY, company TEXT, position TEXT, subrole TEXT, url TEXT,
    employment TEXT, deadline TEXT, salary TEXT, location TEXT, hours TEXT, benefits TEXT, headcount TEXT,
    fit INTEGER, info_json TEXT, created TEXT
);
CREATE TABLE IF NOT EXISTS applications (
    run_id TEXT PRIMARY KEY, company TEXT, position TEXT, status TEXT, applied_on TEXT,
    work_status TEXT, hr_total INTEGER, verdict TEXT, pdf_path TEXT, created TEXT, updated TEXT
);
"""


def connect() -> sqlite3.Connection:
    path = workspace() / "resume.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def _val(info: dict, key: str) -> str:
    item = info.get(key) or {}
    return item.get("value", "") if isinstance(item, dict) else str(item)


def sync(state: dict) -> None:
    a = state.get("analysis") or {}
    if not a.get("company"):
        return  # 분석 전이면 색인할 것이 없다
    info, res, hr = a.get("info") or {}, state.get("research") or {}, state.get("hr") or {}
    prof = res.get("company_profile") or {}
    with connect() as con:
        if res:
            con.execute(
                "INSERT INTO companies VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET "
                "industry=excluded.industry, size=excluded.size, founded=excluded.founded, locations=excluded.locations, "
                "homepage=excluded.homepage, summary=excluded.summary, profile_json=excluded.profile_json, "
                "compare_json=excluded.compare_json, sources=excluded.sources, updated=excluded.updated",
                (a["company"], prof.get("industry", ""), prof.get("size", ""), prof.get("founded", ""),
                 ", ".join(prof.get("locations") or []), a.get("homepage", ""), res.get("summary", ""),
                 json.dumps(prof, ensure_ascii=False), json.dumps(res.get("compare") or [], ensure_ascii=False),
                 " · ".join(res.get("sources") or []), state.get("updated", "")))
        con.execute(
            "INSERT OR REPLACE INTO postings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (state["id"], a["company"], a.get("position", ""), a.get("subrole", ""), state.get("source_url", ""),
             _val(info, "employment"), _val(info, "deadline"), _val(info, "salary"), _val(info, "location"),
             _val(info, "hours"), _val(info, "benefits"), _val(info, "headcount"),
             (a.get("fit") or {}).get("score"), json.dumps(info, ensure_ascii=False), state.get("created", "")))
        con.execute(
            "INSERT OR REPLACE INTO applications VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (state["id"], a["company"], a.get("position", ""), state.get("apply_status", "준비"),
             state.get("applied_on", ""), state.get("status", ""), hr.get("total"), hr.get("verdict", ""),
             state.get("pdf_path", ""), state.get("created", ""), state.get("updated", "")))


def rebuild() -> int:
    """runs/ 폴더의 모든 결과로 DB를 다시 채운다 (기존 결과 옮기기·DB가 지워졌을 때)."""
    from .pipeline import list_runs
    runs = list_runs()
    for r in runs:
        sync(r)
    return len(runs)


def applications() -> list[dict]:
    """지원 현황 화면용: 지원 기록 + 공고 조건 + 회사 정보를 한 줄로."""
    with connect() as con:
        rows = con.execute(
            "SELECT a.*, p.url, p.employment, p.deadline, p.salary, p.location, p.hours, p.benefits, p.headcount, "
            "p.fit, p.subrole, c.industry, c.size, c.locations AS company_locations "
            "FROM applications a LEFT JOIN postings p USING(run_id) LEFT JOIN companies c ON c.name = a.company "
            "ORDER BY COALESCE(NULLIF(a.applied_on, ''), a.created) DESC").fetchall()
    return [dict(r) for r in rows]


def company(name: str) -> dict | None:
    with connect() as con:
        row = con.execute("SELECT * FROM companies WHERE name = ?", (name,)).fetchone()
    return dict(row) if row else None


def days_left(deadline: str) -> int | None:
    try:
        return (date.fromisoformat(deadline[:10]) - date.today()).days
    except ValueError:
        return None

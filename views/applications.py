"""내 지원 현황: 언제 어느 회사에 냈는지, 그 회사·공고가 어떤 곳이었는지 한눈에 본다."""
import csv
import io
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from core import db, ui
from core.pipeline import APPLY_STATUSES, load_state

ui.back_link()
st.markdown("## 📋 내 지원 현황")
st.caption("공고를 처리하면 자동으로 쌓여요. 상태를 '제출'로 바꾼 날이 지원일이 되고, 보관 PDF도 그 날짜로 저장돼요.")

rows = db.applications()
if not rows and db.rebuild():  # 예전 결과가 있으면 처음 한 번 DB로 옮긴다
    rows = db.applications()
if not rows:
    st.info("아직 처리한 공고가 없어요. '회사 맞춤 작성'에서 공고를 넣어 보세요.")
    st.stop()

today = date.today()
week_start = today - timedelta(days=today.weekday())
submitted = [r for r in rows if r["applied_on"]]
soon = [r for r in rows if r["status"] == "준비" and (d := db.days_left(r["deadline"] or "")) is not None and 0 <= d <= 3]
ui.tiles([
    ("오늘 제출", f"{sum(r['applied_on'] == today.isoformat() for r in submitted)}건"),
    ("이번 주 제출", f"{sum(r['applied_on'] >= week_start.isoformat() for r in submitted)}건"),
    ("전체 제출", f"{len(submitted)}건"),
    ("마감 3일 안 (미제출)", f"{len(soon)}건"),
])

with st.container(border=True, key="card_filter"):
    c1, c2, c3 = st.columns([2, 2, 3])
    status = c1.multiselect("상태", APPLY_STATUSES, placeholder="전체")
    period = c2.selectbox("기간", ["전체", "오늘", "이번 주", "최근 30일"])
    query = c3.text_input("회사·직무 검색", placeholder="예: LG CNS, 설비")


def in_period(r) -> bool:
    day = r["applied_on"] or (r["created"] or "")[:10]
    return {"전체": True, "오늘": day == today.isoformat(), "이번 주": day >= week_start.isoformat(),
            "최근 30일": day >= (today - timedelta(days=30)).isoformat()}[period]


shown = [r for r in rows if (not status or r["status"] in status) and in_period(r)
         and (not query or query.lower() in f"{r['company']} {r['position']}".lower())]


def d_day(r) -> str:
    d = db.days_left(r["deadline"] or "")
    return "" if d is None else ("마감" if d < 0 else f"D-{d}")


table = [{
    "지원일": r["applied_on"] or f"({(r['created'] or '')[:10]} 작성)",
    "회사": r["company"], "직무": r["position"], "상태": r["status"], "마감": d_day(r) or r["deadline"] or "",
    "급여": r["salary"] or "-", "근무지": r["location"] or r["company_locations"] or "-",
    "고용": r["employment"] or "-", "점수": r["hr_total"], "판정": r["verdict"] or "",
} for r in shown]
st.markdown(f"**{len(shown)}건**")
st.dataframe(table, hide_index=True, width="stretch",
             column_config={"점수": st.column_config.ProgressColumn("점수", min_value=0, max_value=100, format="%d")})

buf = io.StringIO()
if table:
    w = csv.DictWriter(buf, fieldnames=list(table[0]))
    w.writeheader()
    w.writerows(table)
st.download_button("⬇ 엑셀용 CSV 받기", buf.getvalue().encode("utf-8-sig"), file_name=f"지원현황_{today}.csv",
                   mime="text/csv")

# ── 한 곳 자세히 ─────────────────────────────────────────
st.markdown("### 자세히 보기")
labels = {f"{t['지원일']} · {r['company']} · {r['position']}": r for t, r in zip(table, shown)}
if labels:
    pick = labels[st.selectbox("공고 고르기", list(labels), label_visibility="collapsed")]
    with st.container(border=True, key="card_detail"):
        ui.tiles([("상태", pick["status"]), ("점수", f"{pick['hr_total'] or '-'}"), ("적합도", f"{pick['fit'] or '-'}"),
                  ("마감", d_day(pick) or pick["deadline"] or "-")])
        st.markdown(f"**근무 조건** — 고용: {pick['employment'] or '-'} · 급여: {pick['salary'] or '공고에 없음'} · "
                    f"근무지: {pick['location'] or '-'} · 근무 시간: {pick['hours'] or '-'}  \n"
                    f"복지: {pick['benefits'] or '-'} · 모집 인원: {pick['headcount'] or '-'}")
        if pick["url"]:
            st.markdown(f"공고 링크: {pick['url']}")
        comp = db.company(pick["company"])
        if comp:
            st.markdown(f"**회사** — {comp['summary'] or ''}  \n위치: {comp['locations'] or '-'} · 업종: {comp['industry'] or '-'}"
                        f" · 규모: {comp['size'] or '-'}")
        hr = load_state(pick["run_id"]).get("hr") or {}
        if hr:
            st.markdown(f"**인사담당자 평가 — {hr.get('total', '-')}점 · {hr.get('verdict', '-')}**")
            if hr.get("scores"):
                st.dataframe([{"평가 기준": s.get("item", ""), "점수": f"{s.get('score', '')}/{s.get('max', '')}",
                               "근거": s.get("evidence", "")} for s in hr["scores"]], hide_index=True, width="stretch")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**지적 사항**")
                for x in hr.get("reasons", []) or ["없음"]:
                    st.markdown(f"- {x}")
            with c2:
                st.markdown("**예상 면접 질문**")
                for i, q in enumerate(hr.get("interview_questions", []) or ["없음"], 1):
                    st.markdown(f"{i}. {q}")
        others = [r for r in rows if r["company"] == pick["company"] and r["run_id"] != pick["run_id"]]
        if others:
            st.caption("같은 회사 다른 지원: " + " · ".join(f"{o['position']} ({o['applied_on'] or o['status']})" for o in others))
        pdf = pick["pdf_path"]
        if pdf and Path(pdf).exists():
            st.download_button("⬇ 보관 PDF (자소서·면접 질문·평가 전부)", Path(pdf).read_bytes(), file_name=Path(pdf).name)
            st.caption(f"`{pdf}`")
        else:
            st.caption("보관 PDF가 아직 없어요. '회사 맞춤 작성' → 내보내기 탭에서 만들 수 있어요.")
        st.page_link("views/write.py", label="이 공고의 자소서 보기·고치기 →")

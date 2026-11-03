"""화면 공통 조각: 헤더, 단계 표시, 지표 타일, 카드 스타일."""
import streamlit as st

CSS = """
<style>
.block-container { max-width: 900px; padding-top: 1.6rem; }
[data-testid="stHeader"] { background: transparent; }

/* 테두리 있는 컨테이너 = 흰 카드 */
/* key가 card로 시작하는 컨테이너 = 흰 카드 */
[class*="st-key-card"] {
  background: #fff; border: none !important; border-radius: 18px;
  box-shadow: 0 2px 14px rgba(27, 35, 51, .06); padding: 1.3rem 1.4rem;
}
[data-testid="stPageLink-NavLink"] p { color: #2F6BFF; font-weight: 700; }

/* 업로드 영역: 점선 박스 */
[data-testid="stFileUploaderDropzone"] {
  background: #FAFBFE; border: 2px dashed #C9D3E6; border-radius: 14px; padding: 2rem 1rem;
}

.ra-header { display:flex; justify-content:space-between; align-items:center; margin-bottom: 1.4rem; }
.ra-logo { display:flex; align-items:center; gap:10px; font-weight:800; font-size:1.15rem; color:#1B2333; }
.ra-logo-mark { width:34px; height:34px; border-radius:9px; background:#2F6BFF; color:#fff;
  display:flex; align-items:center; justify-content:center; font-size:1.05rem; }
.ra-badge { background:#E6F6EC; color:#1FA34A; font-size:.8rem; font-weight:700;
  padding:6px 12px; border-radius:999px; }
.ra-badge-demo { background:#FFF4D6; color:#B7791F; }

.ra-steps { display:flex; align-items:center; gap:10px; margin: .2rem 0 1.1rem; flex-wrap: wrap; }
.ra-step { display:flex; align-items:center; gap:8px; font-size:.88rem; font-weight:700; color:#5B6475; }
.ra-step-num { width:24px; height:24px; border-radius:50%; display:flex; align-items:center;
  justify-content:center; font-size:.78rem; color:#fff; background:#C3CAD6; }
.ra-step.done .ra-step-num { background:#1FA34A; }
.ra-step.now .ra-step-num { background:#2F6BFF; }
.ra-step.now { color:#1B2333; }
.ra-step-line { width:26px; height:1px; background:#DDE3EE; }

.ra-tiles { display:grid; grid-template-columns: repeat(4, 1fr); gap:10px; margin:.4rem 0 .8rem; }
.ra-tile { background:#F4F6FA; border-radius:12px; padding:12px 14px; }
.ra-tile-label { font-size:.78rem; color:#6B7385; }
.ra-tile-value { font-size:1.35rem; font-weight:800; color:#1B2333; margin-top:2px; }
@media (max-width: 640px) { .ra-tiles { grid-template-columns: repeat(2, 1fr); } }

.ra-card-icon { font-size: 2rem; line-height: 1; margin-bottom: .5rem; }
.ra-card-title { font-size: 1.12rem; font-weight: 800; color:#1B2333; margin-bottom:.3rem; }
.ra-card-desc { font-size: .88rem; color:#5B6475; min-height: 4.4em; }
.ra-soon { display:inline-block; font-size:.72rem; font-weight:700; color:#8A93A5;
  background:#EEF1F6; padding:2px 8px; border-radius:999px; margin-left:6px; vertical-align: middle; }
.ra-mini-title { font-weight:800; font-size:.9rem; color:#1B2333; }
.ra-mini-desc { font-size:.82rem; color:#5B6475; margin-top:2px; }
.ra-footer { text-align:center; font-size:.78rem; color:#8A93A5; margin-top:2.2rem; }
</style>
"""


def page_setup() -> None:
    from .paths import demo_on

    st.html(CSS)
    badge = ('<div class="ra-badge ra-badge-demo">🧪 체험 모드 · 가상 데이터</div>' if demo_on()
             else '<div class="ra-badge">🔒 내 자료는 이 PC에만 저장돼요</div>')
    st.html(
        f"""
        <div class="ra-header">
          <div class="ra-logo"><div class="ra-logo-mark">✓</div>맞춤 자소서 에이전트</div>
          {badge}
        </div>
        """
    )


def back_link() -> None:
    st.page_link("views/home.py", label="처음으로", icon=":material/arrow_back:")


def steps(labels: list[str], current: int) -> None:
    """current는 1부터. 앞 단계는 완료(초록), 현재는 파랑."""
    parts = []
    for i, label in enumerate(labels, start=1):
        state = "done" if i < current else "now" if i == current else ""
        if i > 1:
            parts.append('<div class="ra-step-line"></div>')
        parts.append(
            f'<div class="ra-step {state}"><div class="ra-step-num">{i}</div>{label}</div>'
        )
    st.html(f'<div class="ra-steps">{"".join(parts)}</div>')


def tiles(items: list[tuple[str, str]]) -> None:
    cells = "".join(
        f'<div class="ra-tile"><div class="ra-tile-label">{label}</div>'
        f'<div class="ra-tile-value">{value}</div></div>'
        for label, value in items
    )
    st.html(f'<div class="ra-tiles">{cells}</div>')


def footer() -> None:
    from .paths import demo_on

    if demo_on():
        st.html('<div class="ra-footer">체험 모드: 가상 데이터는 data_demo 폴더에 있고, 실제 내 데이터는 그대로 보관돼요.</div>')
        return
    st.html(
        '<div class="ra-footer">자료는 data 폴더에만 저장되고, AI를 부를 때만 필요한 내용이 '
        "설정한 AI 서비스로 전송됩니다.</div>"
    )



def show_analysis(state: dict) -> None:
    """공고·회사 자료를 분석한 결과를 사람이 읽기 좋게 보여 준다 (작성 화면 아래쪽과 '회사·공고' 탭에서 같이 쓴다)."""
    from .checks import INFO_FIELDS
    from .research import search_links

    a, res = state.get("analysis") or {}, state.get("research") or {}
    if not a:
        st.caption("아직 분석 전이에요.")
        return
    fit = a.get("fit") or {}
    tiles([("회사", a.get("company") or "-"), ("직무", (a.get("position") or "-")[:18]),
           ("적합도", f"{fit.get('score', '-')}점"), ("자소서 문항", f"{len(a.get('questions') or [])}개")])

    st.markdown("**📄 공고에서 읽은 것**")
    st.markdown(f"- 세부 직무: `{a.get('subrole', '')}` — {a.get('subrole_why', '')}")
    for label, key in (("주요 업무", "duties"), ("필수 요건", "must"), ("우대 사항", "nice"), ("키워드", "keywords"),
                       ("인재상", "talent")):
        if a.get(key):
            st.markdown(f"- {label}: " + ", ".join(map(str, a[key])))
    for q in a.get("questions") or []:
        st.markdown(f"  - 문항: {q.get('question', '')}" + (f" ({q['limit']}자)" if q.get("limit") else " (글자 수 제한 없음)"))

    info = a.get("info") or {}
    if info:
        st.markdown("**💼 근무 조건** (공고 원문에서 근거를 찾은 것만)")
        st.table({"항목": list(INFO_FIELDS.values()),
                  "내용": [(info.get(k) or {}).get("value")
                         or (f"⚠️ 확인 필요 ('{info[k]['dropped']}' — 공고에서 근거 못 찾음)" if (info.get(k) or {}).get("dropped")
                             else "공고에 없음") for k in INFO_FIELDS],
                  "공고 원문 근거": [(info.get(k) or {}).get("quote", "") for k in INFO_FIELDS]})

    st.markdown("**🎯 나와 맞는 정도**")
    st.markdown(f"{fit.get('why', '')}  \n강점: {', '.join(fit.get('strengths') or []) or '-'}  \n"
                f"부족: {', '.join(fit.get('gaps') or []) or '-'}")

    if not res:
        st.caption("회사 리서치는 자소서를 쓰기 시작하면 해요. (적합도만 보기에서는 아직 안 해요)")
        return
    prof = res.get("company_profile") or {}
    st.markdown("**🏢 회사 정보**")
    if res.get("summary"):
        st.markdown(res["summary"])
    st.table({"항목": ["위치", "업종", "규모", "설립", "주요 사업", "주요 제품", "주요 고객"],
              "내용": [", ".join(prof.get("locations") or []) or "-", prof.get("industry") or "-", prof.get("size") or "-",
                     prof.get("founded") or "-", ", ".join(res.get("business") or []) or "-",
                     ", ".join(res.get("products") or []) or "-", ", ".join(prof.get("main_customers") or []) or "-"]})
    if res.get("compare"):
        st.markdown("**🔍 공고 내용과 회사 자료 비교**")
        st.table({"항목": [c.get("item", "") for c in res["compare"]], "공고": [c.get("posting", "") for c in res["compare"]],
                  "회사 자료": [c.get("company", "") for c in res["compare"]],
                  "비교": [c.get("match", "") for c in res["compare"]]})
    if res.get("role_challenges"):
        st.markdown("**🧩 이 직무가 풀어야 할 과제** (자소서 지원 동기에 쓰여요)")
        for ch in res["role_challenges"]:
            st.markdown(f"- {ch.get('challenge', '')} *({ch.get('source', '')})*")
    st.markdown("**📚 읽은 자료**")
    for s in res.get("read") or [{"name": n, "ok": True} for n in res.get("sources", [])]:
        mark = "✅" if s.get("ok", True) else "❌ 열지 못함"
        ref = " · 참고용 (자소서 근거로는 안 씀)" if s.get("reference_only") else ""
        size = f" · {s['chars']:,}자" if s.get("chars") else ""
        st.markdown(f"- {mark} {s.get('name', '')}{size}{ref}" + (f"  \n  {s['note']}" if s.get("note") else ""))
    if any(not s.get("ok", True) for s in res.get("read") or []):
        st.caption("안 열린 페이지는 내용을 복사해 '회사 자료 붙여넣기' 칸에 넣고 다시 시작하면 반영돼요.")
    if a.get("company"):
        st.markdown("직접 찾아볼 곳: " + " · ".join(f"[{k}]({v})" for k, v in search_links(a["company"]).items()))

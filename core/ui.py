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


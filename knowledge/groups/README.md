# 직무군 프롬프트

직무군 6개 × 세부 직무 19개. 근거는 직무군 6개 서류 평가 기준 조사 보고서(2026-11-02). 지원자 경력이 들어 있어 비공개 `data/research/`에 보관한다.

| 파일 | 직무군 | 세부 직무 id |
|---|---|---|
| `ai_consulting.md` | ① AI 컨설팅 | `ax_external` 외부 AX 컨설턴트 · `ax_manufacturing` 제조 AX 컨설턴트 · `dx_inhouse` 사내 DX/AX 담당 |
| `tech_sales.md` | ② 기술영업 | `it_sales` IT·SW 기술영업 · `presales` 프리세일즈 · `electric_sales` 전기·에너지 장비 기술영업 · `b2b_sales` 일반 B2B 영업 |
| `field_equipment.md` | ③ 현장 설비 | `fse_cs` 장비사 FSE·CS·셋업 · `production_equipment` 생산설비 엔지니어 · `factory_electrical` 공장 전기·생산직 |
| `smart_factory.md` | ④ 융합 | `smart_factory_dx` 스마트팩토리(제조사 DX·IIoT) · `mes` MES 엔지니어 · `manufacturing_ax` 제조 AX 엔지니어 |
| `electrical_construction.md` | ⑤ 전기 시공 | `electrician` 건축 전기 기능직 · `interior_electric` 인테리어 전기 · `electrical_pm` 전기 공무·시공관리 |
| `startup_dev.md` | ⑥ 개발 | `fullstack` 주니어 풀스택 · `backend` 백엔드 · `ai_app` AI 애플리케이션 |

## 파일 구조

각 파일은 `<!-- part: 이름 -->` 주석으로 나뉘고, `core/prompts.py`가 단계별로 필요한 부분만 꺼낸다.

| part | 쓰는 에이전트 | 내용 |
|---|---|---|
| `overview` | 전부 | 직무군이 하는 일, 핵심 증거 문법, AI 경험의 무게 |
| `hard_filters` | 매처 | 지원 전에 반드시 확인할 요건 |
| `matcher` | 매처 | 공통 키워드 + 세부 직무별 덮어쓸/낮출 키워드 |
| `writer` | 작성기·수정기 | 증거 문법, 반드시 할 것, 금지 표현 |
| `resume` | 이력서 작성기 | 세부 직무별 이력서 항목 순서 |
| `judge` | 인사담당자 | 세부 직무별 100점 채점표 |

## 주의

- **채점표 배점은 전부 추정**이다. 기업이 공개한 서류 배점표는 6개 직무군 어디에서도 찾지 못했다. 절대 점수가 아니라 직무군 안의 상대 우선순위로 쓴다.
- 실제 공고가 들어오면 **공고의 자격요건·우대사항이 이 파일보다 우선**한다.
- 개인 경력에 맞춘 "내 이야기 각도"는 공개 저장소에 두지 않고 `data/angles.md`에 둔다.

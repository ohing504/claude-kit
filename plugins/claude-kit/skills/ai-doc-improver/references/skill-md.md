---
topic: SKILL.md 특화 개선 점검 — ai-doc-improver 타입별 가이드
absorbed-from: skill-creator (Anthropic 공식), anthropics-claude-code plugin-dev/skill-development (점검 휴리스틱 흡수, 내용 창작·eval 메커니즘은 제외)
---

# SKILL.md 특화 점검

대상이 SKILL.md일 때 범용 점검에 *더해* 적용한다.

## 추가 삭제 신호

- **body에 "언제 쓰는지" 설명** → `description` 프론트매터가 트리거 SSOT. body에 "~같은 요청에 쓴다" 류가 있고 description에도 동일 내용이면 body에서 **삭제**. description이 없는 경우엔 description으로 **이동**.
- **2인칭 표현** ("사용자는 ~해야 한다", "you should ~", "당신은") → 명령형으로 **변환** ("~한다", "~읽는다"). 스킬 body는 AI에게 주는 지시라 2인칭이 노이즈.
- **references/ 파일이 있는데 body에 언급 없음** → 미사용 레퍼런스. 실제로 필요 없으면 **삭제**, 필요하면 body에 언제·왜 읽는지 **pointer 추가**.
- **responsibility 서술이 본문에 묻힘** → 한다/안 한다 경계가 흩어져 있으면 **책임 경계 섹션으로 통합**. 없애는 게 아니라 모으는 것.

## 누락 플래그 — 플래그만, 추가는 사용자 확인

아래 항목이 없으면 *플래그*한다. 채울 내용은 사용자가 정한다.

- **`argument-hint` 없음** — body에 "경로", "URL", "파일", "인자", "폴더"를 받는 흐름이 있는데 프론트매터에 `argument-hint`가 없으면 플래그. 자동완성 힌트 부재.
- **`$ARGUMENTS` 미활용** — `argument-hint`가 있는데 body에 `$ARGUMENTS` 처리(경로·명령 바로 사용 or 타입 검증 후 분기) 없음. 힌트와 body가 불일치.
- **Edge Cases 섹션 없음** — 워크플로우가 3단계 이상이거나 실패 모드·예외 입력이 본문에 흩어져 있으면 플래그. 에러 케이스를 한 곳에서 찾을 수 없음.
- **책임 경계 없음** — 스킬 범위가 광범위하거나 다른 스킬·도구와 겹치는 영역이 있는데 "한다/안 한다"가 명시되지 않으면 플래그.
- **description 트리거 부실** — description이 단순 기능 서술이고 구체적인 트리거 문구("~해줘", "~하고 싶어" 류)가 없으면 플래그. 스킬 undertriggering의 주원인.

## stale 플래그 — 플래그만, 수정은 사용자 확인

- body에서 언급한 `references/`, `scripts/` 파일 경로가 실제로 없음 (broken pointer)
- `scripts/` 안 스크립트를 body에서 호출하는데 시그니처·플래그명이 달라짐
- `allowed-tools` / `tools` 목록에 있는 도구가 body 워크플로우에서 실제로 쓰이지 않음 (또는 반대)

## SKILL.md 전용 잣대

범용 점검의 "본문이 비대 → references/ 외부화" 규칙에 **예외**가 있다:

- **매 실행마다 참조하는 흐름·규칙은 인라인 유지.** 실행 중 Read가 추가로 필요한 내용을 외부화하면 비용이 생긴다. 외부화 대상은 *선택적으로* 참조하는 부가 정보(특정 도메인 가이드, 고급 패턴 등)에 한정.
- **body 길이 기준**: 500줄 이하 / 5,000단어 이하가 이상적. 초과 시 references/ 분리를 제안하되, 매 실행 필요 여부로 판단.

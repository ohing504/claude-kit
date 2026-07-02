---
topic: SKILL.md 특화 개선 점검 — ai-doc-improver 타입별 가이드
absorbed-from: skill-creator (Anthropic 공식 SKILL.md·references/schemas.md·scripts/quick_validate.py·agents/analyzer), Agent Skills best-practices 공식 문서 (점검 휴리스틱 흡수, 내용 창작·eval 메커니즘은 제외)
---

# SKILL.md 특화 점검

대상이 SKILL.md일 때 범용 점검에 *더해* 적용한다.

## 프론트매터·형식 하드 검사 — 기계적으로 100% 잡히는 것부터

정규식·길이·키 검사로 확정 판정 가능한 항목. 아래 하드 규칙은 공식 `quick_validate.py` 기준(위반 시 로드 실패), best-practice 규칙은 실패는 아니나 플래그.

- **`name` 형식** (하드) — `^[a-z0-9-]+$` 위반(대문자·공백·언더스코어), `--` 포함, 선행/후행 하이픈, 64자 초과 → 로드 실패. best-practice 추가 플래그: name에 `<>` 포함, 예약어 `anthropic`·`claude` 포함, `-v2`·`-new`·`-final` 버전 접미사(업데이트는 같은 name 유지).
- **미허용 프론트매터 최상위 키** (하드) — 허용 집합 밖 키는 로드 실패. platform 허용: `name`·`description`·`license`·`allowed-tools`·`metadata`·`compatibility` (`metadata` 하위 키는 자유). Claude Code 확장 허용: `+when_to_use`·`disable-model-invocation`·`argument-hint`·`user-invocable`·`model` 등. `version`·`author`·`tags`처럼 확장 밖이면 플래그.
- **`description` 하드 한도** (하드) — 비어있음, 1024자 초과, `<`/`>`(angle bracket) 포함 중 하나면 로드 실패(초과분 런타임 truncate). Claude Code 맥락이면 `description`+`when_to_use` 합산 1536자 초과도 플래그. (기존 '트리거 부실' 신호는 *내용* 축, 이건 *형식 상한*.)
- **`compatibility` 초과** (하드) — 500자 초과 시 실패.

## 추가 삭제 신호

- **body에 "언제 쓰는지" 설명** → `description` 프론트매터가 트리거 SSOT. body에 "~같은 요청에 쓴다" 류가 있고 description에도 동일 내용이면 body에서 **삭제**. description이 없는 경우엔 description으로 **이동**.
- **body의 2인칭 표현** ("사용자는 ~해야 한다", "you should ~", "당신은") → 명령형으로 **변환** ("~한다", "~읽는다"). 스킬 body는 AI에게 주는 지시라 2인칭이 노이즈.
- **description의 1·2인칭** ("I can help you ~", "you can use this ~", "~해드립니다") → 3인칭 서술로 **변환** ("Processes ~", "~를 점검한다"). *대상 구분*: body는 명령형, description은 3인칭 트리거 서술 — POV 불일치는 discovery(트리거)를 망친다.
- **references/ 파일이 있는데 body에 언급 없음** → 미사용 레퍼런스. 실제로 필요 없으면 **삭제**, 필요하면 body에 언제·왜 읽는지 **pointer 추가**.
- **references 중첩(2단계 참조)** → SKILL.md가 가리키는 참조 파일이 *SKILL.md에 직접 링크되지 않은* 또 다른 참조 파일을 링크하면 플래그. 참조는 SKILL.md에서 1단계로 평탄화 — Claude가 참조를 `head -100`로 부분만 읽어 하위 참조를 놓친다.
- **시간 민감 정보** → 'Old patterns' 접이식(`<details>`) 블록 밖에 날짜 조건부 서술("~년 ~월 이전/이후", "as of <date>", 특정 월-연도 명시)이 있으면 플래그. 폐기 가이드는 접이식 Old patterns 섹션으로 이동(본문은 현재 시점만).
- **교체 가능 옵션 과다 나열** → 같은 작업용 대체 라이브러리·도구를 "X, 또는 Y, 또는 Z…" 식으로 3개 이상 나열하면 플래그. 기본값 1개 + escape hatch(이탈구) 한 줄로 축약.
- **responsibility 서술이 본문에 묻힘** → 한다/안 한다 경계가 흩어져 있으면 **책임 경계 섹션으로 통합**. 없애는 게 아니라 모으는 것.
- **검증 규칙이 여러 단계에 미러링** → 같은 체크리스트·기준이 생성 단계·자체검수·하위 에이전트 프롬프트에 복제되면, 규칙 하나 추가가 모든 사본 동기화를 강제한다. 기준 SSOT 한 곳("규칙 → 강제 수단 → 심각도" 매핑)을 두고 각 단계는 **참조**하게. (단일 정의가 여러 적용 결과를 낳는 관계는 위반 아님 — 독립 갱신되는 사본만 위반.)
  - **강제 수단(기계 검사 vs 판단) 미표시** → linter·검증 스크립트가 잡는 규칙을 본문에 prose로 재서술하면, 무엇이 자동 강제이고 무엇이 사람·모델 판단인지 흩어져 예측이 안 된다. 기계 검사가 잡는 규칙은 본문에서 *그 사실만* 가리키고, 기계화 가능한 prose 규칙은 자동화 백로그로 분류.
  - **하위 에이전트 프롬프트 자급자족 강박** → 격리 컨텍스트라 self-contained로 채우려다 본체 규칙과 미러링이 생긴다. sub-agent도 SSOT 파일을 Read하게 한다(격리라도 파일 접근은 된다); 프롬프트엔 그 작업 고유 데이터만 둔다.

## 누락 플래그 — 플래그만, 추가는 사용자 확인

아래 항목이 없으면 *플래그*한다. 채울 내용은 사용자가 정한다.

- **`argument-hint` 없음** — body에 "경로", "URL", "파일", "인자", "폴더"를 받는 흐름이 있는데 프론트매터에 `argument-hint`가 없으면 플래그. 자동완성 힌트 부재.
- **`$ARGUMENTS` 미활용** — `argument-hint`가 있는데 body에 `$ARGUMENTS` 처리(경로·명령 바로 사용 or 타입 검증 후 분기) 없음. 힌트와 body가 불일치.
- **Edge Cases 섹션 없음** — 워크플로우가 3단계 이상이거나 실패 모드·예외 입력이 본문에 흩어져 있으면 플래그. 에러 케이스를 한 곳에서 찾을 수 없음.
- **책임 경계 없음** — 스킬 범위가 광범위하거나 다른 스킬·도구와 겹치는 영역이 있는데 "한다/안 한다"가 명시되지 않으면 플래그.
- **description 트리거 부실** — description이 단순 기능 서술이고 구체적인 트리거 문구("~해줘", "~하고 싶어" 류)가 없으면 플래그. 스킬 undertriggering의 주원인.
- **모호 지시 문구** — body에 "적절히"·"필요에 따라"·"알아서"·"~를 (적절히) 처리한다" 류가 인접한 번호·열거 단계 없이 나오면 플래그. 명시적 단계 부재는 head-to-head 패배의 최상위 원인 — 명시적 번호 단계로 대체 제안.
- **스크립트 실행/참조 의도 미표기** — `scripts/` 파일이 body에서 언급되는데 인접에 실행(Run/실행) 또는 참조(See/읽는다) 동사가 없으면 플래그(실행인지 읽을 레퍼런스인지 모호 → 즉흥 재작성 유발). `scripts/` 파일이 존재하는데 body에서 전혀 언급 안 되면(미사용) 플래그 — references 미사용 신호를 scripts로 확장.
- **부작용 스킬 자동트리거 미차단** (Claude Code) — body가 배포·커밋·전송·삭제·결제 등 되돌리기 어려운 부작용을 수행하는데 프론트매터에 `disable-model-invocation: true`가 없으면 플래그.
- **제네릭 `name`** — `name`이 denylist(`helper`·`utils`·`tools`·`documents`·`data`·`files`)에 있거나 순수 제네릭 명사면 플래그. gerund(동사+-ing, `processing-pdfs`)·동작 명사구 권장(형식 위반은 아니므로 flag-only).

## stale 플래그 — 플래그만, 수정은 사용자 확인

- body에서 언급한 `references/`, `scripts/` 파일 경로가 실제로 없음 (broken pointer)
- `scripts/` 안 스크립트를 body에서 호출하는데 시그니처·플래그명이 달라짐
- `allowed-tools` / `tools` 목록에 있는 도구가 body 워크플로우에서 실제로 쓰이지 않음 (또는 반대)
- **파일명·경로 위생** — 번들 파일명이 제네릭 패턴(`docN`·`fileN`·`untitled`·`temp`)이라 내용을 안 드러내거나, body 경로에 역슬래시 구분자(`scripts\helper.py`)가 있으면 플래그. 파일명은 내용 기반 서술형(`form_validation_rules.md`), 경로는 항상 forward slash.

## SKILL.md 전용 잣대

범용 점검의 "본문이 비대 → references/ 외부화" 규칙에 **예외**와 **보완**이 있다:

- **매 실행마다 참조하는 흐름·규칙은 인라인 유지.** 실행 중 Read가 추가로 필요한 내용을 외부화하면 비용이 생긴다. 외부화 대상은 *선택적으로* 참조하는 부가 정보(특정 도메인 가이드, 고급 패턴 등)에 한정.
- **body 비대 신호**: 토큰 밀도가 낮고 선택적 참조 정보(특정 도메인 가이드·고급 패턴)가 핵심 흐름과 섞여 있으면 `references/` 외부화를 제안. 분리 기준은 줄 수가 아니라 *매 실행 참조 여부* — 핵심 흐름은 인라인 유지, 선택적 부가 정보만 외부화.
- **body 절대 상한** — 위 "줄 수는 중립" 원칙과 *별개로*, 프론트매터 제외 body가 500줄 또는 ~5k 토큰을 넘으면 SKILL.md 전용 천장 신호. 줄이 많아서가 아니라 progressive disclosure Level 2 예산 초과라 — 계층 하나 더(references 외부화)와 명확한 포인터를 제안. (참조빈도 규칙은 *무엇을* 외부화할지, 이 천장은 *언제라도* 분해 신호.)
- **긴 참조 파일 TOC 없음** — 번들된 `.md` 참조 파일이 100줄을 넘는데 상단에 목차/Contents 섹션이 없으면 플래그. Claude가 부분 읽기할 때 전체 범위를 못 봐 정보 누락.
- **근거 없는 대문자 명령** (프레이밍) — `ALWAYS`·`NEVER`·`MUST`·`DO NOT` 전량 대문자가 인접한 근거("because ~"·"~이므로") 없이 군집하면 플래그. 경직된 명령보다 *이유 동반 재프레이밍*을 제안(범용 점검의 "긍정형 지시 > 대조 예시 > 짧은 금지" 우선순위와 정합).

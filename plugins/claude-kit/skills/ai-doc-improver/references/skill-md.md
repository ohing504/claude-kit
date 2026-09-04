---
topic: SKILL.md 특화 개선 점검 — ai-doc-improver 타입별 가이드
absorbed-from: skill-creator (Anthropic 공식 SKILL.md, references/schemas.md, scripts/quick_validate.py, agents/analyzer), Agent Skills best-practices 공식 문서 (점검 휴리스틱 흡수, 내용 창작과 eval 메커니즘은 제외)
also-absorbed-from: Claude Code 스킬 문서 code.claude.com/docs/en/skills (프론트매터 필드표, 문자열 치환, 동적 컨텍스트 주입)
---

# SKILL.md 특화 점검

대상이 SKILL.md일 때 범용 점검에 *더해* 적용한다.

## 프론트매터와 형식 하드 검사 — 기계적으로 확정되는 것부터

정규식, 길이, 키 검사로 확정 판정할 수 있는 항목이다. 아래 (하드) 표시는 공식 `quick_validate.py` 기준이며, 이 검증은 외부 배포 경로에서 돌아 위반 시 실패한다. Claude Code 자체는 더 관대해서 모르는 키를 무시하고 로드하므로, 규격에 어긋난 프론트매터가 조용히 무효가 된 채 남는다. best-practice 규칙은 실패는 아니지만 플래그한다.

- **`name` 형식** (하드) — `^[a-z0-9-]+$` 위반(대문자, 공백, 언더스코어), `--` 포함, 선행이나 후행 하이픈, 64자 초과면 로드에 실패한다. best-practice 추가 플래그: name에 `<>` 포함, 예약어 `anthropic`과 `claude` 포함, `-v2`나 `-new`나 `-final` 같은 버전 접미사(업데이트는 같은 name을 유지한다).
- **프론트매터 최상위 키** — Claude Code가 받는 키는 `name`, `description`, `when_to_use`, `argument-hint`, `arguments`, `disable-model-invocation`, `user-invocable`, `allowed-tools`, `disallowed-tools`, `model`, `effort`, `context`, `agent`, `background`, `hooks`, `paths`, `shell`, `metadata`, `license`, `compatibility`다. 이 밖의 키는 조용히 무시되므로 로드는 되지만 아무 효과가 없다 — 특히 도구 선언을 `tools`로 쓴 스킬은 선언이 무효다. `allowed-tools`(권한 프롬프트 없이 허용)와 `disallowed-tools`(사용 차단) 중 어느 의도였는지 확인받고 옮길 후보로 플래그한다. `version`, `author`, `tags`도 같은 이유로 플래그한다.
- **외부 배포 경로 상한** (하드) — claude.ai 업로드, Skills API, `package_skill.py`로 배포하는 스킬은 `name`, `description`, `license`, `allowed-tools`, `metadata`, `compatibility`만 받고 나머지 키가 있으면 업로드가 에러로 실패한다(`Unexpected key(s) in SKILL.md frontmatter`). Claude Code 안에서만 쓰는 스킬이면 해당 없다.
- **`argument-hint` 값이 따옴표 없이 `[`로 시작** — YAML이 리스트로 해석하고 표시할 때 문자열로 변환하므로 대괄호가 사라진다. `argument-hint: "[--auto] [<pr#>]"`처럼 감싸도록 제안한다.
- **`$1`을 첫 인자로 사용** — 스킬 치환은 `$0`이 첫 인자, `$1`이 두 번째다(단일 파일 command의 `$1`과 다르다). 인자를 하나만 받는 스킬이 body에서 `$1`을 읽으면 항상 빈 값이므로 플래그한다. 위치 대신 이름으로 받으려면 `arguments` 프론트매터에 이름을 선언하고 body에서 `$name`으로 쓴다.
- **`description` 하드 한도** (하드) — 비어 있음, 1024자 초과, `<`나 `>`(angle bracket) 포함 중 하나면 로드에 실패한다(초과분은 런타임에서 truncate). Claude Code 맥락이면 `description`과 `when_to_use` 합산 1536자 초과도 플래그한다. (기존 '트리거 부실' 신호는 *내용* 점검이고, 이것은 *형식 상한*이다.)
- **`compatibility` 초과** (하드) — 500자 초과 시 실패한다.

## 추가 삭제 신호

- **body에 "언제 쓰는지" 설명** → 트리거의 정본은 `description` 프론트매터다. body에 "~같은 요청에 쓴다" 류가 있고 description에도 같은 내용이 있으면 body에서 **삭제**한다. description이 없으면 description으로 **이동**한다.
- **body의 2인칭 표현** ("사용자는 ~해야 한다", "you should ~", "당신은") → 명령형으로 **변환**한다("~한다", "~읽는다"). 스킬 body는 AI에게 주는 지시라 2인칭이 노이즈다.
- **description의 1인칭과 2인칭** ("I can help you ~", "you can use this ~", "~해드립니다") → 3인칭 서술로 **변환**한다("Processes ~", "~를 점검한다"). *대상 구분*: body는 명령형, description은 3인칭 트리거 서술이다 — 시점이 어긋나면 트리거 발동이 망가진다.
- **references/ 파일이 있는데 body에 언급 없음** → 미사용 레퍼런스다. 실제로 필요 없으면 **삭제**하고, 필요하면 body에 언제 왜 읽는지 **pointer를 추가**한다.
- **references 중첩(2단계 참조)** → SKILL.md가 가리키는 참조 파일이 *SKILL.md에 직접 링크되지 않은* 또 다른 참조 파일을 링크하면 플래그한다. 참조는 SKILL.md에서 1단계로 평탄화한다 — Claude가 참조를 `head -100`으로 부분만 읽어 하위 참조를 놓친다.
- **시간 민감 정보** → 'Old patterns' 접이식(`<details>`) 블록 밖에 날짜 조건부 서술("~년 ~월 이전이나 이후", "as of <date>", 특정 월-연도 명시)이 있으면 플래그한다. 폐기 가이드는 접이식 Old patterns 섹션으로 옮기고 본문에는 현재 시점만 남긴다.
- **교체 가능한 옵션 과다 나열** → 같은 작업용 대체 라이브러리나 도구를 "X, 또는 Y, 또는 Z…" 식으로 3개 이상 나열하면 플래그한다. 기본값 하나와 예외 상황 한 줄로 줄인다.
- **한다/안 한다 경계가 본문에 흩어짐** → **책임 경계 섹션으로 통합**한다. 없애는 게 아니라 모으는 것이다.
- **검증 규칙이 여러 단계에 복제됨** → 같은 체크리스트와 기준이 생성 단계, 자체 검수, 하위 에이전트 프롬프트에 복제되면 규칙 하나를 추가할 때 모든 사본을 동기화해야 한다. "규칙 → 강제 수단 → 심각도" 매핑을 담은 정본 한 곳을 두고 각 단계는 그것을 **참조**하게 한다. (단일 정의가 여러 적용 결과를 낳는 관계는 위반이 아니다 — 독립적으로 갱신되는 사본만 위반이다.)
  - **강제 수단(기계 검사인지 판단인지) 미표시** → linter나 검증 스크립트가 잡는 규칙을 본문에 산문으로 다시 서술하면, 무엇이 자동 강제이고 무엇이 사람과 모델의 판단인지 흩어져 예측이 안 된다. 기계 검사가 잡는 규칙은 본문에서 *그 사실만* 가리키고, 기계화할 수 있는 산문 규칙은 자동화 백로그로 분류한다.
  - **하위 에이전트 프롬프트를 자급자족으로 채우려는 시도** → 격리된 컨텍스트라 self-contained로 채우려다 본체 규칙과 사본이 생긴다. sub-agent도 정본 파일을 Read하게 한다(격리돼도 파일 접근은 된다). 프롬프트에는 그 작업 고유 데이터만 둔다.

## 누락 플래그 — 플래그만 하고, 추가는 사용자 확인

아래 항목이 없으면 *플래그*한다. 채울 내용은 사용자가 정한다.

- **`argument-hint` 없음** — body에 "경로", "URL", "파일", "인자", "폴더"를 받는 흐름이 있는데 프론트매터에 `argument-hint`가 없으면 플래그한다. 자동완성 힌트가 없는 상태다.
- **`$ARGUMENTS` 미활용** — `argument-hint`가 있는데 body에 `$ARGUMENTS` 처리(경로나 명령을 바로 사용하거나 타입 검증 후 분기)가 없다. 힌트와 body가 불일치한다.
- **힌트에 없는 인자를 body가 읽음** — body가 `--auto` 같은 플래그나 두 번째 인자를 해석하는데 `argument-hint`에 안 적혀 있으면 플래그한다. 사용자는 자동완성에 보이는 것만 입력한다. 인자가 둘 이상이면 `$ARGUMENTS[0]`, `$ARGUMENTS[1]`로 위치를 나누거나 `arguments` 프론트매터로 이름을 준다.
- **Edge Cases 섹션 없음** — 워크플로우가 3단계 이상이거나 실패 모드와 예외 입력이 본문에 흩어져 있으면 플래그한다. 에러 케이스를 한 곳에서 찾을 수 없는 상태다.
- **책임 경계 없음** — 스킬 범위가 넓거나 다른 스킬 및 도구와 겹치는 영역이 있는데 "한다/안 한다"가 명시되지 않으면 플래그한다.
- **description 트리거 부실** — description이 단순 기능 서술이고 구체적인 트리거 문구("~해줘", "~하고 싶어" 류)가 없으면 플래그한다. 스킬이 발동되지 않는 주원인이다.
- **모호한 지시 문구** — body에 "적절히", "필요에 따라", "알아서", "~를 (적절히) 처리한다" 류가 인접한 번호나 열거 단계 없이 나오면 플래그한다. 명시적 단계가 없는 것이 head-to-head 비교에서 패배하는 최상위 원인이다 — 명시적 번호 단계로 대체를 제안한다.
- **스크립트를 실행할지 참조할지 미표기** — `scripts/` 파일이 body에서 언급되는데 인접에 실행(Run, 실행)이나 참조(See, 읽는다) 동사가 없으면 플래그한다(실행인지 읽을 레퍼런스인지 모호해 즉흥 재작성을 유발한다). `scripts/` 파일이 존재하는데 body에서 전혀 언급되지 않으면(미사용) 플래그한다 — references 미사용 신호를 scripts로 확장한 것이다.
- **부작용 스킬 자동 트리거 미차단** (Claude Code) — body가 배포, 커밋, 전송, 삭제, 결제처럼 되돌리기 어려운 부작용을 수행하는데 프론트매터에 `disable-model-invocation: true`가 없으면 플래그한다.
- **제네릭 `name`** — `name`이 denylist(`helper`, `utils`, `tools`, `documents`, `data`, `files`)에 있거나 순수 제네릭 명사면 플래그한다. gerund(동사+-ing, `processing-pdfs`)나 동작 명사구를 권장한다(형식 위반은 아니므로 플래그만 한다).

## stale 플래그 — 플래그만 하고, 수정은 사용자 확인

- body에서 언급한 `references/`, `scripts/` 파일 경로가 실제로 없음 (broken pointer)
- `scripts/` 안 스크립트를 body에서 호출하는데 시그니처나 플래그명이 달라짐
- `allowed-tools` 목록에 있는 도구가 body 워크플로우에서 실제로 쓰이지 않음 (또는 그 반대)
- **`allowed-tools`의 Bash 규칙이 body의 명령 표기와 안 맞음** — 규칙은 `Bash(${CLAUDE_SKILL_DIR}/scripts/x.sh *)`인데 body는 `scripts/x.sh`로 호출하면 규칙이 매칭되지 않아 사전 승인이 무효가 된다. 규칙과 body 표기 중 어느 쪽을 맞출지 확인받고 플래그한다. 되돌리기 어려운 동작(삭제, 전송, 결제)을 하는 스크립트는 규칙에서 빼 권한 프롬프트를 남기는 쪽이 안전하다.
- **`` !`명령` ``으로 주입하는 컨텍스트가 `allowed-tools`에 없음** — body 상단 Context 블록의 명령은 스킬 로드 시 먼저 실행되므로, 대응 규칙이 없으면 매 실행마다 권한 프롬프트가 뜬다.
- **파일명과 경로 위생** — 번들 파일명이 제네릭 패턴(`docN`, `fileN`, `untitled`, `temp`)이라 내용을 안 드러내거나, body 경로에 역슬래시 구분자(`scripts\helper.py`)가 있으면 플래그한다. 파일명은 내용을 드러내는 서술형(`form_validation_rules.md`), 경로는 항상 forward slash로 쓴다.

## SKILL.md 전용 기준

범용 점검의 "본문이 김 → references/ 외부화" 규칙에 **예외**와 **보완**이 있다.

- **매 실행마다 참조하는 흐름과 규칙은 인라인으로 유지한다.** 실행 중 Read가 추가로 필요한 내용을 외부화하면 비용이 생긴다. 외부화 대상은 *선택적으로* 참조하는 부가 정보(특정 도메인 가이드, 고급 패턴)에 한정한다.
- **body가 길다는 신호**: 토큰 밀도가 낮고 선택적 참조 정보(특정 도메인 가이드, 고급 패턴)가 핵심 흐름과 섞여 있으면 `references/` 외부화를 제안한다. 분리 기준은 줄 수가 아니라 *매 실행 참조 여부*다 — 핵심 흐름은 인라인으로 두고 선택적 부가 정보만 외부화한다.
- **body 절대 상한** — 위 "줄 수는 판단 기준이 아니다" 원칙과 *별개로*, 프론트매터를 뺀 body가 500줄 또는 약 5k 토큰을 넘으면 SKILL.md 전용 상한 신호다. 줄이 많아서가 아니라 progressive disclosure Level 2 예산을 넘겨서다 — 계층을 하나 더 두고(references 외부화) 명확한 pointer를 붙이도록 제안한다. (참조 빈도 규칙은 *무엇을* 외부화할지 정하고, 이 상한은 *언제라도* 분해하라는 신호다.)
- **긴 참조 파일에 목차 없음** — 번들된 `.md` 참조 파일이 100줄을 넘는데 상단에 목차나 Contents 섹션이 없으면 플래그한다. Claude가 부분만 읽을 때 전체 범위를 못 봐 정보를 놓친다.
- **근거 없는 대문자 명령** (프레이밍) — `ALWAYS`, `NEVER`, `MUST`, `DO NOT` 같은 전량 대문자가 인접한 근거("because ~", "~이므로") 없이 몰려 있으면 플래그한다. 경직된 명령보다 *이유를 함께 적은 재프레이밍*을 제안한다(범용 점검의 "긍정형 지시 > 대조 예시 > 짧은 금지" 우선순위와 맞춘다).

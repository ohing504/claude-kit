---
name: browser-session
description: patchright 또는 playwright에서 launch_persistent_context로 로그인 세션을 프로파일 디렉토리에 저장·재사용하는 패턴 가이드. 세션 유효성 체크(쿠키·네비게이션), headless=false 로그인 대기 루프, 실행 중 만료 감지·재인증까지 Python/JS 양쪽 코드 템플릿으로 제공한다. "patchright 세션 저장", "로그인 상태 유지 크롤링", "persistent context profiles", "매번 로그인 안 하게", "세션 재사용", "세션 만료 처리", "브라우저 프로파일 관리" 같은 맥락이면 반드시 참조한다. 로그인이 필요한 사이트를 크롤링·스크래핑하거나 로그인 세션이 필요한 브라우저 자동화를 구현·리뷰·리팩터링할 때 이 가이드를 먼저 확인한다.
tools: Bash, Read, Edit, Write
---

# Browser Session — Persistent Context 세션 관리

로그인이 필요한 사이트를 patchright/playwright로 다룰 때, 세션을 프로파일에 영속시켜 매 실행 재로그인을 없애고, 만료를 안전하게 처리하는 표준 패턴. 이 스킬은 *작업을 대신 수행하지 않는다* — 호출 코드가 따라 쓸 검증된 코드 템플릿을 제공하는 knowledge 가이드다.

## 책임 경계 (DO / DON'T)

- **DO**: 프로파일 저장·재사용, 세션 유효성 체크, 로그인 대기 루프, 실행 중 만료 감지·재인증. Python/JS 양쪽 템플릿.
- **DON'T**: 특정 사이트 로그인 폼 자동 입력, 2FA·CAPTCHA 자동 처리, 프록시·fingerprint 주입 같은 적극적 봇탐지 우회 — 호출 코드 책임이다. (patchright 기본 stealth 설정은 [persist.md](./references/persist.md)가 다룬다.)
- **DON'T — 사이트별 값 탐색**: 보호 URL·인증 쿠키명·로그인 리다이렉트 조각은 사이트마다 다르다. 이걸 *찾아 세팅*하는 건 호출 스킬(예: 크롤러 스킬)의 몫이고, 이 가이드는 그 값을 **파라미터로 받아** 이동·판정·재인증하는 범용 패턴만 제공한다. 값은 대화나 호출 스킬이 넘긴다.
- **patchright vs playwright**: API가 동일하다. patchright는 Playwright의 stealth 포크로 import 경로만 다르다(`patchright` ↔ `playwright`). 모든 템플릿이 양쪽에 그대로 적용된다.

## 언제 무엇을 읽나

작업 성격에 맞는 reference만 읽는다. 셋 다 Python·JS Incorrect/Correct 코드 쌍을 담는다.

| 하려는 일 | 읽을 파일 |
|---|---|
| 프로파일에 세션 저장·재사용, 컨텍스트 여는 표준 옵션, 경로 규칙 | [references/persist.md](./references/persist.md) |
| 작업 전 로그인 유효성 확인, 로그인 대기 루프, headless 전략 | [references/validate.md](./references/validate.md) |
| 크롤링 도중 세션 만료 감지·재인증, 점진 저장 | [references/expiry-reauth.md](./references/expiry-reauth.md) |

## 표준 흐름

로그인 세션 기반 자동화의 골격. 단계별 코드는 위 reference에 있다.

1. **프로파일 경로 결정** — `~/.browser-profiles/<service>/` (전역, 서비스 단위). → persist.md
2. **non-headless로 세션 확보** — 유효성 체크 후 없으면 로그인 대기 루프. → validate.md
3. **headless로 재시작해 작업** — context 닫고 다시 열어 자동화 실행. → validate.md
4. **도중 만료 감지·재인증** — URL 리다이렉트·API 401/403 감시, 점진 저장. → expiry-reauth.md

## 핵심 원칙 (전 reference 공통)

- **세션 영속은 `launch_persistent_context` + `user_data_dir`** — `launch()`+`new_context()`는 휘발성이라 재로그인을 못 없앤다. `storage_state`(JSON)는 테스트 픽스처용이지 실세션 유지용이 아니다.
- **patchright는 기본 설정이 최선** — detection 회피 `args`·custom `user_agent`·headers를 수동 추가하면 내부 stealth 패치를 오히려 약화시킨다. `channel="chrome"`·`no_viewport`만 쓴다.
- **빈 결과를 성공으로 착각하지 않는다** — 만료의 최대 위험은 에러가 아니라 *조용한 빈 데이터*. 상태 코드·URL을 명시 검사한다.
- **무한 대기·무한 재시도 금지** — 로그인 대기엔 타임아웃을, 재인증엔 시도 횟수 상한을 둔다.
- **프로파일은 .gitignore** — 쿠키·세션 토큰이 들어 있다. 같은 프로파일을 두 프로세스가 동시에 열면 잠금 오류가 난다.
- **스크립트는 자기 의존성을 선언한다** — patchright만 필요한 단일 크롤러가 무관한 프로젝트의 venv를 빌려쓰면, 그 프로젝트가 이동·삭제되면 깨지고 실행 명령도 길어진다. PEP 723 인라인 메타데이터로 자립화한다(아래 [실행 진입점](#셋업--실행-진입점)).

## 셋업 · 실행 진입점

세션 크롤러는 보통 단일 스크립트다. 의존성을 스크립트가 직접 선언하면 무관한 프로젝트 venv를 빌려쓰지 않고 자립 실행된다.

**DON'T** — 남의 프로젝트 venv 빌려쓰기:
```bash
uv run --project ~/other-project python crawler.py   # other-project가 이동·삭제되면 깨지고, 명령도 길어진다
```

**DO** — PEP 723 인라인 메타데이터로 자립(Python):
```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["patchright"]
# ///
"""크롤러 ..."""
```
실행: `uv run crawler.py [args]` — uv가 격리 venv를 자동 생성·캐시한다. shebang + 실행권한(`chmod +x`)이면 `./crawler.py`.

> Chrome은 `channel="chrome"`으로 시스템 Chrome을 쓰니 `patchright install chrome`가 따로 필요 없다. 번들 Chromium을 쓸 거면 최초 1회 `uv run --with patchright patchright install chromium`.

JS는 package.json이 의존성 SSOT라 같은 함정은 적다 — 단 크롤러를 무관한 패키지 안에 두지 말고 자체 package.json을 둔다(`npm i patchright`).

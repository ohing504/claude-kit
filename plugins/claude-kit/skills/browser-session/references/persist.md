# 프로파일 저장·재사용

매 실행마다 다시 로그인하지 않으려면, 로그인으로 생긴 쿠키·localStorage가 디스크에 남아야 한다. 그 그릇이 **persistent context**다.

## 핵심 — `launch_persistent_context`

`launch()` + `new_context()`는 메모리상의 임시 컨텍스트라 프로세스가 끝나면 세션이 사라진다. `launch_persistent_context`는 `user_data_dir`(Chrome 프로파일 디렉토리)에 세션을 영속시켜, 다음 실행이 로그인된 상태로 시작한다.

**DON'T** — 매 실행 세션 소실:
```python
browser = pw.chromium.launch(headless=True)
ctx = browser.new_context()        # 휘발성 — 다음 실행 때 로그인 풀림
```

**DO** — 프로파일에 영속:
```python
ctx = pw.chromium.launch_persistent_context(
    user_data_dir=str(PROFILE),    # 이 디렉토리에 쿠키·세션이 남는다
    headless=True,
)
```

> `launch_persistent_context`는 `browser` 객체가 아니라 **context를 직접 반환**한다. `browser.new_context()`로 또 컨텍스트를 만들지 않는다.

## 경로 규칙

프로파일은 **서비스 단위 전역 경로**에 둔다. 여러 프로젝트가 같은 서비스를 다룰 때 세션을 공유할 수 있고, 프로젝트를 옮겨도 재로그인이 필요 없다.

```
~/.browser-profiles/<service-name>/
```

```python
from pathlib import Path
PROFILE = Path.home() / ".browser-profiles" / "my-service"
PROFILE.mkdir(parents=True, exist_ok=True)
```

```javascript
const path = require("path");
const PROFILE = path.join(process.env.HOME, ".browser-profiles", "my-service");
```

## 컨텍스트 열기 — 표준 옵션

### Python

```python
from patchright.sync_api import sync_playwright   # playwright.sync_api도 동일

def open_session(profile, headless: bool = True):
    pw = sync_playwright().start()
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir=str(profile),
        channel="chrome",          # 설치된 실제 Chrome — patchright stealth의 핵심
        headless=headless,
        no_viewport=True,          # OS 창 크기 사용
        # patchright 전용 추가 옵션: focus_control=False (포커스 이벤트 비활성)
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return pw, ctx, page

# 정리: ctx.close() 후 pw.stop()
```

### JS

```javascript
const { chromium } = require("patchright");        // 또는 require("playwright")

async function openSession(profilePath, headless = true) {
  const ctx = await chromium.launchPersistentContext(profilePath, {
    channel: "chrome",
    headless,
    viewport: null,        // OS 창 크기 사용 (patchright 공식 권장 표기)
  });
  const page = ctx.pages()[0] ?? (await ctx.newPage());
  return { ctx, page };
}

// 정리: await ctx.close()
```

> `channel="chrome"` — 시스템에 설치된 Chrome을 쓴다. CI·서버처럼 Chrome이 없으면 이 줄을 빼서 번들 Chromium으로 폴백한다.

### patchright stealth — 기본 설정을 건드리지 않는다

patchright는 탐지 회피를 **내부 패치로 처리**한다. playwright를 수동 stealth화할 때 흔히 넣는 `--disable-blink-features=AutomationControlled` 같은 detection 회피 `args`, custom `user_agent`·headers를 **추가하면 오히려 탐지 지표가 되어 stealth가 깨진다**. 권장 설정은 위 템플릿의 `channel="chrome"` + `headless` + `no_viewport`(JS는 `viewport: null`)뿐이다.

**DON'T** — playwright 통념을 patchright에 적용:
```python
launch_persistent_context(..., args=["--disable-blink-features=AutomationControlled"],
                          user_agent="Mozilla/5.0 ...")   # patchright stealth를 약화시킨다
```

**DO** — patchright 기본에 맡긴다:
```python
launch_persistent_context(user_data_dir=..., channel="chrome", no_viewport=True)
```

> 적극적 우회(프록시, fingerprint 주입 스크립트)는 이 가이드 범위 밖이다 — 필요하면 호출 코드가 `add_init_script`로 직접 더한다.

## 주의

- **프로파일 잠금** — 같은 `user_data_dir`을 두 프로세스가 동시에 열면 Chrome이 잠금 오류를 낸다. 병렬 실행이 필요하면 서비스별로 디렉토리를 분리한다.
- **.gitignore** — `~/.browser-profiles/`(또는 프로젝트 내 `profiles/`)는 반드시 제외한다. 쿠키·세션 토큰이 들어 있다.
- **`storage_state`는 대안이 아니다** — `storage_state`(JSON 직렬화)는 테스트 픽스처용으로 쿠키·localStorage만 담고 브라우저 프로파일 전체(서비스워커·IndexedDB·확장 상태)는 빠진다. 실제 로그인 세션 유지에는 `launch_persistent_context`를 쓴다.

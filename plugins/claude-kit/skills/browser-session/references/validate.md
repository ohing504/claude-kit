# 세션 유효성 체크 + 로그인 대기

프로파일에 세션이 남아 있어도 만료됐을 수 있다. 작업을 시작하기 전에 *지금 로그인 상태가 유효한지* 확인하고, 아니면 사용자가 로그인할 때까지 기다린다.

## 두 단계 체크 — 경량 / 정확

### 경량 (쿠키 존재 확인)

빠르지만 만료된 쿠키도 통과시킨다. 로그인 대기 루프의 종료 조건처럼 *빈번한 폴링*에 쓴다.

```python
def is_logged_in(ctx, cookie_name: str) -> bool:
    return any(c["name"] == cookie_name and c.get("value") for c in ctx.cookies())
```

```javascript
async function isLoggedIn(ctx, cookieName) {
  const cookies = await ctx.cookies();
  return cookies.some((c) => c.name === cookieName && c.value);
}
```

> `cookie_name`은 해당 서비스의 인증 쿠키명이다 (예: 세션ID 쿠키). 사이트마다 다르므로 호출 코드가 지정한다.

### 정확 (보호된 페이지 네비게이션)

쿠키가 있어도 서버가 세션을 무효화했을 수 있다. 중요한 작업을 시작하기 직전엔 보호된 URL에 실제로 접근해, 로그인 페이지로 리다이렉트되는지로 판정한다.

```python
def is_session_valid(page, protected_url: str, login_url_fragment: str) -> bool:
    page.goto(protected_url, wait_until="domcontentloaded")
    return login_url_fragment not in page.url
```

```javascript
async function isSessionValid(page, protectedUrl, loginUrlFragment) {
  await page.goto(protectedUrl, { waitUntil: "domcontentloaded" });
  return !page.url().includes(loginUrlFragment);
}
```

> `login_url_fragment`는 로그인 리다이렉트 URL의 공통 조각이다 (예: `/login`, `/signin`, `/auth`).
>
> **`protected_url`은 로그인이 *필수*인 페이지여야 한다** — 마이페이지·대시보드·지원 내역처럼 미로그인 시 로그인으로 리다이렉트되는 URL. 공개 목록 페이지(누구나 보는)로 체크하면 미로그인이어도 통과해 만료를 전혀 못 잡는다.

**DON'T** — 체크 없이 바로 작업 시작:
```python
ctx = open_session(PROFILE)        # 세션 만료 시 빈 데이터/에러를 조용히 수집
crawl(page)
```

**DO** — 작업 전 정확 체크:
```python
if not is_session_valid(page, "https://site/dashboard", "/login"):
    # → 로그인 대기 루프로
    ...
crawl(page)
```

## 로그인 대기 루프

세션이 없거나 무효면, `headless=False`로 브라우저를 띄우고 사용자가 직접 로그인할 때까지 폴링한다. **무한 대기 금지** — 타임아웃을 둔다.

### 로그인 화면은 추측하지 말고 리다이렉트로 띄운다

사용자가 로그인하려면 로그인 폼이 화면에 떠 있어야 한다. 이때 **로그인 URL을 직접 추측하지 않는다** — 사이트마다 경로가 다르고(`/login`·`/accounts/login`·`/signin`·`?next=...`), 없는 경로면 404 빈 화면이 떠 사용자가 로그인할 수 없다. 대신 위 정확 체크(`is_session_valid`)가 **보호된 페이지로 이동**하면, 미로그인 시 사이트가 알아서 올바른 로그인 화면(next 파라미터 포함)으로 리다이렉트한다. 그 화면 그대로 두고 폴링하면 된다.

**DON'T** — 로그인 URL 직접 추측:
```python
page.goto(f"{BASE}/login/")    # 사이트에 이 경로가 없으면 404 빈 화면 → 로그인 불가
```

**DO** — 호출자가 넘긴 보호 페이지로 가서 사이트의 리다이렉트에 맡긴다:
```python
page.goto(protected_url)       # 미로그인이면 사이트가 올바른 로그인 화면으로 보낸다
# (is_session_valid가 이미 이 네비게이션을 하므로, 호출 순서만 맞추면 별도 goto 불필요)
```

**DON'T** — 무한 대기 / headless로 띄워 로그인 불가:
```python
ctx = open_session(PROFILE, headless=True)   # 보이지 않아 로그인할 수 없음
while not is_logged_in(ctx, "sid"):
    time.sleep(2)                            # 영원히 멈출 수 있음
```

**DO** — headless=False + 타임아웃:
```python
import time

def wait_for_login(ctx, cookie_name: str, timeout: int = 180) -> bool:
    print(f">>> 로그인 필요 — 브라우저에서 로그인하세요 (최대 {timeout}초)")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_logged_in(ctx, cookie_name):
            print(">>> 로그인 확인됨")
            return True
        time.sleep(2)
    return False
```

```javascript
async function waitForLogin(ctx, cookieName, timeoutMs = 180_000) {
  console.log(`>>> 로그인 필요 — 브라우저에서 로그인하세요 (${timeoutMs / 1000}초)`);
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await isLoggedIn(ctx, cookieName)) {
      console.log(">>> 로그인 확인됨");
      return true;
    }
    await new Promise((r) => setTimeout(r, 2000));
  }
  return false;
}
```

## headless 전략

로그인은 사람이 봐야 하고, 작업은 빠르고 가벼워야 한다. 두 국면에서 headless가 갈린다.

| 국면 | headless | 이유 |
|---|---|---|
| 최초 로그인 | `False` | 사용자가 UI를 직접 조작 |
| 만료 후 재인증 | `False` | 동일 |
| 자동화 작업 | `True` | 속도·리소스 절약 |

같은 프로파일로 headless ↔ non-headless를 바꿀 땐 context를 닫고 다시 연다. 전형적 흐름:

```python
# protected_url·login_fragment·cookie_name은 호출 스킬이 사이트에 맞게 넘긴다
# 1) non-headless로 세션 확보 — 보호 페이지로 이동(유효하면 통과, 미로그인이면 로그인 화면이 뜬다)
pw, ctx, page = open_session(PROFILE, headless=False)
if not is_session_valid(page, protected_url, login_fragment):
    if not wait_for_login(ctx, cookie_name, 180):   # 떠 있는 로그인 화면에서 로그인할 때까지 폴링
        ctx.close(); pw.stop()
        raise RuntimeError("로그인 타임아웃")
ctx.close(); pw.stop()

# 2) headless로 재시작해 작업
pw, ctx, page = open_session(PROFILE, headless=True)
# ... 작업 ...
ctx.close(); pw.stop()
```

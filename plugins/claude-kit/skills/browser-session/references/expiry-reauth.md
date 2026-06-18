# 실행 중 세션 만료 감지·재인증

세션은 작업 *도중에도* 만료될 수 있다. 시작 전 체크([validate.md](./validate.md))를 통과했어도, 긴 크롤링 중 서버가 세션을 끊으면 그 다음 요청부터 빈 데이터·로그인 페이지가 돌아온다. 이걸 잡지 않으면 **조용히 잘못된 결과를 수집**한다.

## 감지 — 두 신호

### URL 리다이렉트

페이지 네비게이션 결과가 로그인 URL로 튀면 만료다.

```python
class SessionExpiredError(Exception):
    pass

def assert_session_alive(page, login_url_fragment: str):
    if login_url_fragment in page.url:
        raise SessionExpiredError(f"세션 만료 — 현재 URL: {page.url}")
```

```javascript
class SessionExpiredError extends Error {}

function assertSessionAlive(page, loginUrlFragment) {
  if (page.url().includes(loginUrlFragment)) {
    throw new SessionExpiredError(`세션 만료 — ${page.url()}`);
  }
}
```

### API 상태 코드

페이지 컨텍스트 안에서 `fetch`로 API를 칠 때(쿠키 자동 포함), 401·403이면 만료다.

```python
def evaluate_fetch(page, url: str):
    result = page.evaluate(
        """async (u) => {
            const r = await fetch(u, { credentials: "include" });
            return { status: r.status, body: r.ok ? await r.json() : null };
        }""",
        url,
    )
    if result["status"] in (401, 403):
        raise SessionExpiredError(f"API 인증 실패: {result['status']}")
    return result
```

```javascript
async function evaluateFetch(page, url) {
  const result = await page.evaluate(async (u) => {
    const r = await fetch(u, { credentials: "include" });
    return { status: r.status, body: r.ok ? await r.json() : null };
  }, url);
  if (result.status === 401 || result.status === 403) {
    throw new SessionExpiredError(`API 인증 실패: ${result.status}`);
  }
  return result;
}
```

## 처리 패턴

**DON'T** — 만료를 무시하고 계속:
```python
for item in items:
    data = evaluate_fetch(page, item.url)   # 만료 후엔 빈 body를 계속 저장
    save(data)
```

**DO** — 감지 → 재인증 → 재개. 진행 상황을 디스크에 점진 저장해, 재인증 후 중단점부터 잇는다.

```python
def crawl_with_reauth(items, profile, cookie_name, login_fragment):
    pw, ctx, page = open_session(profile, headless=True)
    for item in items:
        if already_done(item):          # 점진 저장 → 재시작 시 건너뛰기
            continue
        try:
            data = evaluate_fetch(page, item.url)
            assert_session_alive(page, login_fragment)
            save(data)                  # 한 건씩 즉시 저장 (중단 대비)
        except SessionExpiredError:
            ctx.close(); pw.stop()
            # non-headless로 재로그인 (validate.md의 wait_for_login)
            pw, ctx, page = reauth(profile, cookie_name)
            data = evaluate_fetch(page, item.url)   # 같은 항목 재시도
            save(data)
    ctx.close(); pw.stop()
```

`reauth`는 [validate.md](./validate.md)의 로그인 대기 루프를 그대로 쓴다 — headless=False로 열고 `wait_for_login` 후 headless로 재시작.

## 원칙

- **빈 결과를 성공으로 착각하지 않는다** — 만료의 가장 큰 위험은 에러가 아니라 *조용한 빈 데이터*다. 상태 코드·URL을 명시적으로 검사한다.
- **점진 저장** — SQLite·파일에 건별로 즉시 쓴다. 재인증으로 프로세스가 끊겨도 중단점부터 재개한다.
- **무한 재시도 금지** — 재인증 후 같은 항목이 또 만료되면(예: 계정 차단) 몇 회 시도 후 중단하고 사용자에게 알린다.
- **정중한 크롤링** — 만료는 과도한 요청의 신호일 수 있다. 요청 간 지연·동시성 1을 유지한다.

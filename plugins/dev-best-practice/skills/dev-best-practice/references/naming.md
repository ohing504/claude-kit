# 이름 짓는 규칙

`common.md` 판정 3이 피할 이름을 정한다면, 이 파일은 **무엇을 쓸지**를 정한다. 새 파일마다 고민하지 않도록 조합 규칙으로 적는다.

1. 이름은 경로 전체로 읽는다
2. 기본형은 대상 명사 하나
3. 역할어는 홀로 두지 않는다
4. 단수로 쓰고 복수는 담는 것에만
5. 접두는 파일이 열을 넘을 때 붙인다
6. 약어는 그 단어가 이미 도메인 어휘일 때만
7. 케이스는 언어가 정한다

판정의 근거는 저장소 마흔둘을 센 결과다. 2026-09-04에 GitHub `git/trees` API로 경로를 받아 세었다(Go 열넷, Python 열넷, TypeScript 열넷. `vendor`, `node_modules`, `dist`, `testdata`, `generated`, 테스트 파일 제외).

## 1. 이름은 경로 전체로 읽는다

**폴더가 이미 말한 것을 파일 이름에 다시 넣지 않는다.** 쓰는 쪽이 보는 것은 `logger/config.go`이지 `config.go`가 아니다.

```text
internal/logger/config.go        ← logger의 설정
internal/logger/logger_config.go ← logger를 두 번 말한다
```

실측이 이 형태를 보여준다. `config`, `types`, `client`, `handler`처럼 그 자체로는 대상이 없는 이름의 파일 중, 부모 폴더가 대상 이름인 것이 Go 70%, Python 97%, TypeScript 73%다.

| 언어 | 부모가 대상 이름 | 부모도 일반 이름 |
|---|---|---|
| go | 215 (70%) | 90 |
| py | 69 (97%) | 2 |
| ts | 839 (73%) | 308 |

예: `modules/caddyhttp/push/handler.go`, `celery/backends/database/models.py`, `src/textual/css/types.py`

**그래서 이름을 지을 때 파일만 보지 않는다.** 경로를 왼쪽부터 이어 읽어 문장이 되는지 본다 — "logger의 config"는 되고 "config의 config"는 안 된다.

## 2. 기본형은 대상 명사 하나

`session.go`, `download.py`, `element.ts`. 동작이 아니라 다루는 것을 쓴다(`common.md` 판정 3).

`[한정어]-[대상]-[역할]` 순으로 붙이되, 필요한 것만 남긴다. 왼쪽이 좁히는 말이고 오른쪽이 무엇인지다.

| 형태 | 예 | 언제 |
|---|---|---|
| 대상 | `session`, `invoice` | 기본. 대부분 여기서 끝난다 |
| 대상 + 역할 | `webhook-handler`, `stripe-client` | 같은 대상에 역할이 여럿일 때 |
| 한정어 + 대상 | `pending-invoice`, `draft-post` | 같은 대상의 상태나 종류를 가를 때 |

**세 마디를 넘으면 폴더로 옮길 때다.** `admin-user-settings-form.tsx`가 되면 `admin/user-settings/form.tsx`를 검토한다. 판정 1이 그 이름을 다시 짧게 만든다.

## 3. 역할어는 홀로 두지 않는다

`handler`, `manager`, `service`, `provider`, `client`, `helper`, `util`, `store`는 무엇에 대한 것인지를 말하지 않는다. **대상이 이름 안이나 폴더 이름에 있어야 한다.**

```text
webhook-handler.ts        대상이 이름 안에
webhooks/handler.ts       대상이 폴더 이름에
handler.ts                어느 쪽에도 없다 — 고친다
```

TypeScript 실측에서 이 역할어들이 대상과 함께 쓰인 것이 1,611개, 홀로 쓰인 것이 1,147개다. 홀로 쓰인 것의 73%는 부모 폴더가 대상 이름이라 판정 1로 통과한다.

**`manager`와 `service`는 대상이 붙어도 다시 본다.** 그 둘은 역할조차 말하지 않는다 — `session-manager`가 세션을 만드는지 지우는지 세는지 이름에 없다. 하는 일이 하나면 그 일로 이름 짓고(`session-store`), 여럿이면 나눌 때다.

## 4. 단수로 쓰고 복수는 담는 것에만

파일과 폴더 모두 단수가 기본이다. 실측이 그렇다.

| 언어 | 파일 단수 | 폴더 단수 |
|---|---|---|
| go | 85% | 86% |
| py | 82% | 64% |
| ts | 86% | 72% |

복수를 쓰는 자리는 둘이다.

- **여러 개를 담는 폴더** — `features/`, `components/`, `hooks/`, `migrations/`
- **정의를 여러 개 담는 묶음 파일** — `types.ts`, `constants.py`, `routes.go`

`features/customer/`이지 `features/customers/`가 아니다. 그 폴더가 담는 것은 고객 하나에 관한 코드다. 컬렉션을 렌더하는 컴포넌트도 그 자체는 하나라 `customer-list.tsx`다.

**폴더의 복수 비율이 파일보다 높은 것이 이 규칙과 맞는다.** 여러 개를 담는 것이 폴더이기 때문이다.

## 5. 접두는 파일이 열을 넘을 때 붙인다

한 폴더의 파일이 늘면 폴더를 더 만들기 전에 이름 접두로 묶는다. **언제부터 그렇게 하는지가 실측에 있다** — 폴더 안 파일 수별로, 접두를 둘 이상과 공유하는 파일의 비율(중앙값)이다.

| 언어 | 3~5개 | 6~10개 | 11~20개 | 21개+ |
|---|---|---|---|---|
| go | 0% | 0% | 11% | 28% |
| py | 0% | 0% | 17% | 10% |
| ts | 0% | 0% | 21% | 27% |

**열까지는 접두가 없고 열하나부터 나타난다.** 파일이 적을 때 붙이면 이름만 길어진다.

```text
modules/git/  파일 101개
  repo_*.go     24    commit_*.go   10    tree_*.go    9
```

접두는 그 폴더 안에서만 뜻이 통하면 된다. 폴더 이름을 접두로 다시 쓰지 않는다(판정 1).

**Go에서는 이것이 폴더의 대체 수단이다.** 폴더를 만들면 패키지가 갈려 export를 다시 설계해야 한다(`go.md` 판정 4).

## 6. 약어는 그 단어가 이미 도메인 어휘일 때만

**타자를 줄이려고 만든 축약을 파일 이름에 쓰지 않는다.** 실측에서 두 무리가 갈린다.

| 쓰는 것 (마흔둘에서 흔함) | 안 쓰는 것 (거의 없음) |
|---|---|
| `config` 704, `util(s)` 2757, `auth` 350, `spec` 346, `id` 273, `admin` 228, `env` 156, `init` 60, `db` 44, `repo` 93, `info` 72 | `cfg`, `ctx`, `err`, `msg` 7, `req` 7, `res`, `conn` 8, `addr`, `impl`, `temp` 4 |

앞 무리는 그 형태가 이미 그 분야의 단어다 — 아무도 `configuration.ts`나 `authentication-client.ts`라고 쓰지 않는다. 뒤 무리는 코드 안 지역 변수에서만 통하는 축약이라 파일 이름에서는 풀어 쓴다.

**판정 기준: 그 축약형으로 검색했을 때 찾는 사람이 있겠는가.** `db`는 있고 `cfg`는 없다.

## 7. 케이스는 언어가 정한다

| 언어 | 파일 | 근거 |
|---|---|---|
| TypeScript, JavaScript | kebab-case | `react.md` 판정 7 |
| Go | 소문자와 밑줄 | `go.md` 판정 5 |
| Python | snake_case | `python.md` 판정 4 |

**파일 이름과 안의 심볼 이름은 따로 간다.** `stats-page.tsx`가 `StatsPage`를 export하고 `text_area.py`가 `TextArea`를 정의한다. 파일 이름은 파일시스템 규칙을 따르고 심볼 이름은 언어 규칙을 따른다.

한 저장소에 케이스를 섞지 않는다. 섞이면 파일을 찾을 때마다 어느 쪽인지 확인해야 한다.

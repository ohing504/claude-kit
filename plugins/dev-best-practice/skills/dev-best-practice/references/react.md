# React와 Next.js 배치 판정

`common.md`의 판정을 전제하고, React와 Next.js 저장소에만 적용되는 것을 담는다.

1. 슬라이스는 대상으로 묶고 그 안을 세그먼트로 나눈다
2. 세그먼트 이름은 쓰임을 가리킨다
3. 배럴 파일을 쓰지 않는다
4. `features`는 두 뜻이라 먼저 정한다
5. 강제하는 것은 단방향 흐름 하나다
6. Next.js와 함께 쓸 때
7. 서버에서 실행되는 코드는 세그먼트를 따로 둔다
8. 파일 이름은 kebab-case로 쓴다

근거로 삼는 출처가 서로 충돌한다.

| 출처 | 무엇인가 | 무엇을 강제하나 |
|---|---|---|
| Feature-Sliced Design v2.1 | 레이어와 세그먼트 이름을 표준화한 방법론 | import 방향, 슬라이스마다 public API |
| bulletproof-react | 가장 널리 복제되는 React 저장소 구조 예제 | 단방향 흐름, 기능 간 import 금지, 배럴 파일 금지 |
| Robin Wieruch의 글 | 규모가 커질 때 폴더가 늘어나는 순서를 8단계로 적은 개인 글 | 강제 없음, 판정 기준만 |

## 1. 슬라이스는 대상으로 묶고 그 안을 세그먼트로 나눈다

`src/` 바로 아래에 `shared/`와 대상별 슬라이스를 두고, 슬라이스 안을 `ui`, `model`, `api`로 나눈다.

```text
src/
  shared/          여러 슬라이스가 쓰는 것
  stats/
    ui/            화면에 보이는 것 (컴포넌트, 포매터, 스타일)
    model/         데이터 모델, 스토어, 비즈니스 로직
    api/           서버 요청 함수와 그 타입
  studio/
    ui/
```

**FSD의 `entities`와 `features`와 `widgets` 구분은 도입하지 않는다.** 그 셋을 쓰면 한 대상(`user`)의 코드가 `entities/user/`와 `features/reset-password/`와 `widgets/user-profile-card/`로 나뉜다. 얻는 것은 재사용 판정 하나이고, 그 판정은 파일을 옮길 때 해도 늦지 않다.

FSD 문서 자신이 레이어를 덜 쓰는 것을 허용한다 — "You don't have to use every layer in your project — only add them if you think it brings value to your project" (<https://feature-sliced.design/docs/get-started/overview>).

세그먼트 이름은 FSD가 정의한 것을 그대로 쓴다.

| 세그먼트 | 담는 것 |
|---|---|
| `ui` | UI 표시에 관한 모든 것 — 컴포넌트, 날짜 포매터, 스타일 |
| `api` | 백엔드 상호작용 — 프론트가 보내는 요청 함수, 데이터 타입, 매퍼. 서버가 요청을 받는 코드는 판정 7 |
| `model` | 데이터 모델 — 스키마, 인터페이스, 스토어, 비즈니스 로직 |
| `lib` | 그 슬라이스의 다른 모듈이 쓰는 코드 |
| `config` | 설정 파일과 기능 플래그 |

**실제로 파일이 들어가는 세그먼트만 만든다.** 빈 폴더를 미리 만들어 두지 않는다.

## 2. 세그먼트 이름은 쓰임을 가리킨다

`components/`, `hooks/`, `types/`, `utils/`, `actions/`, `modals/`로 나누지 않는다. 파일이 무엇인지만 말하고 무엇을 위한 것인지는 말하지 않는 이름이다.

FSD 원문 판정이 한 문장이다 — **"segment names should describe purpose (the why), not essence (the what)"** (<https://feature-sliced.design/docs/about/understanding/naming>).

FSD 튜토리얼이 적는 이유는 이렇다.

- 폴더 안에서 코드를 찾는 데 도움이 안 되어 파일을 하나씩 열어 봐야 한다.
- 서로 무관한 코드가 한 폴더에 모인다.
- 하나를 고칠 때 함께 고쳐야 하는 파일이 늘어 코드 리뷰와 테스트가 어려워진다.

**확장자가 소속을 정하지 않는다.** FSD의 `ui` 정의는 "UI components, date formatters, styles, etc."이고 포매터가 명시적으로 들어 있다. 숫자를 화면 문구로 바꾸는 `.ts` 파일을 `.tsx`가 아니라는 이유로 `model`이나 `utils`로 보내면, 문구를 고치려는 사람이 두 폴더를 다 열어야 한다. 판정 기준은 "무엇을 담았나"가 아니라 **"무엇을 고치려고 이 파일을 여나"** 이다.

**shadcn을 쓰면 그 경로를 지킨다.** `components.json`의 `aliases`가 `"ui": "@/components/ui"`와 `"utils": "@/lib/utils"`를 고정하고 CLI가 그 경로에 파일을 넣는다. `common.md` 판정 6이 도구 설정을 1순위로 두는 경우다.

## 3. 배럴 파일을 쓰지 않는다

배럴 파일은 `index.ts`가 하위 파일을 재export하는 것이고, FSD가 public API를 구현하는 수단이다. 앱 코드에는 두지 않는다.

배럴을 두면 이런 비용이 생긴다.

- **읽는 모듈이 늘어난다** — 배럴에서 하나를 꺼내도 그 배럴이 재export하는 것을 전부 읽는다.
- **정의로 이동이 구현 파일을 열지 않는다** — 편집기에서 심볼을 눌러도 `index.ts`가 열려 한 번 더 눌러야 한다. `grep` 결과에도 재export 줄이 먼저 나온다.
- **순환 참조가 생긴다** — 같은 슬라이스 안의 파일이 배럴에서 import하면 `tab-panel.ts`가 `index.ts`를 부르고 `index.ts`가 다시 `tab-panel.ts`를 부른다.

Vercel이 잰 수치다(<https://vercel.com/blog/how-we-optimized-package-imports-in-next-js>).

| 대상 | 배럴 경유 | 직접 import |
|---|---|---|
| lucide-react | 5.8s (1583 modules) | 3s (333 modules) |
| @mui/material | 7.1s (2225 modules) | 2.9s (735 modules) |
| @material-ui/icons | 10.2s (11738 modules) | 2.9s (632 modules) |

자기 앱 코드에서도 같은 규모의 차이가 나온다. TkDodo의 Next.js 프로젝트에서 페이지 하나가 11k 모듈을 읽어 시작에 5~10초가 걸렸고, 내부 배럴을 걷어낸 뒤 3.5k로 68% 줄었다(<https://tkdodo.eu/blog/please-stop-using-barrel-files>).

**Next.js의 `optimizePackageImports`는 이 비용을 자기 코드에서 줄여 주지 않는다.** node_modules 패키지가 대상이고 슬라이스마다 두는 `index.ts`는 해당하지 않는다.

**배럴이 주던 것은 각각 다른 수단으로 얻는다.**

| 배럴이 주던 것 | 배럴 없이 얻는 법 |
|---|---|
| 노출 제어 | Biome `noPrivateImports` — 심볼에 JSDoc `@private`나 `@package`를 붙인다. 경로가 아니라 심볼 단위라 파일을 옮겨도 따라간다 |
| 파일 이동 내성 | `tsconfig.json`의 `paths` 별칭으로 슬라이스 경로를 고정한다 |
| 배럴을 다시 만들지 않기 | Biome `noBarrelFile`과 `noReExportAll` |

**라이브러리를 배포한다면 배럴을 쓴다.** 진입점이 하나 필요하기 때문이고, 이것이 유일한 정당한 경우다.

## 4. `features`는 두 뜻이라 먼저 정한다

같은 단어가 출처마다 다른 것을 가리킨다. 도입 전에 이 대응을 맞춘다.

| 무엇을 담나 | FSD | bulletproof-react, Wieruch |
|---|---|---|
| 대상(`user`, `post`)에 관한 코드 묶음 | `entities/user/` | `features/user/` |
| 사용자가 하는 행동(장바구니 담기, 비밀번호 재설정) | `features/add-to-cart/` | 대상 폴더 안에 함께 둠 |
| 페이지를 채우는 큰 UI 덩어리 | `widgets/` | 대상 폴더 안 `components/` |

FSD의 features 레이어는 행동이다 — 원문이 "This layer is for the main interactions in your app, things that your users care to do"라고 적고 예로 "add to cart", "reset password", "rate product"를 든다. **대상으로 묶은 `features/user/`를 FSD 규격으로 옮기면 그 폴더는 `entities/user/`가 된다.**

## 5. 강제하는 것은 단방향 흐름 하나다

세 출처가 이름과 캡슐화에서 갈리지만 단방향 흐름은 셋 다 같은 문장으로 적는다. 하나만 강제할 수 있다면 이것이다.

- 코드는 한 방향으로 흐른다 — `shared` → 슬라이스 → 페이지.
- 슬라이스끼리 서로 import하지 않는다. 조합은 페이지에서 한다.

**문서에 적는 대신 린트 규칙으로 설정한다.** 규칙을 문서에만 적으면 새 팀원이 안 지켜도 아무 일이 없지만 린트는 커밋을 막는다.

Biome을 쓴다면 이 설정이 최소다. 기본으로 켜지는 것은 `noPrivateImports`뿐이고 나머지는 적어야 실행된다(2026-09-02 확인).

```json
{
  "linter": {
    "rules": {
      "performance": {
        "noBarrelFile": "error",
        "noReExportAll": "error"
      },
      "suspicious": { "noImportCycles": "error" }
    }
  }
}
```

`noPrivateImports`는 `correctness` 그룹이고 project 도메인에 속해 저장소 전체를 스캔한다. 스캔에 시간이 든다고 공식 문서가 밝힌다(<https://biomejs.dev/linter/domains/>).

ESLint를 쓴다면 `import/no-restricted-paths`의 zones로 같은 것을 막는다. 슬라이스가 늘 때마다 zone을 손으로 추가해야 한다. FSD를 규격대로 쓴다면 steiger가 규칙을 자동으로 설정하지만, beta라서 규칙 이름과 설정 형식이 바뀔 수 있다.

## 6. Next.js와 함께 쓸 때

Next.js는 배치를 규정하지 않는다고 스스로 밝히고("Next.js is unopinionated about how you organize and colocate your project files") 대신 배치 도구를 준다(<https://nextjs.org/docs/app/getting-started/project-structure>).

- **colocation** — `app/` 안의 폴더는 `page.js`나 `route.js`가 있어야 라우트가 되므로, 그 밖의 파일을 같은 폴더에 두어도 URL로 노출되지 않는다.
- **`_folder`** — 밑줄 접두는 그 폴더와 하위 전체를 라우팅에서 뺀다. colocation이 이미 되므로 필수는 아니고, 앞으로 추가될 Next.js 파일 규약과 이름이 겹치는 것을 피하는 용도다.
- **`(folder)`** — 괄호로 감싸면 URL 경로에서 빠진다. 사이트 구획으로 라우트를 묶거나 같은 층에서 레이아웃을 여러 개 둘 때 쓴다.
- **`src/`** — `app`을 `src/app`으로 옮겨 설정 파일과 앱 코드를 나눈다. 루트에 `app`이 있으면 `src/app`은 무시된다.

**FSD와 함께 쓰면 폴더 이름이 겹친다.** `app`과 `pages`를 Next.js와 FSD가 둘 다 쓴다. FSD 공식 가이드의 해법은 FSD 레이어에 접두를 붙이는 것(`_app`, `_pages`)이고, Next.js의 `app`을 루트에 두고 `src/`에는 FSD 코드만 남기는 배치를 권한다.

**App Router에서 배럴을 쓰면 빌드가 깨질 수 있다.** 서버 전용 모듈이 슬라이스의 `index.ts`로 나가면, 클라이언트 컴포넌트가 그 슬라이스를 import할 때 서버 전용 부수효과가 클라이언트 모듈 그래프로 따라 들어간다. 판정 3을 지키면 이 경우가 생기지 않는다.

**라우트 폴더 안에 기능을 넣을지에서 두 출처가 갈린다.** Wieruch는 기능을 `pages/projects/` 안에 넣는 것을 반대한다 — 기능 폴더 구조가 프로젝트 안에서 일관되지 않게 되고, 나중에 다른 페이지에서 재사용하려면 다시 꺼내야 한다. Next.js는 `_folder`로 colocation을 권한다. 둘 중 무엇을 따를지 저장소마다 한 번 정해 저장소 문서에 적는다.

## 7. 서버에서 실행되는 코드는 세그먼트를 따로 둔다

`api` 세그먼트는 프론트가 백엔드로 **보내는** 요청이다. FSD 정의가 "backend interactions: request functions, data types, mappers"이고 받는 쪽 코드는 여기 없다. FSD 자신도 Next.js 가이드에서 받는 코드에 다른 세그먼트를 준다 — Route Handler는 `api-routes`, 데이터베이스 질의는 `shared`의 `db`(<https://feature-sliced.design/docs/guides/tech/with-nextjs>).

슬라이스 안에서는 `server/` 세그먼트에 모은다. FSD가 표준 세그먼트 밖의 이름을 허용한다 — "You can also create custom segments"(<https://feature-sliced.design/docs/reference/slices-segments>).

| 무엇 | 어디에 두나 |
|---|---|
| Server Action | 슬라이스의 `server/`. 파일 맨 위에 `'use server'` |
| Route Handler `route.ts` | `app/` 아래 라우터가 정한 경로. 본문은 슬라이스의 `server/`를 호출하는 것만 둔다 |
| 그 밖의 프로토콜 진입점 (MCP tool 핸들러 등) | 슬라이스의 `server/` |

**Server Action은 파일을 나누는 것이 프레임워크 요구다.** 클라이언트 컴포넌트에서 호출하려면 `'use server'`를 맨 위에 둔 별도 파일이어야 한다고 Next.js가 적는다(<https://nextjs.org/docs/app/api-reference/directives/use-server>). 서버 컴포넌트 안에서만 쓰는 것은 그 컴포넌트 안에 함수로 두어도 된다.

**`server/`는 실행 위치가 아니라 번들 경계다.** 판정 2가 금지하는 `components/`나 `types/`와 다른 이유가 여기 있다. 이 폴더의 파일이 클라이언트 모듈 그래프로 들어가면 비밀값과 내부 로직이 브라우저로 나간다. `import 'server-only'`를 넣으면 클라이언트에서 import될 때 빌드가 실패한다(<https://nextjs.org/docs/app/getting-started/server-and-client-components>).

**`actions/` 폴더를 만들지 않는다.** 판정 2대로 무엇을 위한 코드인지가 이름에 없다. Server Action이 몇 개뿐이면 `server/actions.ts` 한 파일, 늘어나면 하는 일로 이름 지은 파일로 나눈다.

**Server Action은 인증을 자기 안에서 확인한다.** 화면을 거치지 않고 POST 요청으로 직접 호출된다고 Next.js가 경고한다(<https://nextjs.org/docs/app/getting-started/mutating-data>). 배치와 별개지만 `server/`에 파일을 만들 때마다 확인할 것이다.

## 8. 파일 이름은 kebab-case로 쓴다

컴포넌트 파일도 `stats-page.tsx`로 쓴다. export 이름은 `StatsPage`로 두어 파일 이름과 다르게 간다.

이유 둘.

- **대소문자를 구분하지 않는 파일시스템에서 이름만 바꾼 것이 git에 잡히지 않는다.** macOS 기본 APFS와 Windows가 그렇다. `Button.tsx`를 `button.tsx`로 바꾸면 커밋에 들어가지 않아 다른 사람이 받았을 때 import가 깨진다. 옮길 때 `git mv`를 쓴다.
- **한 저장소에 케이스가 섞이면 파일을 찾을 때마다 어느 쪽인지 확인해야 한다.** shadcn을 쓰면 `components/ui/`가 이미 kebab이므로 나머지를 kebab으로 맞추는 것이 섞이지 않는 쪽이다.

널리 쓰이는 저장소 아홉 곳의 `.tsx` 파일 이름을 세었다(2026-09-03, `git/trees` API. `node_modules`와 `dist`와 `.test.`와 `.stories.` 제외).

| 저장소 | kebab | Pascal |
|---|---|---|
| shadcn-ui/ui | 2827 | 2 |
| vercel/ai-chatbot | 44 | 0 |
| bulletproof-react | 64 | 0 |
| vercel/commerce | 19 | 0 |
| create-t3-app | 31 | 4 |
| TanStack/router | 1496 | 373 |
| refinedev/refine | 715 | 351 |
| calcom/cal.com | 104 | 697 |
| payloadcms/payload | 40 | 491 |

Pascal이 많은 둘은 2018년과 2020년에 시작한 저장소다. 최근에 시작한 넷은 Pascal이 0이다.

**kebab으로 바꿀 때 이름이 겹치는지 확인한다.** `studio/ui/Sidebar.tsx`를 `sidebar.tsx`로 바꾸면 `components/ui/sidebar.tsx`와 import 문에서 구분되지 않는다. 한쪽에 슬라이스 이름을 붙인다(`studio-sidebar.tsx`) — `common.md` 판정 3이 같은 것을 정한다.

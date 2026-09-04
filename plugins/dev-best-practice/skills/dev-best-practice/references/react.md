# React와 Next.js 배치 판정

`common.md`의 판정을 전제하고, React와 Next.js 저장소에만 적용되는 것을 담는다.

1. 기능 폴더로 묶고 그 안을 세그먼트로 나눈다
2. 최상위 공용 폴더는 도구가 만든 자리에 둔다
3. 기능 묶음 폴더 이름은 하나만 쓴다
4. 배럴 파일을 쓰지 않는다
5. 단방향 흐름을 린트로 강제한다
6. Next.js와 함께 쓸 때
7. 파일 이름은 kebab-case로 쓴다

판정의 근거는 실제로 운영되는 저장소를 센 결과다. 2026-09-03에 GitHub `git/trees` API로 아래 열넷의 파일 경로를 받아 세었다.

dub, unkey, documenso, formbricks, openstatus, midday, inbox-zero, papermark, twenty, plane, trigger.dev, cal.com, vercel/ai-chatbot, bulletproof-react

문서로 규격을 정한 방법론으로 Feature-Sliced Design이 있지만 판정의 근거로 쓰지 않는다. 위 열넷 중 FSD가 정한 세그먼트 이름(`ui`, `model`)을 쓰는 곳이 없고, 채택 규모도 작다 — FSD 문서 저장소가 별 2,361개인 데 비해 bulletproof-react가 35,786개이고, FSD 린터 steiger의 npm 주간 내려받기가 88,979인 데 비해 `eslint-plugin-boundaries`가 1,639,672이다(2026-09-03 확인).

## 1. 기능 폴더로 묶고 그 안을 세그먼트로 나눈다

`src/features/{대상}/` 아래에 그 기능의 코드를 모으고, 안을 세그먼트로 나눈다.

```text
src/
  app/                 라우팅 (Next.js)
  components/          여러 기능이 함께 쓰는 UI
  lib/                 여러 기능이 함께 쓰는 코드
  hooks/               여러 기능이 함께 쓰는 훅
  features/
    account/
      components/      이 기능의 화면
      lib/             이 기능의 로직
      hooks/
      api/             서버 요청
```

세그먼트 이름은 실측에서 많이 쓰인 것을 쓴다 — `components`, `lib`, `hooks`, `api`. 그 밖에 `services`, `repositories`, `utils`, `pages`가 나온다.

**실제로 파일이 들어가는 세그먼트만 만든다.** 세그먼트가 하나뿐이면 나머지는 만들지 않는다.

**세그먼트를 몇 개로 나눌지는 `common.md` 판정 2가 정한다.** 기능 폴더의 파일이 20개까지면 세그먼트 없이 평평하게 두는 것이 낫다.

## 2. 최상위 공용 폴더는 도구가 만든 자리에 둔다

`shadcn init`이 `components/ui/`와 `lib/utils.ts`와 `hooks/`를 만든다. 이 자리를 옮기지 않는다.

- 실측한 열넷 중 `components`가 일곱, `lib`이 여섯, `utils`가 여섯, `hooks`가 넷에 있다. `shared` 한 폴더로 묶은 곳은 cal.com 하나다.
- 옮기면 `components.json`의 `aliases`와 import 경로 전부가 바뀌는데, 얻는 것이 이름 하나다.

**`components.json`의 `components`와 `ui`를 같은 값으로 두지 않는다.** 두 값은 서로 다른 registry 항목의 목적지다 — `registry:ui`는 단일 파일 primitive이고 `registry:component`와 `registry:block`은 여러 파일로 된 조립물이다(<https://ui.shadcn.com/docs/registry/registry-item-json>). 같은 값으로 두면 덮어써도 되는 primitive와 고쳐 쓰는 조립물이 한 폴더에 섞인다.

**`components/ui/`에 손으로 쓴 컴포넌트를 넣지 않는다.** `shadcn add --overwrite`로 primitive를 갱신할 때 무엇이 덮어써도 되는지 구분되지 않는다. registry에 없는 것은 `components/` 바로 아래나 기능 폴더로 옮긴다.

## 3. 기능 묶음 폴더 이름은 하나만 쓴다

`features`와 `modules`와 `domains` 중 무엇을 써도 되지만 한 저장소에 하나만 쓴다.

| 이름 | 쓰는 저장소 |
|---|---|
| `features` | cal.com, bulletproof-react, papermark, formbricks, inbox-zero, unkey |
| `modules` | twenty, formbricks, cal.com, plane |
| `domains` | dub, unkey, papermark, openstatus |

섞으면 새 코드를 어디 둘지 매번 정해야 한다. twenty는 `modules`와 `widgets`와 `entities`와 `domains`를, papermark는 `features`와 `domains`와 `ee`를 함께 쓴다.

**`features`가 출처마다 다른 것을 가리킨다.** bulletproof-react에서는 대상(`features/user/`)이고 Feature-Sliced Design에서는 사용자가 하는 행동(`features/add-to-cart/`)이다. FSD 문서를 참고할 때 이 차이를 먼저 맞춘다.

## 4. 배럴 파일을 쓰지 않는다

배럴 파일은 `index.ts`가 하위 파일을 재export하는 것이다. 앱 코드에는 두지 않는다.

- **읽는 모듈이 늘어난다** — 배럴에서 하나를 꺼내도 그 배럴이 재export하는 것을 전부 읽는다.
- **정의로 이동이 구현 파일을 열지 않는다** — 편집기에서 심볼을 눌러도 `index.ts`가 열려 한 번 더 눌러야 한다. `grep` 결과에도 재export 줄이 먼저 나온다.
- **순환 참조가 생긴다** — 같은 폴더의 파일이 배럴에서 import하면 `tab-panel.ts`가 `index.ts`를 부르고 `index.ts`가 다시 `tab-panel.ts`를 부른다.

bulletproof-react가 같은 판정을 적고 이유로 번들러를 든다 — "In the past, it was recommended to use barrel files to export all the files from a feature. However, it can cause issues for Vite to do tree shaking and can lead to performance issues. Therefore, it is recommended to import the files directly." (<https://github.com/alan2207/bulletproof-react/blob/master/docs/project-structure.md>)

## 5. 단방향 흐름을 린트로 강제한다

- 코드는 한 방향으로 흐른다 — 공용 폴더 → 기능 폴더 → 페이지.
- 기능 폴더끼리 서로 import하지 않는다. 조합은 페이지에서 한다.

bulletproof-react가 같은 것을 적는다 — "It might not be a good idea to import across the features. Instead, compose different features at the application level. This way, you can ensure that each feature is independent which makes the codebase less convoluted." (<https://github.com/alan2207/bulletproof-react/blob/master/docs/project-structure.md>)

**문서에 적는 대신 린트 규칙으로 설정한다.** 규칙을 문서에만 적으면 새 팀원이 안 지켜도 아무 일이 없지만 린트는 커밋을 막는다.

Biome이면 이 설정으로 된다. `overrides` 블록 하나면 기능 폴더가 늘어도 설정이 늘지 않는다.

```json
{
  "linter": {
    "rules": {
      "performance": { "noBarrelFile": "error", "noReExportAll": "error" },
      "suspicious": { "noImportCycles": "error" }
    }
  },
  "overrides": [
    {
      "includes": ["src/features/**"],
      "linter": {
        "rules": {
          "style": {
            "noRestrictedImports": {
              "level": "error",
              "options": {
                "patterns": [
                  {
                    "group": ["@/features/*", "@/features/*/**"],
                    "message": "다른 기능 폴더를 직접 import하지 않는다. 같은 기능 안에서는 상대 경로를 쓴다"
                  },
                  {
                    "group": ["../../*", "../../*/**", "../../../**"],
                    "message": "상대 경로로 기능 폴더 밖을 가리키지 않는다. 여러 기능이 함께 쓰는 것은 @/lib으로 쓴다"
                  }
                ]
              }
            }
          }
        }
      }
    }
  ]
}
```

`noRestrictedImports`의 `patterns`는 v2.2.0부터 쓸 수 있다.

**두 패턴이 다 있어야 한다.** alias만 막으면 `../../stats/lib/service`처럼 상대 경로로 부르는 것이 전부 통과한다.

**상대 경로 패턴은 파일의 깊이에 기댄다.** `../../`가 기능 폴더 밖이 되려면 파일이 `features/{기능}/{세그먼트}/파일` 자리에 있어야 한다. 아래 둘을 지키면 정확하고, 벗어나면 새는 곳이 생긴다(`@biomejs/biome@2.5.11`로 확인, 2026-09-04).

| 전제 | 어기면 |
|---|---|
| 기능 폴더 바로 아래에 파일을 두지 않고 세그먼트 안에 둔다 | `features/b/x.ts`에서 `../d/lib/service`가 한 단계라 통과한다 |
| 세그먼트 아래에 폴더를 더 만들지 않는다 | `features/d/components/sub/y.ts`에서 같은 기능의 `../../lib/service`가 막힌다 |

세그먼트 아래에 폴더를 두어야 할 만큼 파일이 많으면 그 깊이만큼 패턴에 `../../../*`를 더한다.

**규칙을 넣으면 두 방향을 다 시험한다.** 막아야 할 import를 하는 파일과 통과해야 할 import를 하는 파일을 각각 만들어 린트를 돌리고, 확인한 뒤 지운다. 막히는 쪽만 시험하면 규칙이 너무 좁게 걸리는 것을 놓친다.

**`noPrivateImports`는 이 용도에 맞지 않는다.** `@package`를 붙인 심볼이 그 심볼을 **정의한 파일의 폴더** 밖에서 막히므로, 같은 기능 폴더 안의 다른 세그먼트에서도 쓸 수 없다. `features/c/lib/service.ts`의 심볼을 `features/c/components/view.ts`가 못 쓰는 것을 확인했다.

ESLint를 쓴다면 `eslint-plugin-boundaries`가 같은 것을 한다. 규칙 하나를 위해 ESLint를 함께 돌릴 이유는 없다 — 위 Biome 설정으로 같은 것이 막힌다.

## 6. Next.js와 함께 쓸 때

Next.js는 배치를 규정하지 않는다고 스스로 밝히고("Next.js is unopinionated about how you organize and colocate your project files") 대신 배치 도구를 준다(<https://nextjs.org/docs/app/getting-started/project-structure>).

- **colocation** — `app/` 안의 폴더는 `page.js`나 `route.js`가 있어야 라우트가 되므로, 그 밖의 파일을 같은 폴더에 두어도 URL로 노출되지 않는다.
- **`_folder`** — 밑줄 접두는 그 폴더와 하위 전체를 라우팅에서 뺀다. colocation이 이미 되므로 필수는 아니고, 앞으로 추가될 Next.js 파일 규약과 이름이 겹치는 것을 피하는 용도다.
- **`(folder)`** — 괄호로 감싸면 URL 경로에서 빠진다. 사이트 구획으로 라우트를 묶거나 같은 층에서 레이아웃을 여러 개 둘 때 쓴다.
- **`src/`** — `app`을 `src/app`으로 옮겨 설정 파일과 앱 코드를 나눈다. 루트에 `app`이 있으면 `src/app`은 무시된다.

**Server Action은 `'use server'`를 맨 위에 둔 별도 파일이어야 한다.** 클라이언트 컴포넌트에서 호출하려면 그렇다고 Next.js가 적고, 파일 이름의 예로 `actions.ts`를 든다(<https://nextjs.org/docs/app/api-reference/directives/use-server>). 서버 컴포넌트 안에서만 쓰는 것은 그 컴포넌트 안에 함수로 두어도 된다.

**서버에서만 도는 파일에 `import 'server-only'`를 넣는다.** 클라이언트에서 import될 때 빌드가 실패해 비밀값과 내부 로직이 브라우저로 나가는 것을 막는다(<https://nextjs.org/docs/app/getting-started/server-and-client-components>).

**라우트 폴더 안에 기능을 넣을지에서 두 출처가 갈린다.** Robin Wieruch는 기능을 `pages/projects/` 안에 넣는 것을 반대한다 — 기능 폴더 구조가 프로젝트 안에서 일관되지 않게 되고, 나중에 다른 페이지에서 재사용하려면 다시 꺼내야 한다. Next.js는 `_folder`로 colocation을 권한다. 둘 중 무엇을 따를지 저장소마다 한 번 정해 저장소 문서에 적는다.

## 7. 파일 이름은 kebab-case로 쓴다

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

**kebab으로 바꿀 때 이름이 겹치는지 확인한다.** `studio/components/Sidebar.tsx`를 `sidebar.tsx`로 바꾸면 `components/ui/sidebar.tsx`와 import 문에서 구분되지 않는다. 한쪽에 기능 이름을 붙인다(`studio-sidebar.tsx`) — `common.md` 판정 3이 같은 것을 정한다.

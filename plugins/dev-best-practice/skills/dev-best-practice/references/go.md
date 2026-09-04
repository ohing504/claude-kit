# Go 배치 판정

`common.md`의 판정을 전제하고, Go 저장소에만 적용되는 것을 담는다.

1. 공개 범위는 `internal/`로 정한다
2. `pkg/`를 만들지 않는다
3. 실행 진입점은 `cmd/`에 둔다
4. 폴더는 늦게 만들고 파일 이름 접두로 묶는다
5. 파일 이름은 소문자와 밑줄로 쓴다
6. `util.go`는 다른 언어와 다르게 본다

판정의 근거는 실제로 운영되는 저장소를 센 결과다. 2026-09-04에 GitHub `git/trees` API로 아래 열넷의 파일 경로를 받아 세었다(`vendor`, `testdata`, `third_party`, `docs`, `examples` 경로와 생성 파일 제외).

cli/cli, gohugoio/hugo, junegunn/fzf, spf13/cobra, caddyserver/caddy, traefik/traefik, prometheus/prometheus, ollama/ollama, charmbracelet/bubbletea, rclone/rclone, syncthing/syncthing, minio/minio, go-gitea/gitea, grafana/k6

## 1. 공개 범위는 `internal/`로 정한다

`internal/`은 관례가 아니라 컴파일러가 강제하는 규정이다. `internal/`의 **부모 디렉토리를 뿌리로 하는 트리 안**에서만 import된다.

```text
a/internal/secret/   ← a/ 아래에서는 import된다
a/a.go               import "m/a/internal/secret"   통과
b/b.go               import "m/a/internal/secret"   use of internal package not allowed
```

재현해 확인했다(go1.27.0, 2026-09-04). 다른 언어에서 밑줄 접두나 린트로 표현하던 "밖에서 쓰지 마라"를 Go는 빌드 실패로 만든다.

- 열넷 중 아홉이 쓴다. 안 쓰는 다섯은 fzf, cobra, bubbletea, rclone, gitea다.
- **`internal/` 바로 아래 폴더 이름은 도메인 명사로 쓴다.** 아홉 저장소의 `internal/` 직속 폴더 98개 중 층위 이름(`utils`, `handlers`, `service`, `model`, `types`)은 하나뿐이었다(minio의 `handlers`).

**라이브러리를 배포하면 공개 범위가 곧 API다.** 밖에서 쓸 것만 위에 두고 나머지를 `internal/`로 내린다. 안 쓰는 다섯 중 cobra와 bubbletea는 파일이 루트에 평평해 나눌 것이 없는 경우다(→ 4).

## 2. `pkg/`를 만들지 않는다

열넷 중 `pkg/`를 쓰는 곳은 둘이다(cli/cli, traefik).

`pkg/`는 그 아래 무엇이 오는지를 말하지 않는다. `internal/`은 컴파일러가 뜻을 주지만 `pkg/`에는 그런 것이 없어 import 경로에 의미 없는 한 단계가 붙는다. 공개할 것은 모듈 루트 아래 도메인 폴더에 두고, 감출 것은 `internal/`에 둔다.

## 3. 실행 진입점은 `cmd/`에 둔다

바이너리를 여럿 내면 `cmd/<이름>/main.go`로 나눈다. 열넷 중 열이 쓴다.

`cmd/` 아래 폴더 하나가 바이너리 하나다. 진입점만 두고 로직은 `internal/`이나 도메인 폴더에 둔다 — `cmd/` 아래 코드는 다른 곳에서 import할 수 없는 자리가 아니라 그냥 main 패키지라, 로직을 여기 두면 테스트에서도 쓰기 어려워진다.

바이너리가 하나뿐이면 루트에 `main.go`를 두어도 된다. cobra와 bubbletea처럼 라이브러리만 내는 저장소에는 `cmd/`가 없다.

## 4. 폴더는 늦게 만들고 파일 이름 접두로 묶는다

**디렉토리가 곧 패키지 경계다.** 폴더를 만들면 import 경로와 공개 범위(대문자 export)가 함께 바뀌므로, 다른 언어에서 폴더를 만드는 것보다 비싸다.

| 저장소 | 루트 직속 `.go` | 성격 |
|---|---|---|
| charmbracelet/bubbletea | 40 | 라이브러리 |
| caddyserver/caddy | 36 | 서버 + 라이브러리 |
| spf13/cobra | 25 | 라이브러리 |
| gohugoio/hugo | 5 | 앱 |
| 나머지 열 | 0~2 | 앱 |

**라이브러리는 오래 평평하게 두고 앱은 잘게 나눈다.** `.go`를 담은 폴더의 파일 수 중앙값이 큰 앱 저장소에서 1~2다(gitea 2, minio 2, rclone 1, cli/cli 1). 폴더가 많은 것이 아니라 폴더 하나가 작다.

**한 패키지가 커지면 폴더가 아니라 파일 이름 접두로 묶는다.** gitea에서 잰 것이다.

| 패키지 | 파일 | 접두를 둘 이상과 공유하는 파일 | 접두 |
|---|---|---|---|
| `modules/git` | 101 | 59 | `repo_*` 24, `commit_*` 10, `tree_*` 9 |
| `routers/web/repo` | 63 | 28 | `issue_*` 15, `editor_*` 7 |
| `models/issues` | 29 | 14 | `issue_*` 12, `comment_*` 2 |

같은 패키지 안이면 파일을 나눠도 심볼이 그대로 보이므로, 폴더로 자를 때처럼 export를 다시 설계할 필요가 없다. `common.md` 판정 2의 규모 구간을 Go에서는 이렇게 읽는다 — 파일이 늘어도 폴더를 만드는 대신 이름 접두를 먼저 쓴다.

## 5. 파일 이름은 소문자와 밑줄로 쓴다

열넷 전부에서 대문자로 시작하는 `.go` 파일이 0개였다.

여러 단어면 밑줄로 잇는다 — `file_error.go`, `admin_auth_ldap.go`. 밑줄이 든 파일 대부분이 빌드 제약이 아니라 복합어다(hugo 117개 중 113개, gitea 570개 중 555개, prometheus 133개 중 106개).

**끝 단어가 GOOS나 GOARCH면 빌드 제약이 된다.** `listen_unix.go`는 unix에서만 컴파일되고 `_test.go`는 테스트 파일이다. 복합어 이름을 지을 때 마지막 단어가 `linux`, `windows`, `darwin`, `js`, `arm64` 같은 것이 되지 않게 한다.

## 6. `util.go`는 다른 언어와 다르게 본다

`common.md` 판정 3은 `utils.py`, `common.ts` 같은 **파일**을 피하라고 한다. Go에서는 이 판정의 근거가 약해진다.

**파일 이름이 import 경로에 나타나지 않는다.** `a/internal/secret/secret.go`를 쓰는 쪽은 `import "m/a/internal/secret"`으로 폴더를 부르고 `secret.Hi()`로 심볼을 부른다. 파일 이름은 그 패키지를 여는 사람만 본다.

실측도 그렇다. `util.go`, `utils.go`, `helper.go`, `helpers.go`, `common.go`, `misc.go`가 열넷 중 열둘에 있고 gitea에는 33개다.

**그래서 Go에서 판정 대상은 폴더 이름이다.** 폴더 이름이 곧 패키지 이름이자 호출부에 쓰이는 접두이므로, `util` 패키지를 만들면 `util.Something()`이라고 부르게 된다. `common.md` 판정 3의 `util/` 폴더 판정("안이 다시 대상별로 나뉘는가")을 여기 그대로 적용한다.

파일 쪽에서는 이렇게 본다.

- **패키지 안에 `util.go` 하나를 두는 것은 넘어간다.** 그 패키지를 여는 사람만 보는 이름이다.
- **`util.go`가 커져 나눠야 할 때는 대상 이름으로 나눈다.** `util.go`를 `util2.go`로 늘리지 않는다.
- **`util` 패키지 안의 `util.go`는 고친다.** fzf의 `src/util/util.go`와 gitea의 `modules/util/util.go`가 그 형태다.

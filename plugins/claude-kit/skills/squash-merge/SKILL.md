---
name: squash-merge
description: PR을 squash merge하고 squash 메시지 정리(net diff만, PR 내부 단계 차단), 원격 브랜치 삭제까지 한 흐름. 메인 체크아웃에서 실행하면 로컬 브랜치 삭제와 base 동기화도 하고, 워크트리는 지우지 않는다. "스쿼시 머지", "머지하자" 발화에 — merge 실행 전 확인(`--auto` 인자로만 생략).
argument-hint: "[--auto] [<pr#>|<branch>|<url>]"
allowed-tools: Bash(gh:*), Bash(git:*)
---

# Squash Merge

## Context

- 현재 브랜치: !`git branch --show-current`
- 인자: `$ARGUMENTS` — `[--auto] [<pr#>|<branch>|<url>]`

## 인자

- **타겟** (`--auto`를 제외한 첫 인자): PR 번호, 브랜치 이름, PR URL 중 하나. `gh pr view <타겟>`에 그대로 전달. 생략 시 현재 브랜치 연결 PR auto detect.
- **`--auto`**: Step 3의 사용자 확인 게이트 생략. 나머지 단계는 동일하게 실행.

## Task

### Step 1. PR 식별 + 분석

타겟 인자 없으면 `gh pr view --json number,headRefName,baseRefName,title,body,state,author`로 현재 branch 연결 PR auto detect. detect 실패 시 사용자에게 PR 번호 요청 후 종료(`--auto`여도 추측으로 진행 X).

PR 정보 + 변경 사항:

- `gh pr view <NUM> --json number,headRefName,baseRefName,title,body,commits,files,state,mergeable,mergeStateStatus,author`
- `gh pr diff <NUM>` (full net diff)

`headRefName`, `baseRefName`은 Step 5에서 쓰므로 기억해 둔다.

PR이 이미 머지/닫힘 상태면 squash 단계 skip하고 Step 5부터 진행.

**머지 가능 사전 점검**:

- `mergeable == CONFLICTING` 또는 `mergeStateStatus ∈ {DIRTY, BLOCKED, DRAFT, BEHIND}` → 멈추고 사유 보고, 강제 진행 X (충돌, 필수 체크 미통과, base 뒤처짐, 초안).
- `UNKNOWN` → 잠시 후 재조회.
- `UNSTABLE`(일부 체크 실패, 진행 중이나 머지 가능) → 경고 후 판단 요청.

**미커밋 파일 점검**: linked 워크트리에서 실행 중이면(`git rev-parse --git-dir`와 `--git-common-dir`가 다르면) `git status --short`를 확인한다. 데스크톱 앱은 세션에서 Claude가 연 PR이 머지된 뒤 untracked 파일을 묻지 않고 지울 수 있다. 결과는 Step 3에서 쓴다. 메인 체크아웃의 미커밋 변경은 다른 세션의 것일 수 있어 점검 대상이 아니다.

### Step 2. squash 메시지 작성 — net diff 사실 기반

**기준**: PR base 대비 head의 **net diff**만 보고 작성 — 중간 commit history 인용 X.

**차단 (session-context bleed)**:

- PR 내 자체 발견 버그와 그 수정 commit
- 되돌린 작업 (revert, restore)
- 중간 refactor, rename 후 재변경 흔적
- 개별 commit message 인용 (이슈 참조 줄은 예외, 아래 수집 규칙)
- 세션 발화, 블로커, 디버깅 과정, 키 디시전 번호(D-NN) 인용

**형식**:

- subject: `type(scope): summary` — recent commits + CLAUDE.md 컨벤션 일치
- body: 5줄 이내 bullet — net 변경만, HEREDOC
- 이슈 참조 줄은 body 맨 끝에 별도 블록으로, bullet 5줄 제한에 포함하지 않는다

**봇 의존성 PR은 body를 비운다 (net diff 기반 작성의 예외)**

**조건 둘을 모두 만족할 때만**:

1. PR `author.is_bot`이 `true`
2. net diff가 의존성 버전 선언 파일의 버전 문자열 변경뿐 (`pubspec.yaml`/`.lock`, `package.json`/lockfile, `.github/workflows/*.yml`의 `uses:` 핀, `build.gradle*`, `Gemfile`/`.lock`, `go.mod`/`go.sum`, `requirements*.txt`, `Cargo.toml`/`.lock`)

이 두 조건을 만족하면:

- **subject**: PR 제목 그대로. **body**: 빈 문자열 (Step 4에서 `--body ""`).
- **이슈 참조 수집을 통째로 건너뛰고**, "매칭 안 된 `#N`" 보고도 하지 않는다.
- **`Signed-off-by: dependabot[bot]` 트레일러도 넣지 않는다.**

**이슈 참조 수집 — commit history 차단의 유일한 예외**

출처는 셋: PR body, PR 제목, 각 commit의 `messageHeadline`+`messageBody`(Step 1의 `commits`). `(close[sd]?|fix(es|ed)?|resolve[sd]?) #N`과 `Refs #N`을 **대소문자 무시**로 모두 걷는다.

- **이슈 번호마다 키워드를 반복해 한 줄씩.** `Closes #1, #2`는 GitHub가 #1만 닫는다. 타 저장소는 `Closes owner/repo#100`.
- **중복 제거**: 여러 출처가 같은 이슈를 언급하면 한 줄로 합친다. 같은 이슈에 닫기 키워드와 `Refs`가 섞여 있으면 닫기 키워드만 남긴다.
- **키워드 승격 금지**: `Refs #N`만 있던 이슈를 `Closes`로 바꾸지 않는다. 닫을지는 그 이슈의 완료 조건이 정한다.
- **net diff에서 사라진 작업의 참조는 뺀다**: 중간 commit이 `Closes #7`을 달았어도 그 변경이 PR 안에서 되돌려졌으면 넣지 않는다.
- **매칭 안 된 `#N` 언급을 보고한다.** 세 출처에서 `#\d+`를 걷어, 참조 줄이 되지 못한 번호가 남으면 Step 3 출력에 한 줄 남긴다.
  - 출력 문구: `#N 언급이 <걸린 출처>에 있으나 닫기 키워드 없음 — 이슈면 말미 Closes #N 규격(commit 스킬) 위반, PR 번호 언급이면 무시`
  - `<걸린 출처>`는 그 번호가 실제로 나온 곳(PR 본문 / PR 제목 / commit message). PR 본문으로 고정해 적지 않는다.
  - 수집에서 빼는 둘: 코드블록, 인용 블록 안의 번호, 바로 위 규칙으로 뺀 번호.
  - `--auto`에서도 출력한다.
  - 자동으로 `Closes`를 붙이지 않는다. 붙일지는 사용자가 정하고, 붙인다면 영문 `Closes #N`.

배치는 bullet과 빈 줄 하나로 띄운 마지막 블록.

### Step 3. 실행 전 확인 게이트 (자동 발화, 명시 호출 공통)

**흐름**: 확인 없이 merge X (destructive, 복구 곤란).

1. PR(번호, 제목) + squash subject/body를 응답 본문에 코드블록으로 출력. Step 1에서 미커밋 파일이 나왔으면 그 목록과 "머지하면 앱이 지울 수 있습니다"를 함께 출력
2. confirm

- **subject/body는 응답 본문 텍스트로 출력한다.** AskUserQuestion `preview`는 터미널 전용이라 데스크탑, 모바일에선 사라져, 사용자가 내용 없이 승인 버튼만 본다.
- confirm 수단은 자유(AskUserQuestion/평문). 본문에 내용이 있으면 매체와 무관하게 표시된다.
- "머지하자" 류 자연어 진입도 raw git/gh 직접 처리 X — 본 흐름(Step 2 포함) 경유.

**`--auto` 지정 시**: 2번(confirm)만 생략하고 Step 4로 직행. 1번은 그대로 수행해 무엇을 머지했는지 기록으로 남긴다. Step 1의 머지 가능 사전 점검과 미커밋 파일 점검은 `--auto`에서도 멈춘다 — 사용자 확인이 아니라 머지 안전성과 파일 유실 문제라 옵션으로 우회하지 않는다.

### Step 4. squash merge 실행

```bash
gh pr merge <NUM> --squash --subject "<subject>" --body "$(cat <<'EOF'
<body>
EOF
)"
```

- GitHub 기본(개별 commit 이어붙이기) X — `--subject` + `--body` 명시 의무.
- **봇 의존성 PR(Step 2 예외)은 `--body ""`.** HEREDOC 없이 빈 문자열을 그대로 넘긴다 — `--body`를 생략하면 저장소의 `squash_merge_commit_message` 설정(대개 `PR_BODY`)이 되살아나 릴리즈 노트 전문이 커밋에 들어간다.
- **`--delete-branch`(`-d`) 사용 금지.** 이 옵션은 원격만이 아니라 로컬까지 정리하는데, 그 과정에서 gh가 현재 워크트리에서 base를 checkout하고 `git pull`을 실행한다. 다른 세션의 미커밋 변경이 워크트리에 있으면 그 pull이 실패하고(사용자 `pull.rebase=true`면 rebase 거부 메시지), 체크아웃된 브랜치만 바뀐 채 남는다. 원격 브랜치 삭제와 로컬 정리는 Step 5가 한다.

### Step 5. 머지 뒤 정리

```bash
HEAD_BRANCH=<headRefName>; BASE=<baseRefName>
git ls-remote --exit-code --heads origin "$HEAD_BRANCH" >/dev/null && git push origin --delete "$HEAD_BRANCH"
if [ "$(git rev-parse --git-dir)" = "$(git rev-parse --git-common-dir)" ]; then
  current=$(git branch --show-current)
  [ "$current" = "$HEAD_BRANCH" ] && git switch "$BASE" && current=$BASE
  git branch -D "$HEAD_BRANCH"
  if [ "$current" = "$BASE" ]; then git pull --ff-only origin "$BASE"; else git fetch origin "$BASE:$BASE"; fi
fi
```

- **워크트리는 지우지 않는다.** linked 워크트리에서는 원격 브랜치만 지운다. 폴더와 브랜치는 데스크톱 앱이나 세션 종료 프롬프트가 정리한다.
- **실패하면 git 출력을 그대로 보고하고 강제로 진행하지 않는다.** 다른 워크트리가 쓰는 브랜치는 git이 삭제를 거부한다.

## Execution

Step 1-2는 분석 단계. **Step 3 확인 후** Step 4→5를 순차 실행. git, gh 외 도구는 쓰지 않는다. 마지막에 merge PR URL과 정리 결과를 보고한다.

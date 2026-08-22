---
name: squash-merge
description: PR을 squash merge하고 squash 메시지 정리(net diff만, PR 내부 단계 차단)·방금 머지한 PR 브랜치만 로컬 정리·base 동기화까지 한 흐름. "스쿼시 머지", "머지하자" 발화에 — merge 실행 전 확인(`--auto` 인자로만 생략).
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

PR squash merge → 메시지 정리 → 로컬 정리 한 흐름으로 실행.

### Step 1. PR 식별 + 분석

타겟 인자 없으면 `gh pr view --json number,headRefName,baseRefName,title,body,state`로 현재 branch 연결 PR auto detect. detect 실패 시 사용자에게 PR 번호 요청 후 종료(`--auto`여도 추측으로 진행 X).

PR 정보 + 변경 사항:

- `gh pr view <NUM> --json number,headRefName,baseRefName,title,body,commits,files,state,mergeable,mergeStateStatus`
- `gh pr diff <NUM>` (full net diff)

`baseRefName`은 Step 6 동기화에 재사용하므로 기억해 둔다.

PR이 이미 머지/닫힘 상태면 squash 단계 skip하고 Step 5(로컬 정리)부터 진행.

**머지 가능 사전 점검**:

- `mergeable == CONFLICTING` 또는 `mergeStateStatus ∈ {DIRTY, BLOCKED, DRAFT, BEHIND}` → 멈추고 사유 보고, 강제 진행 X (충돌·필수 체크 미통과·base 뒤처짐·초안).
- `UNKNOWN` → 잠시 후 재조회.
- `UNSTABLE`(일부 체크 실패·진행 중이나 머지 가능) → 경고 후 판단 요청.

### Step 2. squash 메시지 작성 — net diff 사실 기반

**기준**: PR base 대비 head의 **net diff**만 보고 작성 — 중간 commit history 인용 X.

**차단 (session-context bleed)**:

- PR 내 자체 발견 버그·수정 commit
- 되돌린 작업 (revert·restore)
- 중간 refactor·rename 후 재변경 흔적
- 개별 commit message 인용 (이슈 참조 줄은 예외, 아래 수집 규칙)
- 세션 발화·블로커·디버깅 과정·키 디시전 번호(D-NN) 인용

**형식**:

- subject: `type(scope): summary` — recent commits + CLAUDE.md 컨벤션 일치
- body: 5줄 이내 bullet — net 변경만, HEREDOC
- 이슈 참조 줄은 body 맨 끝에 별도 블록으로, bullet 5줄 제한에 포함하지 않는다

**이슈 참조 수집 — commit history 차단의 유일한 예외**

출처는 셋: PR body, PR 제목, 각 commit의 `messageHeadline`+`messageBody`(Step 1의 `commits`). `(close[sd]?|fix(es|ed)?|resolve[sd]?) #N`과 `Refs #N`을 **대소문자 무시**로 모두 걷는다.

- **이슈 번호마다 키워드를 반복해 한 줄씩.** `Closes #1, #2`는 GitHub가 #1만 닫는다. 타 저장소는 `Closes owner/repo#100`.
- **중복 제거**: 여러 출처가 같은 이슈를 언급하면(PR body와 commit 양쪽, 또는 commit 여럿) 한 줄로 합친다. 같은 이슈에 닫기 키워드와 `Refs`가 섞여 있으면 닫기 키워드만 남긴다.
- **키워드 승격 금지**: `Refs #N`만 있던 이슈를 `Closes`로 바꾸지 않는다. 닫을지는 그 이슈의 완료 조건이 정한다.
- **net diff에서 사라진 작업의 참조는 뺀다**: 중간 commit이 `Closes #7`을 달았어도 그 변경이 PR 안에서 되돌려졌으면 넣지 않는다. net diff 기준은 참조 줄에도 같이 적용된다.
- **매칭 안 된 `#N` 언급을 보고한다.** 세 출처에서 `#\d+`를 걷어, 참조 줄이 되지 못한 번호가 남으면 Step 3 출력에 한 줄 남긴다.
  - 출력 문구: `#N 언급이 <걸린 출처>에 있으나 닫기 키워드 없음 — 이슈면 말미 Closes #N 규격(commit 스킬) 위반, PR 번호 언급이면 무시`
  - `<걸린 출처>`는 그 번호가 실제로 나온 곳(PR 본문 / PR 제목 / commit message). PR 본문으로 고정해 적지 않는다.
  - 수집에서 빼는 둘: 코드블록·인용 블록 안의 번호(과거 사례·예시를 옮겨 적은 것), 바로 위 규칙으로 뺀 번호.
  - `--auto`에서도 출력 — 참조 줄이 통째로 빠진 것은 body만 봐서는 눈에 띄지 않는다.
  - 자동으로 `Closes`를 붙이지 않는다. 붙일지는 사용자가 정하고, 붙인다면 영문 `Closes #N`.

배치는 bullet과 빈 줄 하나로 띄운 마지막 블록.

```text
- <net 변경 bullet>

Closes #12
Closes #14
Refs #9
```

### Step 3. 실행 전 확인 게이트 (자동 발화·명시 호출 공통)

**흐름: ① PR(번호·제목) + squash subject/body를 응답 본문에 코드블록으로 출력 → ② confirm.** 확인 없이 merge X (destructive·복구 곤란).

- **subject/body는 응답 본문 텍스트로 출력한다.** AskUserQuestion `preview`는 터미널 전용이라 데스크탑·모바일에선 사라져, 사용자가 내용 없이 승인 버튼만 본다.
- confirm 수단은 자유(AskUserQuestion·평문). 본문에 내용이 있으면 매체와 무관하게 표시된다.
- "머지하자" 류 자연어 진입도 raw git/gh 직접 처리 X — 본 흐름(Step 2 포함) 경유.

**`--auto` 지정 시**: ②의 confirm만 생략하고 Step 4로 직행. ①(PR 정보 + subject/body 출력)은 그대로 수행해 무엇을 머지했는지 기록으로 남긴다. Step 1의 머지 가능 사전 점검은 `--auto`에서도 동일 적용 — 충돌, 필수 체크 미통과, 초안, base 뒤처짐은 사용자 확인이 아니라 머지 안전성 문제라 옵션으로 우회하지 않는다.

### Step 4. squash merge 실행

```bash
gh pr merge <NUM> --squash --subject "<subject>" --body "$(cat <<'EOF'
<body>
EOF
)"

# 원격 head 삭제 (repo auto-delete가 켜져 있으면 이미 없어 실패한다)
git push origin --delete "<PR headRefName>" \
  || echo "원격 브랜치 삭제 실패 — 위 git 출력 확인 (이미 삭제됐으면 그대로 진행)"
```

- GitHub 기본(개별 commit 이어붙이기) X — `--subject` + `--body` 명시 의무.
- **`--delete-branch`(`-d`) 사용 금지.** 이 옵션은 원격만이 아니라 로컬까지 정리하는데, 그 과정에서 gh가 현재 워크트리에서 base를 checkout하고 `git pull`을 실행한다. 다른 세션의 미커밋 변경이 워크트리에 있으면 그 pull이 실패하고(사용자 `pull.rebase=true`면 rebase 거부 메시지), 체크아웃된 브랜치만 바뀐 채 남는다. 원격 삭제는 위 `git push origin --delete`로, 로컬 정리는 Step 5(worktree-aware)로 분리한다.
- 원격 head를 여기서 지워야 Step 5의 `[gone]` 감지가 성립한다. `git push origin --delete`는 로컬 remote-tracking ref도 함께 지운다.

### Step 5. 방금 머지한 PR 브랜치만 로컬 정리 (worktree 처리 포함)

**정리 대상은 오직 이번에 머지한 PR의 head 브랜치 하나** (Step 1의 `headRefName`). 전역 `[gone]` 스윕 금지 — 무관한 브랜치·다른 동시 세션의 활성 worktree까지 `--force`로 날려 미커밋 작업을 파괴하기 때문. squash merge가 retire시킨 건 이 브랜치 하나뿐이다.

```bash
git fetch -p
HEAD_BRANCH=<PR headRefName>   # Step 1에서 받은 값
BASE=<PR baseRefName>          # Step 1에서 받은 값
MAIN_WT=$(git worktree list | head -1 | awk '{print $1}')
CURRENT_WT=$(git rev-parse --show-toplevel)

# 이 브랜치가 실제로 [gone] 상태인지 확인 (원격 삭제 반영됐는지)
track=$(git for-each-ref --format '%(upstream:track)' "refs/heads/$HEAD_BRANCH")
if [ "$track" != "[gone]" ]; then
  echo "브랜치 '$HEAD_BRANCH' 미존재 또는 [gone] 아님 — 로컬 정리 skip"
else
  worktree=$(git worktree list | grep "\\[$HEAD_BRANCH\\]" | awk '{print $1}')
  if [ "$worktree" = "$CURRENT_WT" ] && [ "$CURRENT_WT" != "$MAIN_WT" ]; then
    echo "⏭  현재 작업 중인 linked worktree — 정리는 세션 종료 시 keep/remove 프롬프트에서. remove를 고르면 워크트리와 브랜치 '$HEAD_BRANCH'가 함께 삭제되고, keep이면 둘 다 남는다."
  elif [ "$worktree" = "$CURRENT_WT" ]; then
    git checkout "$BASE" && git branch -D "$HEAD_BRANCH" \
      || echo "브랜치 '$HEAD_BRANCH' 보존 — $BASE로 checkout 실패 (위 git 출력 확인)"
  else
    if [ -n "$worktree" ]; then
      echo "Removing worktree: $worktree"
      git worktree remove --force "$worktree"
    fi
    echo "Deleting branch: $HEAD_BRANCH"
    git branch -D "$HEAD_BRANCH"
  fi
fi
```

- **현재 linked worktree 자신은 제거하지 않는다** — worktree 세션은 자기 worktree에 `git worktree lock`을 걸고 현재 브랜치가 체크아웃 상태라 `worktree remove`와 `branch -D` 모두 실패. 보존 후, 세션 종료 시 keep/remove 프롬프트에서 정리하도록 안내만(종료 키는 환경마다 달라 특정 키 언급 X).
- **메인 워크트리는 다르다.** 거기서 PR 브랜치를 체크아웃한 채 머지하면 `git worktree list`가 메인 워크트리를 그 브랜치 소유로 보여주지만, 이건 정리를 건너뛸 이유가 아니다 — base로 checkout하면 브랜치를 지울 수 있다. 워크트리 자체는 그대로 둔다.
- **다른 `[gone]` 브랜치는 건드리지 않는다** — 책임은 방금 머지한 PR 브랜치까지. 누적 `[gone]` 정리는 별도 사용자 판단·별도 도구 몫.

### Step 6. base 브랜치 로컬 동기화

```bash
BASE=<PR baseRefName>   # Step 1에서 받은 값 (보통 main, develop 등일 수 있음)
MAIN_WT=$(git worktree list | head -1 | awk '{print $1}')
CURRENT_WT=$(git rev-parse --show-toplevel)
if [ "$CURRENT_WT" = "$MAIN_WT" ]; then
  if [ -n "$(git status --porcelain)" ]; then
    if [ "$(git branch --show-current)" = "$BASE" ]; then
      # 미커밋 변경이 base 위에 있음 — pull도 fetch도 안 되므로 보고만 한다
      echo "$BASE에 미커밋 변경이 있어 동기화 skip — 커밋하거나 stash한 뒤 직접 pull하세요"
    else
      # 다른 세션의 미커밋 변경 — checkout으로 건드리지 않고 ref만 갱신
      git fetch origin "$BASE:$BASE" \
        && echo "미커밋 변경 있어 checkout 없이 로컬 $BASE ref만 fast-forward"
    fi
  else
    git checkout "$BASE" && git pull --ff-only
  fi
else
  # linked worktree에서 실행 중 — base는 메인 워크트리 소유. 여기서 checkout 강행 X (already checked out 실패).
  git fetch origin "$BASE:$BASE" 2>/dev/null \
    && echo "로컬 $BASE ref fast-forward 완료 (현재 worktree 유지)" \
    || echo "$BASE 동기화 skip — 메인 워크트리에서 수행하세요 (현재 linked worktree)"
fi
```

- base는 `main` 고정 X → Step 1의 `baseRefName` 사용(develop 등 비-main 대응).
- fast-forward 실패 시 보고만, 강제 진행 X. 미커밋 변경은 어느 경로에서도 그대로 둔다.
- 분기 근거: dirty 워크트리에서 `git pull`은 실패하고(전역 `pull.rebase=true`면 rebase 거부), 체크아웃된 브랜치로는 `git fetch origin <base>:<base>`도 거부된다.

## Execution

Step 1-2는 분석 단계. **Step 3 확인 후** Step 4→5→6을 **순차** 실행 — 머지로 원격 브랜치가 삭제돼야 `git fetch -p`가 `[gone]`을 감지하므로, 이 세 단계는 데이터 의존이 있어 병렬 묶음 X.

**git·gh 외 도구 금지** (Read/Edit/Write/TaskCreate 등 X). 마지막에 merge PR URL + 정리한 PR 브랜치(또는 보존 사유) 출력.

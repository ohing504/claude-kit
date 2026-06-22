---
name: squash-merge
description: PR을 squash merge하고 squash 메시지 정리(net diff만, PR 내부 단계 차단)·로컬 [gone] 브랜치 정리·main 동기화까지 한 흐름. "스쿼시 머지", "머지하자" 발화에 — merge 실행 전 확인.
argument-hint: <pr-number-optional>
allowed-tools: Bash(gh:*), Bash(git:*)
---

# Squash Merge

## Context
- 현재 브랜치: !`git branch --show-current`
- PR 번호 인자: `$1` (생략 시 현재 branch 연결 PR auto detect)

## Task

PR squash merge → 메시지 정리 → 로컬 정리 한 흐름으로 실행.

### Step 1. PR 식별 + 분석

PR 번호 인자(`$1`) 없으면 `gh pr view --json number,headRefName,baseRefName,title,body,state`로 현재 branch 연결 PR auto detect. detect 실패 시 사용자에게 PR 번호 요청 후 종료.

PR 정보 + 변경 사항:
- `gh pr view <NUM> --json number,headRefName,baseRefName,title,commits,files,state,mergeable,mergeStateStatus`
- `gh pr diff <NUM>` (full net diff)

`baseRefName`은 Step 6 동기화에 재사용하므로 기억해 둔다.

PR이 이미 머지/닫힘 상태면 squash 단계 skip하고 Step 5(로컬 정리)부터 진행.

**머지 가능 사전 점검**: `mergeable == CONFLICTING` 또는 `mergeStateStatus ∈ {DIRTY, BLOCKED, DRAFT, BEHIND}`면 멈추고 사유 보고 — 강제 진행 X (충돌·필수 체크 미통과·base 뒤처짐·초안). `UNKNOWN`이면 잠시 후 재조회. `UNSTABLE`(일부 체크 실패·진행 중이나 머지는 가능)은 사용자에게 경고 후 판단 요청.

### Step 2. squash 메시지 작성 — net diff 사실 기반

**기준**: PR base 대비 head의 **net diff**만 보고 작성 — 중간 commit history 인용 X.

**차단 (session-context bleed)**:
- PR 내 자체 발견 버그·수정 commit
- 되돌린 작업 (revert·restore)
- 중간 refactor·rename 후 재변경 흔적
- 개별 commit message 인용
- 세션 발화·블로커·디버깅 과정·키 디시전 번호(D-NN) 인용

**형식**:
- subject: `type(scope): summary` — recent commits + CLAUDE.md 컨벤션 일치
- body: 5줄 이내 bullet — net 변경만, HEREDOC

### Step 3. 실행 전 확인 게이트 (자동 발화·명시 호출 공통)

merge 전 **대상 PR(번호·제목) + squash subject/body를 제시하고 confirm 받는다** — 확인 없이 merge 실행 X (destructive·복구 곤란). "머지하자" 류 자연어 진입도 raw git/gh로 직접 처리 X, 반드시 본 흐름(Step 2 포함).

### Step 4. squash merge 실행

```bash
gh pr merge <NUM> --squash --delete-branch --subject "<subject>" --body "$(cat <<'EOF'
<body>
EOF
)"
```

GitHub 기본(개별 commit 이어붙이기) 사용 X — `--subject` + `--body` 명시 의무.

`--delete-branch`로 머지 직후 원격 head 브랜치를 삭제 → Step 5의 `[gone]` 감지를 보장한다 (repo의 auto-delete 설정과 무관하게 일관 동작). gh가 이어서 시도하는 로컬 브랜치 삭제는 worktree를 인식하지 못해 실패할 수 있으나 무방 — 로컬 정리는 Step 5가 worktree-aware하게 담당한다.

### Step 5. 로컬 [gone] 정리 (worktree 처리 포함)

```bash
git fetch -p
CURRENT_WT=$(git rev-parse --show-toplevel)
git for-each-ref --format '%(refname:short) %(upstream:track)' | \
  awk '$2 == "[gone]" {print $1}' | while read branch; do
  echo "Processing branch: $branch"
  worktree=$(git worktree list | grep "\\[$branch\\]" | awk '{print $1}')
  if [ -n "$worktree" ] && [ "$worktree" = "$CURRENT_WT" ]; then
    echo "  ⏭  현재 작업 중인 worktree — Claude Code worktree 세션이라 정리는 세션 종료 시 keep/remove 프롬프트에서. 브랜치 '$branch'도 worktree와 함께 보존."
    continue
  fi
  if [ -n "$worktree" ]; then
    echo "  Removing worktree: $worktree"
    git worktree remove --force "$worktree"
  fi
  echo "  Deleting branch: $branch"
  git branch -D "$branch"
done
```

**현재 worktree 자기 자신은 절대 제거·삭제 시도 X.** Claude Code worktree 세션은 실행 동안 자기 worktree에 `git worktree lock`을 걸어 외부 cleanup을 막고(공식 동작), 현재 브랜치는 체크아웃 상태라 — `git worktree remove`도 `git branch -D`도 실패한다. 이 경우 위 스크립트처럼 `continue`로 통째로 건너뛰고, 세션 종료 시 Claude Code가 띄우는 keep/remove worktree 프롬프트에서 정리하도록 안내만 한다 (종료 키 시퀀스는 환경마다 다르므로 특정 키를 안내하지 않는다).

[gone] 브랜치가 없으면 "로컬 정리 대상 없음" 보고.

### Step 6. base 브랜치 로컬 동기화

```bash
BASE=<PR baseRefName>   # Step 1에서 받은 값 (보통 main, develop 등일 수 있음)
MAIN_WT=$(git worktree list | head -1 | awk '{print $1}')
CURRENT_WT=$(git rev-parse --show-toplevel)
if [ "$CURRENT_WT" = "$MAIN_WT" ]; then
  git checkout "$BASE" && git pull --ff-only
else
  # linked worktree에서 실행 중 — base는 메인 워크트리 소유. 여기서 checkout 강행 X (already checked out 실패).
  git fetch origin "$BASE:$BASE" 2>/dev/null \
    && echo "로컬 $BASE ref fast-forward 완료 (현재 worktree 유지)" \
    || echo "$BASE 동기화 skip — 메인 워크트리에서 수행하세요 (현재 linked worktree)"
fi
```

base 브랜치는 `main` 고정이 아니라 **Step 1에서 받은 `baseRefName`**을 쓴다 (develop 등 비-main base 대응). fast-forward 실패 시(로컬 base 미커밋 변경 등) 보고하고 강제 진행 X. linked worktree에서는 `git checkout`을 강행하지 않는다 — base가 메인 워크트리에 이미 체크아웃되어 있어 실패하기 때문.

## Execution

Step 1-2는 분석 단계. **Step 3 확인 후** Step 4→5→6을 **순차** 실행 — 머지로 원격 브랜치가 삭제돼야 `git fetch -p`가 `[gone]`을 감지하므로, 이 세 단계는 데이터 의존이 있어 병렬 묶음 X.

**git·gh 외 도구 금지** (Read/Edit/Write/TaskCreate 등 X). 마지막에 merge PR URL + 정리된 [gone] 브랜치 목록 출력.

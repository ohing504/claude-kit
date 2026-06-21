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
- `gh pr view <NUM> --json number,headRefName,baseRefName,title,commits,files,state`
- `gh pr diff <NUM>` (full net diff)

PR이 이미 머지/닫힘 상태면 squash 단계 skip하고 Step 4(로컬 정리)부터 진행.

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
gh pr merge <NUM> --squash --subject "<subject>" --body "$(cat <<'EOF'
<body>
EOF
)"
```

GitHub 기본(개별 commit 이어붙이기) 사용 X — `--subject` + `--body` 명시 의무.

### Step 5. 로컬 [gone] 정리 (worktree 처리 포함)

```bash
git fetch -p
git for-each-ref --format '%(refname:short) %(upstream:track)' | \
  awk '$2 == "[gone]" {print $1}' | while read branch; do
  echo "Processing branch: $branch"
  worktree=$(git worktree list | grep "\\[$branch\\]" | awk '{print $1}')
  if [ -n "$worktree" ] && [ "$worktree" != "$(git rev-parse --show-toplevel)" ]; then
    echo "  Removing worktree: $worktree"
    git worktree remove --force "$worktree"
  fi
  echo "  Deleting branch: $branch"
  git branch -D "$branch"
done
```

[gone] 브랜치가 없으면 "로컬 정리 대상 없음" 보고.

### Step 6. main 로컬 동기화

```bash
git checkout main && git pull --ff-only
```

fast-forward 실패 시(로컬 main 미커밋 변경 등) 보고하고 강제 진행 X.

## Execution

Step 1-2는 분석 단계. **Step 3 확인 후** Step 4-6(merge·로컬 정리·동기화)을 한 메시지에 multiple tools로 묶어 실행.

**git·gh 외 도구 금지** (Read/Edit/Write/TaskCreate 등 X). 마지막에 merge PR URL + 정리된 [gone] 브랜치 목록 출력.

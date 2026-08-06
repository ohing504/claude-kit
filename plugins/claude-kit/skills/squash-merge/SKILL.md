---
name: squash-merge
description: PR을 squash merge하고 squash 메시지 정리(net diff만, PR 내부 단계 차단)·방금 머지한 PR 브랜치만 로컬 정리·base 동기화까지 한 흐름. "스쿼시 머지", "머지하자" 발화에 — merge 실행 전 확인.
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
- `gh pr view <NUM> --json number,headRefName,baseRefName,title,commits,files,state,mergeable,mergeStateStatus`
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
- 개별 commit message 인용
- 세션 발화·블로커·디버깅 과정·키 디시전 번호(D-NN) 인용

**형식**:
- subject: `type(scope): summary` — recent commits + CLAUDE.md 컨벤션 일치
- body: 5줄 이내 bullet — net 변경만, HEREDOC

### Step 3. 실행 전 확인 게이트 (자동 발화·명시 호출 공통)

**흐름: ① PR(번호·제목) + squash subject/body를 응답 본문에 코드블록으로 출력 → ② confirm.** 확인 없이 merge X (destructive·복구 곤란).

- **subject/body는 본문 텍스트로.** AskUserQuestion `preview` 필드에만 담지 말 것 — preview는 터미널 전용이라 데스크탑·모바일에선 사라져, 사용자가 내용 없이 승인 버튼만 본다.
- confirm 수단은 자유(AskUserQuestion·평문). 내용이 본문에 있으면 매체 무관 표시 — `preview`는 중복일 뿐 유일 표시처 X.
- "머지하자" 류 자연어 진입도 raw git/gh 직접 처리 X — 본 흐름(Step 2 포함) 경유.

**`--auto` 지정 시**: ②의 confirm만 생략하고 Step 4로 직행. ①(PR 정보 + subject/body 출력)은 그대로 수행해 무엇을 머지했는지 기록으로 남긴다. Step 1의 머지 가능 사전 점검은 `--auto`에서도 동일 적용 — 충돌, 필수 체크 미통과, 초안, base 뒤처짐은 사용자 확인이 아니라 머지 안전성 문제라 옵션으로 우회하지 않는다.

### Step 4. squash merge 실행

```bash
gh pr merge <NUM> --squash --delete-branch --subject "<subject>" --body "$(cat <<'EOF'
<body>
EOF
)"
```

- GitHub 기본(개별 commit 이어붙이기) X — `--subject` + `--body` 명시 의무.
- `--delete-branch`: 원격 head 즉시 삭제 → Step 5의 `[gone]` 감지 보장(repo auto-delete 설정 무관). 이어지는 gh의 로컬 삭제는 worktree 미인식으로 실패해도 무방 — 로컬 정리는 Step 5(worktree-aware) 담당.

### Step 5. 방금 머지한 PR 브랜치만 로컬 정리 (worktree 처리 포함)

**정리 대상은 오직 이번에 머지한 PR의 head 브랜치 하나** (Step 1의 `headRefName`). 전역 `[gone]` 스윕 금지 — 무관한 브랜치·다른 동시 세션의 활성 worktree까지 `--force`로 날려 미커밋 작업을 파괴하기 때문. squash merge가 retire시킨 건 이 브랜치 하나뿐이다.

```bash
git fetch -p
HEAD_BRANCH=<PR headRefName>   # Step 1에서 받은 값
CURRENT_WT=$(git rev-parse --show-toplevel)

# 이 브랜치가 실제로 [gone] 상태인지 확인 (원격 삭제 반영됐는지)
track=$(git for-each-ref --format '%(upstream:track)' "refs/heads/$HEAD_BRANCH")
if [ "$track" != "[gone]" ]; then
  echo "브랜치 '$HEAD_BRANCH' 미존재 또는 [gone] 아님 — 로컬 정리 skip"
else
  worktree=$(git worktree list | grep "\\[$HEAD_BRANCH\\]" | awk '{print $1}')
  if [ -n "$worktree" ] && [ "$worktree" = "$CURRENT_WT" ]; then
    echo "⏭  현재 작업 중인 worktree — Claude Code worktree 세션이라 정리는 세션 종료 시 keep/remove 프롬프트에서. 브랜치 '$HEAD_BRANCH'도 worktree와 함께 보존."
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

- **현재 worktree 자신은 제거·삭제 X** — worktree 세션은 자기 worktree에 `git worktree lock`을 걸고 현재 브랜치가 체크아웃 상태라 `worktree remove`·`branch -D` 모두 실패. 보존 후, 세션 종료 시 keep/remove 프롬프트에서 정리하도록 안내만(종료 키는 환경마다 달라 특정 키 언급 X).
- **다른 `[gone]` 브랜치는 건드리지 않는다** — 책임은 방금 머지한 PR 브랜치까지. 누적 `[gone]` 정리는 별도 사용자 판단·별도 도구 몫.

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

- base는 `main` 고정 X → Step 1의 `baseRefName` 사용(develop 등 비-main 대응).
- fast-forward 실패 시(로컬 base 미커밋 변경 등) 보고 후 강제 진행 X.
- linked worktree에선 `git checkout` 강행 X — base가 메인 워크트리에 이미 체크아웃돼 실패.

## Execution

Step 1-2는 분석 단계. **Step 3 확인 후** Step 4→5→6을 **순차** 실행 — 머지로 원격 브랜치가 삭제돼야 `git fetch -p`가 `[gone]`을 감지하므로, 이 세 단계는 데이터 의존이 있어 병렬 묶음 X.

**git·gh 외 도구 금지** (Read/Edit/Write/TaskCreate 등 X). 마지막에 merge PR URL + 정리한 PR 브랜치(또는 보존 사유) 출력.

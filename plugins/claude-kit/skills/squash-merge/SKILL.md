---
name: squash-merge
description: PR을 squash merge하고 squash 메시지 정리(net diff만, PR 내부 단계 차단), 원격 브랜치 삭제까지 한 흐름. 메인 체크아웃에서 실행하면 로컬 브랜치 삭제와 base 동기화도 하고, 워크트리는 지우지 않는다. "스쿼시 머지", "머지하자" 발화에 — merge 실행 전 확인(`--auto` 인자로만 생략).
argument-hint: "[--auto] [<pr#>|<branch>|<url>]"
allowed-tools: Read, Bash(gh:*), Bash(git:*), Bash(${CLAUDE_SKILL_DIR}/scripts/post_merge.sh *)
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

- `gh pr view <NUM> --json number,headRefName,headRefOid,baseRefName,title,body,commits,files,state,mergeable,mergeStateStatus,author`
- `gh pr diff <NUM>` (full net diff)

`headRefName`, `headRefOid`, `baseRefName`은 Step 5에 넘기므로 기억해 둔다.

PR이 이미 머지/닫힘 상태면 squash 단계 skip하고 Step 5부터 진행.

**머지 가능 사전 점검**:

- `mergeable == CONFLICTING` 또는 `mergeStateStatus ∈ {DIRTY, BLOCKED, DRAFT, BEHIND}` → 멈추고 사유 보고, 강제 진행 X (충돌, 필수 체크 미통과, base 뒤처짐, 초안).
- `UNKNOWN` → 잠시 후 재조회.
- `UNSTABLE`(일부 체크 실패, 진행 중이나 머지 가능) → 경고 후 판단 요청.

**미커밋 파일 점검**: linked 워크트리에서 실행 중이면(`git rev-parse --git-dir`와 `--git-common-dir`가 다르면) `git status --short`를 확인한다. 데스크톱 앱은 세션에서 Claude가 연 PR이 머지된 뒤 untracked 파일을 묻지 않고 지울 수 있다. 결과는 Step 3에서 쓴다. 메인 체크아웃의 미커밋 변경은 다른 세션의 것일 수 있어 점검 대상이 아니다.

### Step 2. squash 메시지 작성

`references/squash-message.md`를 Read해 규격대로 subject와 body를 쓴다. PR base 대비 head의 net diff만 사실로 쓴다.

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
- **봇 의존성 PR(메시지 규격의 예외)은 `--body ""`.** HEREDOC 없이 빈 문자열을 그대로 넘긴다 — `--body`를 생략하면 저장소의 `squash_merge_commit_message` 설정(대개 `PR_BODY`)이 되살아나 릴리즈 노트 전문이 커밋에 들어간다.
- **`--delete-branch`(`-d`) 사용 금지.** 이 옵션은 원격만이 아니라 로컬까지 정리하는데, 그 과정에서 gh가 현재 워크트리에서 base를 checkout하고 `git pull`을 실행한다. 다른 세션의 미커밋 변경이 워크트리에 있으면 그 pull이 실패하고(사용자 `pull.rebase=true`면 rebase 거부 메시지), 체크아웃된 브랜치만 바뀐 채 남는다. 원격 브랜치 삭제와 로컬 정리는 Step 5가 한다.

### Step 5. 머지 뒤 정리

```bash
${CLAUDE_SKILL_DIR}/scripts/post_merge.sh <headRefName> <baseRefName> <headRefOid>
```

원격 브랜치는 실행 위치와 무관하게 남아 있으면 지운다. 그 뒤 동작은 실행 위치로 정해진다.

| 실행 위치 | 동작 |
|---|---|
| 메인 체크아웃 | 머지한 브랜치를 지우고 base를 동기화한다. 미커밋 변경, PR에 없는 커밋, 다른 워크트리가 쓰는 브랜치는 건드리지 않고 사유를 출력한다. |
| 데스크톱 앱 워크트리 | 폴더와 브랜치를 앱에 맡긴다. |
| 그 밖의 linked 워크트리 | 폴더와 브랜치를 세션 종료 프롬프트에 맡긴다. |

- **이 스킬은 워크트리를 지우지 않는다.** 다른 세션이 쓰는 중일 수 있어 위 세 경우 모두 폴더를 남긴다.
- **방금 머지한 브랜치만 다룬다.** 전역 `[gone]` 스윕을 하지 않는다. 쌓인 워크트리와 브랜치 정리는 이 스킬의 범위가 아니다.

## Execution

Step 1-2는 분석 단계. **Step 3 확인 후** Step 4→5를 순차 실행. 마지막에 merge PR URL과 스크립트 출력을 그대로 보고한다.

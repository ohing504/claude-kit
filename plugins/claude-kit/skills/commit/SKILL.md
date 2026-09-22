---
name: commit
description: 변경을 commit하고 요청 범위에 따라 push와 PR 생성까지 확장. 열린 PR에 commit을 더 push하면 PR 본문도 다시 쓴다. commit message와 PR 본문은 git diff와 git log 사실만 반영(세션 대화와 디버깅 과정 차단). "커밋해줘"는 commit만, "커밋하고 PR", "PR 만들어줘"는 push+PR — push와 PR 전 확인, 모호하면 commit만.
allowed-tools: Bash(git:*), Bash(gh pr create:*), Bash(gh pr edit:*), Bash(gh pr view:*)
---

# Commit

## Context
- 현재 상태: !`git status`
- 변경 사항: !`git diff HEAD`
- 신규 파일(untracked): !`git ls-files --others --exclude-standard`
- 현재 브랜치: !`git branch --show-current`
- 기본 브랜치: !`git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's@^origin/@@' | grep . || echo "(미설정 — main 가정)"`
- 최근 커밋: !`git log --oneline -10`

## 범위 판단

발화에서 작업 범위를 정한다 — 모호하면 commit만, push와 PR은 명시 의도일 때만. commit만 한 뒤 push와 PR이 필요해 보이면 "push와 PR도 진행할까요?"를 한 줄로 제안한다.

## commit message와 PR 본문 (공통)

**사실 출처는 diff다.** commit은 위 `git diff HEAD`, PR은 base 대비 branch 전체(`git log <base>..HEAD`). 단 `git diff HEAD`는 신규(untracked) 파일을 포함하지 않으므로, 위 '신규 파일' 목록에 항목이 있으면 `git diff --no-index /dev/null <file>`로 직접 확인한다.

**넣지 않는다**: 세션 대화(사용자 발화, 결정 과정, 블로커), 작업 중 발견한 버그와 디버깅 시도, 되돌린 작업.

**제목은 그 줄만 읽어도 이해되게** (self-contained). 이슈 번호나 문서명이나 내부 코드네임을 *내용 대신* 쓰지 않는다 — 찾아봐야 알면 `git log` 훑기가 무의미해진다.
- ❌ `docs: 이슈 관리를 최상위 #38 기준으로 정합` / ✅ `docs: 리팩토링 이슈를 목적 기준 계층으로 재편` (참조는 본문이나 말미 `Closes #38`로)
- **`wip:` 금지** — 미완 상태를 커밋에 적으면 그게 stale 사본이 된다.
- **비유와 은유 금지.** 무슨 동작인지 그대로 쓴다 — 삭제, 추가, 이동, 교체. 읽는 쪽이 무엇을 한 변경인지 유추해야 하면 `git log`로 찾을 수 없다.
  - ❌ `refactor: 옛 구조를 걷어내고 판정 기준을 세운다` / ✅ `refactor: 옛 렌더 경로를 삭제하고 판정 기준 문서를 확정`

형식과 언어는 이 순서로 정한다:

1. 프로젝트 CLAUDE.md 컨벤션
2. recent commits 패턴
3. 둘 다 없으면 Conventional Commits — `type(scope): 요약`, 본문은 무엇과 왜만 (어떻게는 코드에)

## commit

**staging 범위**: 이번 작업에서 변경한 파일만 경로로 명시해 add. `git add -A`와 디렉토리째 add는 의도가 명확할 때만. 프로젝트 CLAUDE.md에 staging 규약이 있으면 그것을 따른다.

`--no-verify` 금지. pre-commit hook이 실패하면 보고하고, hook이 지적한 것을 고친 뒤 재커밋한다.

## push + PR (확장 범위일 때만)

1. **branch** — 현재 브랜치가 기본 브랜치(위 Context의 '기본 브랜치' 값)면 commit 전 새 feature branch 생성.
2. **실행 전 확인** — branch, commit 메시지, PR 초안(제목과 본문)을 제시하고 confirm. push와 PR은 되돌리기 어렵다.
3. **push** — `git push -u origin <branch>`
4. **PR 생성** — `gh pr create --base <기본 브랜치>`
5. **열린 PR에 commit을 더 push했으면 본문을 다시 쓴다** — `gh pr edit <N> --body-file -`. 본문은 생성 시점이 아니라 지금의 net diff를 서술한다.

```markdown
## 무엇이 바뀌나
(net diff 한두 줄)

## 왜
(이슈 링크 한 줄. 없으면 한 문장)

Closes #12
```

테스트와 lint 결과는 적지 않는다. CI가 PR 페이지에 붙이고, 본문에 손으로 적은 것은 아무도 대조하지 않는다.

생성하거나 갱신한 PR의 URL을 마지막에 출력한다.

**git과 gh 외 도구는 쓰지 않는다.** Read, Edit, Write로 파일을 열지 않는다.

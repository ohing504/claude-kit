---
name: commit
description: 변경을 commit하고 요청 범위에 따라 push·PR 생성까지 확장. commit message·PR 본문은 git diff·log 사실만 반영(세션 대화·디버깅 과정 차단). "커밋해줘"는 commit만, "커밋하고 PR"·"PR 올려줘"는 push+PR — push·PR 전 확인, 모호하면 commit만.
allowed-tools: Bash(git:*), Bash(gh pr create:*)
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

발화에서 작업 범위를 정한다 — 모호하면 *commit만*(좁게·안전), push·PR은 명시 의도일 때만:
- **commit만**: "커밋해줘", "커밋", 범위 미언급
- **commit + push + PR**: "커밋하고 PR", "PR 올려줘", "푸시하고 PR" 등 push·PR 명시
- commit만 한 뒤 push·PR이 필요해 보이면 "push·PR도 진행할까요?" 한 줄 제안 (강제 X)

## commit (공통)

위 git diff의 **실제 코드 변경 사항만** 분석해 commit message 작성. 단 `git diff HEAD`는 신규(untracked) 파일을 포함하지 않으므로, 위 '신규 파일' 목록에 항목이 있으면 그 내용을 직접 확인(`git diff --no-index /dev/null <file>`)해 메시지·staging에 반영한다.

**엄격히 차단** (session-context bleed):
- 본 세션 사용자 발화·블로커·결정 과정
- 작업 중 발견한 버그·디버깅 시도·되돌린 작업
- 동형 분석·키 디시전 번호 인용 (D-NN 식)
- 코드 변경 / git log 범위와 무관한 대화 맥락

**staging 범위**: 프로젝트 CLAUDE.md에 staging 규약(여러 세션 동시 작업·폴더째 add 금지·hunk 단위 확인 등)이 있으면 그것을 *우선* 따른다. 없으면 이번 작업에서 실제로 변경한 파일만 경로로 명시해 add — `git add -A`/`.`/디렉토리째 add는 의도가 명확할 때만. 한 파일에 타 작업 변경이 섞일 수 있는 환경이면 stage 전 `git diff <file>`로 내 변경만 있는지 확인.

**헤더는 그 줄만 읽어도 이해되게** (self-contained). 이슈 번호나 문서명이나 내부 코드네임을 *내용 대신* 쓰지 않는다 — 찾아봐야 알면 `git log` 훑기가 무의미해진다.
- ❌ `docs: 이슈 관리를 최상위 #38 기준으로 정합` / ✅ `docs: 리팩토링 이슈를 목적 기준 계층으로 재편` (참조는 본문이나 말미 `Closes #38`로)
- **`wip:` 금지** — 미완 상태를 커밋에 적으면 그게 stale 사본이 된다.

메시지 형식과 언어는 이 순서로 정한다:

1. 프로젝트 CLAUDE.md 컨벤션
2. recent commits 패턴
3. 둘 다 없으면 Conventional Commits — `type(scope): 요약`, 본문은 무엇과 왜만 (어떻게는 코드에)

Claude Code 기본 git commit 절차 적용 (HEREDOC, --no-verify 금지). pre-commit hook이 실패하면 보고하고 강제 진행 X — `--no-verify` 우회 금지, hook 지적을 fix한 뒤 재커밋. commit만이면 위 staging 규약대로 stage + commit을 한 메시지로 묶어 실행.

## push + PR (확장 범위일 때만)

1. **branch** — 현재 브랜치가 기본 브랜치(위 Context의 '기본 브랜치' 값, 보통 main·master)면 commit 전 새 feature branch 생성.
2. **실행 전 확인** — branch·commit 메시지·PR 초안(제목·본문)을 제시하고 confirm. push·PR은 outward·되돌리기 어려운 액션이라 자동 발화 시 게이트 필수.
3. **push** — `git push -u origin <branch>`
4. **PR** — `gh pr create --base <기본 브랜치>`. PR 본문은 base 대비 branch 전체 commit 범위(`git log <base>..HEAD`) 사실 기반. session-context guard는 PR 본문에도 동일 적용.

**PR 본문 4블록** — 검증 증거를 여기 몰아넣는다. 이슈 본문의 주장은 아무도 대조하지 않지만, PR 본문은 diff와 CI 옆에 놓여 거짓이면 바로 드러난다.

```markdown
## 무엇이 바뀌나
(net diff 한두 줄. 중간에 시도했다 되돌린 것은 쓰지 않는다)

## 왜
(이슈 링크 한 줄. 없으면 한 문장)

## 검증
$ pnpm test -- routes
  12 passed

Closes #42
```

- **검증 블록은 실제 실행한 명령과 출력**을 넣는다. "테스트 통과함" 같은 요약으로 대체하지 않는다
- **`Closes #N`은 PR이 기본 브랜치를 타겟할 때만 동작한다.** base가 기본 브랜치가 아니면 키워드가 무시되고 머지해도 이슈에 아무 영향이 없다 — 그 경우 머지 후 `gh issue close`가 별도로 필요함을 보고한다
- 이슈 1개 = PR 1개. 거절된 agentic PR은 17% 더 많은 줄, 10% 더 많은 파일을 건드린다

생성된 PR URL을 마지막에 출력.

## Execution

push+PR은 *확인을 받은 뒤* branch·add·commit·push·gh pr create을 sequential dependency 순서로 실행.

**확인·git·gh 외 도구 사용 금지.** Read/Edit/Write/TaskCreate 등 사용 X — lean execution이 session-context guard의 effective 강화.

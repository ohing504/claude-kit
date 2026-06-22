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

메시지 형식·언어는 recent commits + 프로젝트 CLAUDE.md 컨벤션. Claude Code 기본 git commit 절차 적용 (HEREDOC, --no-verify 금지). pre-commit hook이 실패하면 보고하고 강제 진행 X — `--no-verify` 우회 금지, hook 지적을 fix한 뒤 재커밋. commit만이면 위 staging 규약대로 stage + commit을 한 메시지로 묶어 실행.

## push + PR (확장 범위일 때만)

1. **branch** — 현재 브랜치가 기본 브랜치(위 Context의 '기본 브랜치' 값, 보통 main·master)면 commit 전 새 feature branch 생성.
2. **실행 전 확인** — branch·commit 메시지·PR 초안(제목·본문)을 제시하고 confirm. push·PR은 outward·되돌리기 어려운 액션이라 자동 발화 시 게이트 필수.
3. **push** — `git push -u origin <branch>`
4. **PR** — `gh pr create --base <기본 브랜치>`. PR 본문은 base 대비 branch 전체 commit 범위(`git log <base>..HEAD`) 사실 기반. session-context guard는 PR 본문에도 동일 적용. Test plan은 실제 변경 영역 한정.

생성된 PR URL을 마지막에 출력.

## Execution

push+PR은 *확인을 받은 뒤* branch·add·commit·push·gh pr create을 sequential dependency 순서로 실행.

**확인·git·gh 외 도구 사용 금지.** Read/Edit/Write/TaskCreate 등 사용 X — lean execution이 session-context guard의 effective 강화.

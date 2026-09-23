---
name: leave-a-will
description: 세션을 끝내거나 다음 세션으로 넘기기 전에 남은 것(commit, push, PR, 돌고 있는 작업, 기록하지 않은 결정, 미룬 논의)을 모아 항목별로 처분하고, 진행 중인 작업이 남으면 scratchpad에 핸드오프 문서를 쓴다. "세션 끝내도 돼?", "마무리하자", "남은 거 있어?", "핸드오프 문서 써줘", "다음 세션으로 넘기자" 발화에 쓴다.
allowed-tools: Bash(git:*), Bash(gh pr:*), Bash(grep:*), Bash(jq:*), Read, Write, Agent
---

# leave-a-will

## Context

- git: !`git status --short --branch 2>/dev/null; git log @{u}..HEAD --oneline 2>/dev/null; git worktree list 2>/dev/null`
- PR: !`gh pr view --json number,state,url --jq '"#\(.number) \(.state) \(.url)"' 2>/dev/null || echo "(없음)"`
- 세션 기록: !`f=$(ls ~/.claude/projects/*/"$CLAUDE_CODE_SESSION_ID".jsonl 2>/dev/null | head -1); [ -n "$f" ] && echo "$f (compact $(grep -c '"compact_boundary"' "$f")회)" || echo "(없음)"`

## 1. 모은다

- git: commit하지 않은 변경, push하지 않은 commit, 열린 PR, 남은 worktree
- 세션: 돌고 있는 백그라운드 작업, 서브에이전트, cron
- 대화: 기록하지 않은 결정, 미룬 논의와 답하지 않은 질문, 검증하지 않은 완료 주장, 사용자의 작업 방식 교정, 접어 둔 아이디어

compact된 세션이면 compact 요약의 `Pending Tasks`와 먼저 대조한다. 요약만으로 부족할 때만 마지막 compact 이전 대화를 뽑아 `model: haiku` Agent에게 위 대화 항목을 `[L줄번호]`와 짧은 인용을 붙여 찾게 한다. 파일이 크면 줄 범위를 나눠 여러 Agent에 맡긴다.

```bash
f=<세션 기록>; L=$(grep -n '"compact_boundary"' "$f" | tail -1 | cut -d: -f1)
head -n "$L" "$f" | jq -r 'select((.type=="user" or .type=="assistant") and .isMeta != true and .isCompactSummary != true)
  | (.message.content | if type=="string" then . else map(select(.type=="text").text) | join("\n") end
     | gsub("<system-reminder>.*?</system-reminder>"; ""; "p")) as $t
  | select($t | test("\\S")) | "[L\(input_line_number) \(.type)] \($t)"' > <scratchpad>/pre-compact.txt
```

기록을 훑지 않았으면 판정에 "compact 이전은 요약으로만 확인"을 적는다.

## 2. 처분한다

항목마다 번호, 내용, 근거, 추천 처분을 표로 보이고 사용자가 번호로 정하게 한다.

처분: 지금 처리(`commit` 등) / 이슈(`git-issue`) / 아이디어(`idea-note`) / 메모리 / 문서 / 핸드오프 / 버림

- 여러 세션에 걸쳐 참이어야 하는 결정과 할 일은 핸드오프가 아니라 이슈, 메모리, 문서로 보낸다. 핸드오프 문서는 다음 세션이 한 번 읽고 버린다.
- 변경 버리기, worktree 삭제, 작업 중단은 사용자가 그 번호를 지정했을 때만 실행한다.

## 3. 판정한다

진행 중인 작업이 없으면 `잃을 것 없음`과 확인한 항목별 결과를 한 줄씩 출력한다.

남았으면 scratchpad에 `handoff.md`를 쓰고 경로와 `<경로> 읽고 이어가` 한 줄을 출력한다.

```markdown
# 핸드오프: <작업 이름>
작업 디렉토리: <절대 경로> / 브랜치: <이름>

## 목표
## 현재 상태      (끝난 것, 진행 중인 것, 마지막으로 통과한 체크)
## 진행 중 추론   (가설과 근거 좌표, 배제한 것과 이유)
## 막힌 지점      (없으면 생략)
## 다음 한 단계   (바로 실행할 명령이나 먼저 열 파일)
## 옮겨 둔 곳     (2단계에서 만든 이슈, 메모리, 문서 경로)
```

# squash 메시지의 이슈 참조 처리

## 결정

- **수집 범위** — PR body, PR 제목, 각 commit의 message에서 닫기 키워드와 `Refs`를 걷는다. squash 메시지가 개별 commit message를 인용하지 않는다는 규칙의 유일한 예외다.
- **형식** — 이슈 번호마다 키워드를 반복해 한 줄씩 적는다.
- **중복** — 여러 출처가 같은 이슈를 가리키면 한 줄로 합치고, 닫기 키워드와 `Refs`가 섞이면 닫기 키워드를 남긴다.
- **승격 금지** — `Refs`만 있던 이슈를 닫기 키워드로 바꾸지 않는다.
- **net diff 기준 적용** — 중간 commit이 단 참조라도 그 변경이 PR 안에서 되돌려졌으면 넣지 않는다.
- **발동 조건 판정 없음** — 그 줄이 실제로 이슈를 닫는지는 저장소 설정이 정하므로 스킬이 판정하지도 보고하지도 않는다.

## 확인

```check
{"checks": [
  {"cmd": "grep -c '이슈 참조 수집' plugins/claude-kit/skills/squash-merge/SKILL.md", "expect": "1"},
  {"cmd": "git grep -l '기본 브랜치를 타겟할 때만' -- ':!docs/decisions' | wc -l | tr -d ' '", "expect": "0"}
]}
```

## 근거

**사실** — GitHub 공식 문서 [Linking a pull request to an issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue)는 여러 이슈를 연결할 때 "Use full syntax for each issue"라며 `Resolves #10, resolves #123, resolves octo-org/octo-repo#100`을 예로 든다 (2026-08-13 조회). 키워드 하나에 번호를 쉼표로 이어 붙이면 첫 번호만 닫힌다.

**사실** — 같은 문서에 닫기 키워드는 PR이 저장소의 기본 브랜치에 머지될 때 동작한다고 적혀 있다.

**장점** — 커밋에만 적힌 참조가 squash 메시지에 남는다. 번호마다 키워드를 반복하므로 나머지 이슈가 열린 채 남지 않는다.

**단점** — 참조를 걷으려면 개별 commit message를 읽어야 해서, 그것을 인용하지 않는다는 규칙의 경계가 흐려진다. 되돌려진 작업의 참조를 빼는 판단은 자동으로 검증되지 않는다.

## 기각

- **닫기 키워드의 발동 조건을 스킬이 판정하고 보고한다** — base가 기본 브랜치인지 조회해 알리는 안. 언제 닫히는지는 저장소 설정이 정할 일이라 스킬이 대신 판정할 근거가 없다.
- **한 줄에 이슈 번호를 쉼표로 나열** — GitHub가 첫 번호만 닫는다.
- **PR body의 참조만 쓰고 commit은 보지 않는다** — 커밋에만 적힌 참조가 사라진다.

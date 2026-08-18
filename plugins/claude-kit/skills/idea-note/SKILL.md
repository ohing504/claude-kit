---
name: idea-note
description: 거친 아이디어를 짧은 인터뷰로 구체화해 저장소 GitHub Discussions의 Ideas 카테고리에 기록하는 도구. "아이디어 메모", "이런거 어때", "나중에 해보면", "아이디어 노트" 같은 요청 시 사용. 기능 정의(스펙 문서), 착수할 작업(이슈), 대화 내 작업 추적(TaskCreate)에는 사용 안 함.
argument-hint: "[적어둘 아이디어]"
allowed-tools: Bash(gh repo view:*), Bash(gh api:*), Read, Write, Edit, AskUserQuestion
---

# idea-note

아이디어를 받아 저장소 Discussions에 기록한다. **하는 일은 추가 하나다.**

아이디어는 대부분 쓰이지 않는다. 여기는 버리기 아까운 것을 짧은 절차로 남겨 두는 위치이지 언젠가 실행할 목록이 아니다. 그래서 알림, 정기 리뷰, 우선순위 정렬을 붙이지 않는다.

## 어디에 쓰나

Discussions가 정본이다. 파일은 GitHub remote가 없거나 사용자가 Discussions 활성화를 거절했을 때만 쓴다.

파일이 정본이 아닌 이유 셋. 커밋이 필요하고, 작업 브랜치에 묶여 머지 전까지 안 보이고, 브랜치를 버리면 같이 사라진다.

**판정 순서**

1. `gh repo view --json nameWithOwner` — 실패하면 4번
2. `gh api repos/<OWNER>/<NAME> -q '.has_discussions'` — `true`면 Discussions에 기록
3. `false`면 켜자고 사용자에게 안내한다. 승인하면 `gh api -X PATCH repos/<OWNER>/<NAME> -F has_discussions=true`(admin 권한이 없어 실패하면 4번), 거절하면 4번
4. 파일 fallback — `docs/idea-notes.md`. 파일이 없으면 사용자 확인을 받고 신설한다(자동 생성 없음)

**꺼져 있다고 조용히 파일로 넘어가지 않는다.** 그러면 같은 저장소의 아이디어가 Discussions와 파일 두 곳에 나뉘어 쌓인다.

기록 위치는 저장소당 하나다. 플러그인이나 하위 영역마다 나누지 않는다.

## 무엇을 묻나

나중에 이 아이디어를 다시 볼 때 판정에 필요한 것이 셋이다.

| 필요한 것 | 없으면 |
|---|---|
| 왜 떠올랐나 (계기, 풀려는 문제) | 무슨 문제인지 몰라 판단이 안 됨 |
| 무엇을 하자는 것인가 | 제목만 남고 내용이 빔 |
| 언제 하면 되나 (착수 조건) | 볼 때마다 처음부터 다시 판단 |

**셋 중 사용자 문장에 없는 것만 묻는다. 최대 2개.** 이미 있으면 묻지 않고, "그냥 적어줘"라고 하면 하나도 묻지 않는다.

세 번째가 가장 자주 빠진다. 착수 조건이 없으면 우선순위 값이 있어도 판정이 안 되므로, 우선순위는 기록하지 않고 착수 조건을 받는다.

## 어떻게 쓰나

**제목** — 목록에서 제목만 읽고 무엇에 관한 것인지 알 수 있는 서술문. 이슈 제목과 달리 완료 판정이 필요 없다. 아이디어는 닫히지 않는다.

**본문** — 필드 라벨 없이 산문 2~4문단. 위 표의 셋이 들어갔는지 쓰고 나서 확인한다. 라벨을 붙이면 칸을 채우려고 추측 문장이 생긴다.

파일 fallback일 때만 마지막에 기록 날짜를 한 줄 남긴다. Discussions는 자동으로 기록한다.

## 명령

저장소 ID와 카테고리 ID를 먼저 조회한다. `Ideas`는 Discussions를 켜면 기본 생성되므로 만들지 않는다. 조회 결과에 slug `ideas`가 없으면(카테고리를 지웠거나 이름을 바꾼 저장소) 어느 카테고리에 쓸지 사용자에게 묻는다.

```bash
gh api graphql -f query='{repository(owner:"OWNER",name:"NAME"){id discussionCategories(first:20){nodes{slug id}}}}' \
  -q '.data.repository | .id, (.discussionCategories.nodes[] | "\(.slug)\t\(.id)")'
```

본문은 세션 스크래치패드에 임시 파일로 쓰고 `-F b=@<파일>`로 넘긴다. 스크래치패드는 세션 전용이라 따로 지우지 않는다. 인라인 heredoc은 인용 처리가 어긋나 명령이 실패하는 경우가 많고, `$(cat ...)`은 명령 치환이라 `Bash(gh api:*)` 허용 규칙으로 통과하지 않는다.

```bash
gh api graphql -f query='mutation($r:ID!,$c:ID!,$t:String!,$b:String!){createDiscussion(input:{repositoryId:$r,categoryId:$c,title:$t,body:$b}){discussion{number url}}}' \
  -f r=<repositoryId> -f c=<ideas categoryId> -f t='<제목>' -F b=@<본문파일> \
  -q '.data.createDiscussion.discussion | "#\(.number) \(.url)"'
```

생성된 URL을 사용자에게 보여준다.

## 이 도구가 하지 않는 것

| 동작 | Discussions | 파일 fallback |
|---|---|---|
| 추가 | 이 도구 | 이 도구 |
| 조회 | GitHub 검색 | `grep`, Read |
| 삭제 | GitHub UI | Edit |
| 이슈로 승격 | Discussion 페이지의 Create issue from discussion | 성립하지 않음 |

파일 fallback의 `이슈로 승격`이 비어 있는 것은 누락이 아니다. 변환할 Discussion이 없으므로 GitHub의 변환 기능이 성립하지 않는다. 착수할 것이 되면 `git-issue`로 이슈를 새로 만든다.

조회를 이 도구가 맡지 않는 이유도 같다. 검색 도구가 이미 있는데 명령을 하나 더 만들면 그 명령을 기억해야 한다.

## 쓰지 않을 때

- 기능이나 요구사항을 정의한다 → 스펙 문서
- 다음 세션에 넘길 착수 대상이다 → 이슈(`git-issue`)
- 이번 대화에서 끝낼 작업이다 → TaskCreate
- 되돌리기 비싼 선택의 근거다 → 결정 문서

## 톤

한국어 기본. 수집 단계라 판단보다 확장에 초점을 둔다. 거친 아이디어를 다듬으려 들지 않되 기록 형식은 일관되게 유지한다.

# squash 메시지 규격

**기준**: PR base 대비 head의 **net diff**만 보고 작성 — 중간 commit history 인용 X.

**차단 (session-context bleed)**:

- PR 내 자체 발견 버그와 그 수정 commit
- 되돌린 작업 (revert, restore)
- 중간 refactor, rename 후 재변경 흔적
- 개별 commit message 인용 (이슈 참조 줄은 예외, 아래 수집 규칙)
- 세션 발화, 블로커, 디버깅 과정, 키 디시전 번호(D-NN) 인용

**봇 의존성 PR은 body를 비운다 (net diff 기반 작성의 예외)**

**조건 둘을 모두 만족할 때만**:

1. PR `author.is_bot`이 `true`(dependabot, renovate 등 — `gh pr view --json author`가 `login` 외에 `is_bot` 불리언을 함께 반환하므로 `login` 문자열 패턴 매칭보다 이걸 우선한다)
2. net diff가 의존성 버전 선언 파일의 버전 문자열 변경뿐 (`pubspec.yaml`/`.lock`, `package.json`/lockfile, `.github/workflows/*.yml`의 `uses:` 핀, `build.gradle*`, `Gemfile`/`.lock`, `go.mod`/`go.sum`, `requirements*.txt`, `Cargo.toml`/`.lock`)

**근거**: 봇 PR 본문은 업스트림 릴리즈 노트 전문(`<details>` HTML 포함 수백 줄)이다. 그 내용은 PR에 영구 보존되고 커밋 제목의 `(#N)`이 이미 그 링크이므로, 커밋 body에 복사하면 중복인 채로 `git log`, `git show` 출력만 밀어낸다. 릴리즈 노트에 섞인 `BREAKING CHANGE` 문구가 release-please 등 커밋 body를 읽는 도구의 major bump 오탐을 내는 위험도 같이 제거된다.

**net diff에 소스 변경이 섞이면(조건 2 미충족) 일반 규칙으로 돌아간다.** 봇이 연 PR이라도 사람이 commit을 얹어 생성 코드 재생성, 호출부 수정, 마이그레이션이 섞였으면 그 변경은 PR 어디에도 설명이 없다 — 왜 그 수정이 함께 필요했는지를 body에 남긴다.

이 두 조건을 만족하면:

- **subject**: PR 제목 그대로. **body**: 빈 문자열 (Step 4에서 `--body ""`).
- **이슈 참조 수집을 통째로 건너뛴다.** 봇 PR 본문의 릴리즈 노트에는 업스트림 저장소의 `#N`과 `owner/repo#N`이 수십 개 들어 있다. 우리 저장소 이슈가 아니므로 참조 줄로 만들지 않고, "매칭 안 된 `#N`" 보고도 하지 않는다 (전량이 미매칭이라 보고가 노이즈가 된다).
- **`Signed-off-by: dependabot[bot]` 트레일러도 넣지 않는다.** squash 커밋의 author는 머지한 사람이다.

**형식**:

- subject: `type(scope): summary` — recent commits + CLAUDE.md 컨벤션 일치
- body: 5줄 이내 bullet — net 변경만, HEREDOC
- 이슈 참조 줄은 body 맨 끝에 별도 블록으로, bullet 5줄 제한에 포함하지 않는다

**이슈 참조 수집 — commit history 차단의 유일한 예외**

출처는 셋: PR body, PR 제목, 각 commit의 `messageHeadline`+`messageBody`(Step 1의 `commits`). `(close[sd]?|fix(es|ed)?|resolve[sd]?) #N`과 `Refs #N`을 **대소문자 무시**로 모두 걷는다.

- **이슈 번호마다 키워드를 반복해 한 줄씩.** `Closes #1, #2`는 GitHub가 #1만 닫는다. 타 저장소는 `Closes owner/repo#100`.
- **중복 제거**: 여러 출처가 같은 이슈를 언급하면(PR body와 commit 양쪽, 또는 commit 여럿) 한 줄로 합친다. 같은 이슈에 닫기 키워드와 `Refs`가 섞여 있으면 닫기 키워드만 남긴다.
- **키워드 승격 금지**: `Refs #N`만 있던 이슈를 `Closes`로 바꾸지 않는다. 닫을지는 그 이슈의 완료 조건이 정한다.
- **net diff에서 사라진 작업의 참조는 뺀다**: 중간 commit이 `Closes #7`을 달았어도 그 변경이 PR 안에서 되돌려졌으면 넣지 않는다. net diff 기준은 참조 줄에도 같이 적용된다.
- **매칭 안 된 `#N` 언급을 보고한다.** 세 출처에서 `#\d+`를 걷어, 참조 줄이 되지 못한 번호가 남으면 Step 3 출력에 한 줄 남긴다.
  - 출력 문구: `#N 언급이 <걸린 출처>에 있으나 닫기 키워드 없음 — 이슈면 말미 Closes #N 규격(commit 스킬) 위반, PR 번호 언급이면 무시`
  - `<걸린 출처>`는 그 번호가 실제로 나온 곳(PR 본문 / PR 제목 / commit message). PR 본문으로 고정해 적지 않는다.
  - 수집에서 빼는 둘: 코드블록, 인용 블록 안의 번호(과거 사례, 예시를 옮겨 적은 것), 바로 위 규칙으로 뺀 번호.
  - `--auto`에서도 출력 — 참조 줄이 통째로 빠진 것은 body만 봐서는 눈에 띄지 않는다.
  - 자동으로 `Closes`를 붙이지 않는다. 붙일지는 사용자가 정하고, 붙인다면 영문 `Closes #N`.

배치는 bullet과 빈 줄 하나로 띄운 마지막 블록.

```text
- <net 변경 bullet>

Closes #12
Closes #14
Refs #9
```

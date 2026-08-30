# 세션 사용량 계측 도구의 정본과 경계

## 결정

- **계측 규칙의 정본은 `plugins/claude-kit/tools/usage/tests/test_session.py`이고, 적재 규칙의 정본은 `tests/test_index.py`다** — 무엇을 어떻게 세는지와 무엇을 어느 열에 담는지는 이 테스트 파일들이 정한다. 같은 규칙을 소스 주석이나 `README.md`에 다시 적지 않는다. 새 지표가 필요하면 테스트를 먼저 쓰고 그 다음 도구에 넣는다.
- **모든 수치에 "세션 기록에 남은 것만"이라는 경계를 붙인다** — 이 도구는 `~/.claude/projects/<슬러그>/<세션ID>.jsonl`을 읽어 센다. 그 파일에 남지 않은 것은 세지 않는다. 경계를 붙이지 않은 수치를 인용하지 않는다.
- **도구가 만드는 산출물을 저장소 안에 두지 않는다** — 이 저장소는 공개돼 있고, 세션 기록에는 실제 파일 경로와 작업 내용과 경우에 따라 비밀이 들어간다. 세션 하나를 재는 결과는 stdout으로만 낸다. 코퍼스 인덱스는 `~/.claude/usage-index.db`에 만들고 `--db`로 바꾼다.
- **세션 파일은 읽기만 한다** — 옮기지도 고치지도 않는다. 그 파일은 Claude Code가 관리하고, 손대면 Claude 안에서 transcript를 다시 찾지 못하며 그 세션의 대화가 변질된다.
- **인덱스에 셸 명령 원문을 담지 않는다** — API 키, 내부 호스트명, 계정 정보가 그대로 들어간다. 파일을 지목한 호출의 경로만 담는다.
- **인덱스의 적재 단위는 요청 하나와 도구 호출 하나다** — 세션 집계만 담으면 지표를 새로 만들 때마다 코퍼스를 다시 전부 읽어야 한다.
- **다시 읽을 세션은 그 세션을 이루는 파일 전부의 크기 합과 가장 늦은 수정 시각으로 가르고, 다시 읽을 때는 그 세션의 행을 전부 지우고 파일을 처음부터 읽는다** — 뒤에 붙은 행만 이어 넣으면 압축 지점과 쉰 구간의 판정이 어긋난다. 끝난 세션이라는 상태를 두지 않는다. 세션은 몇 달 뒤에도 재개된다. 메인 파일 하나만 보면 서브에이전트와 teammate가 쓴 것이 늘어도 판정이 그대로여서 그 요청이 영영 빠진다. 읽지 못한 세션(`status='error'`)만 예외로 크기와 시각이 같아도 다시 읽는다 — 읽지 못한 원인이 도구 쪽일 수 있고, 건너뛰면 도구를 고친 뒤에도 그 세션이 영영 `error`로 남는다.
- **한 파일의 요청은 인덱스에 한 번만 담는다** — teammate 세션은 `subagents/` 아래가 아니라 top-level 세션 파일로 남아, 메인 세션의 agent 행으로 담긴 뒤 자기 세션으로 또 담기면 `requests` 전체를 합할 때 같은 요청이 두 번 세어진다. teammate 파일은 `status='teammate'`로 두고 요청과 도구 호출을 담지 않는다.
- **`usage session`의 기본 출력은 JSON이고 사람이 읽을 표는 `--table`이다** — 이 도구를 부르는 쪽은 대부분 스킬을 쓰는 에이전트다.
- **플러그인 버전과 이 도구의 버전은 따로 올린다** — `plugins/claude-kit/.claude-plugin/plugin.json`의 `version`은 저장소가 내놓는 릴리스 번호이고, `plugins/claude-kit/tools/usage/pyproject.toml`의 `version`은 `uv tool install`이 설치하는 패키지 자신의 번호다. 둘을 같은 값으로 묶으면 이 도구만 고쳐도 스킬 전체의 릴리스 번호가 오르고, 스킬만 고치면 패키지 번호가 뒤처진다.
- **도구 안의 파일은 저장소 문서를 링크하거나 경로로 가리키지 않는다** — 이 도구는 `uv tool install`로 저장소 밖에 설치돼 실행되므로, 설치된 사본에서 `docs/`와 `.claude/`의 경로가 존재하지 않는다.
- **`pytest`, `ruff check`, `ruff format --check`, `ty check` 넷 다 통과해야 한다** — `ty check`의 진단 0건도 통과 조건이다.
- **저장소마다 다른 판정은 도구에 넣지 않고 옵션 인자로 받는다** — `--marks`가 기본으로 내는 `Skill`과 `Agent`는 Claude Code가 정한 도구 이름이라 어느 저장소의 세션에서든 같은 뜻을 갖는다. 어느 셸 명령이 단계를 여는지는 저장소마다 다르므로 `--marks-bash`에 정규식을 받아 판정한다.
- **잔존 비용은 압축에서 끊는다** — 압축 경계에서 그때까지 살아 있던 항목을 전부 닫고, 그 자리에 크기 `context_tokens(경계)`인 `compaction` 항목 하나를 새로 연다. 압축 앞뒤를 하나의 구간으로 이으면 압축이 실제로 지운 컨텍스트의 잔존이 사라진다.
- **잔존 비용의 스코프는 `(session_id, agent_id)`로 서브에이전트마다 독립이다** — 서브에이전트가 쓴 것은 부모 스코프의 원장에 합산하지 않는다. 부모가 지불한 것은 `Agent` 도구 호출이 낸 보고서의 잔존뿐이다.
- **`base` 항목(요청 1의 컨텍스트)은 분해하지 않는다** — 시스템 프롬프트, 지침, 메모리가 뭉쳐 있고 세션 기록에 그 내부 구성이 안 남아 쪼갤 근거가 없다. 잔존 계산 규칙의 정본은 `tests/test_residual.py`다.

## 확인

```check
{"checks": [
  {"cmd": "[ \"$(grep -oE '^version *= *\\\"[^\\\"]+\\\"' plugins/claude-kit/tools/usage/pyproject.toml | grep -oE '[0-9][^\\\"]*')\" = \"$(grep -A1 'name = \\\"usage\\\"' plugins/claude-kit/tools/usage/uv.lock | grep -oE '\\\"[0-9][^\\\"]*\\\"' | tr -d '\\\"')\" ] && echo same || echo differ", "expect": "same"},
  {"cmd": "grep -rIniE 'oh-my-creator|minju|ojju|studios|PERSONA|naver-blog' --exclude-dir=__pycache__ plugins/claude-kit/tools/usage/README.md plugins/claude-kit/tools/usage/pyproject.toml plugins/claude-kit/tools/usage/src plugins/claude-kit/tools/usage/tests | wc -l | tr -d ' '", "expect": "0"},
  {"cmd": "grep -rInE 'docs/decisions|[.]claude/(rules|skills|agents)|claude-kit/docs' --exclude-dir=__pycache__ plugins/claude-kit/tools/usage/README.md plugins/claude-kit/tools/usage/pyproject.toml plugins/claude-kit/tools/usage/src plugins/claude-kit/tools/usage/tests | wc -l | tr -d ' '", "expect": "0"},
  {"cmd": "find plugins/claude-kit/tools/usage -type f -not -path '*/.*' -not -path '*__pycache__*' | wc -l | tr -d ' '", "expect": "14"},
  {"cmd": "uv run --directory plugins/claude-kit/tools/usage --no-sync pytest -q >/dev/null 2>&1 && echo pass || echo fail", "expect": "pass"},
  {"cmd": "uv run --directory plugins/claude-kit/tools/usage --no-sync ruff check . >/dev/null 2>&1 && uv run --directory plugins/claude-kit/tools/usage --no-sync ruff format --check . >/dev/null 2>&1 && echo pass || echo fail", "expect": "pass"},
  {"cmd": "uv run --directory plugins/claude-kit/tools/usage --no-sync ty check >/dev/null 2>&1 && echo pass || echo fail", "expect": "pass"}
]}
```

## 근거

**사실** — 계측 동작을 바꾸지 않는 변경은 같은 transcript 파일을 변경 전후의 도구에 넣고 `usage session` 출력을 대조해 검증할 수 있다.

**사실** — `usage`는 `uv tool install`로 설치돼 실행되므로 실행 경로에 `/tools/`가 들어가지 않는다. 실행 경로에서 도구 이름과 하위 명령을 읽어내는 판정은 이 저장소에서 한 건도 잡지 못한다.

**장점** — 산출물을 저장소에 두지 않으므로 공개 저장소에 실제 파일 경로와 작업 내용이 커밋될 경로가 없다.

**사실** — 세션 파일 2,061개를 적재하면 요청 147,700행, 도구 호출 158,323행, 데이터베이스 54MB가 나온다. 처음 적재가 35초, 변경된 세션만 다시 읽는 두 번째 실행이 2초다(2026-08-30 실측).

**장점** — 세는 규칙을 테스트 한 곳에만 적으므로, 규칙을 바꿀 때 갱신할 위치가 하나다. 요청과 도구 호출 단위로 담으므로 지표를 새로 만들 때 코퍼스를 다시 읽지 않는다.

**단점** — 세는 규칙을 알려면 테스트 파일을 읽어야 하고, `README.md`만 읽어서는 알 수 없다. `--marks-bash`는 쓰는 쪽이 정규식을 직접 써야 하므로, 저장소마다 그 정규식을 어딘가에 적어 둬야 한다.

## 기각

- **`usage <세션 ID>`를 그대로 두고 인덱싱만 옵션으로 붙인다** — 하는 일이 둘로 갈리는데 이름이 하나면 어느 것을 부르는지가 옵션에 숨는다. 하위 호환을 파기하고 `usage session`과 `usage index`로 나눴다.
- **인덱스에 셸 명령 원문을 담는다** — 어느 명령이 결과를 얼마나 실었는지 되짚을 수 있지만, 비밀이 그대로 들어간다. 도구 이름과 결과 크기만으로도 어느 종류의 호출이 컨텍스트를 키웠는지는 낼 수 있다.
- **변경된 세션의 뒤에 붙은 행만 이어 넣는다** — 압축 지점, 쉰 구간, 합쳐진 usage 판정이 전부 행 전체 순서에 의존해 어긋난다.
- **플러그인 설치 경로로 도구를 실행한다** — 마켓플레이스가 `source: directory`이면 `installLocation`이 원본 경로 그대로여서 `~/.claude/plugins/marketplaces/claude-kit`이 존재하지 않는다. 플러그인 캐시 경로는 버전마다 달라져 명령이 깨진다. `uv tool install`로 설치해 `usage`를 직접 호출한다.

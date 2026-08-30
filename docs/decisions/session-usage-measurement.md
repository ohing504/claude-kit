# 세션 사용량 계측 도구의 정본과 경계

## 결정

- **계측 규칙의 정본은 `plugins/claude-kit/tools/usage/tests/test_session.py`다** — 무엇을 어떻게 세는지는 이 테스트 파일이 정한다. 같은 규칙을 소스 주석이나 `README.md`에 다시 적지 않는다. 새 지표가 필요하면 테스트를 먼저 쓰고 그 다음 도구에 넣는다.
- **모든 수치에 "세션 기록에 남은 것만"이라는 경계를 붙인다** — 이 도구는 `~/.claude/projects/<슬러그>/<세션ID>.jsonl`을 읽어 센다. 그 파일에 남지 않은 것은 세지 않는다. 경계를 붙이지 않은 수치를 인용하지 않는다.
- **도구가 만드는 산출물을 저장소 안에 두지 않는다** — 이 저장소는 공개돼 있고, 세션 기록에는 실제 파일 경로와 작업 내용과 경우에 따라 비밀이 들어간다. 도구는 stdout으로만 출력한다.
- **플러그인 버전과 패키지 버전을 같이 올린다** — `plugins/claude-kit/.claude-plugin/plugin.json`의 `version`과 `plugins/claude-kit/tools/usage/pyproject.toml`의 `version`은 항상 같은 값이다.
- **도구 안의 파일은 저장소 문서를 링크하거나 경로로 가리키지 않는다** — 이 도구는 `uv tool install`로 저장소 밖에 설치돼 실행되므로, 설치된 사본에서 `docs/`와 `.claude/`의 경로가 존재하지 않는다.
- **`pytest`, `ruff check`, `ruff format --check`, `ty check` 넷 다 통과해야 한다** — `ty check`의 진단 0건도 통과 조건이다.
- **저장소마다 다른 판정은 도구에 넣지 않고 옵션 인자로 받는다** — `--marks`가 기본으로 내는 `Skill`과 `Agent`는 Claude Code가 정한 도구 이름이라 어느 저장소의 세션에서든 같은 뜻을 갖는다. 어느 셸 명령이 단계를 여는지는 저장소마다 다르므로 `--marks-bash`에 정규식을 받아 판정한다.

## 확인

```check
{"checks": [
  {"cmd": "[ \"$(grep -oE '\"version\": *\"[^\"]+\"' plugins/claude-kit/.claude-plugin/plugin.json | grep -oE '[0-9][^\"]*')\" = \"$(grep -oE '^version *= *\"[^\"]+\"' plugins/claude-kit/tools/usage/pyproject.toml | grep -oE '[0-9][^\"]*')\" ] && echo same || echo differ", "expect": "same"},
  {"cmd": "grep -rIniE 'oh-my-creator|minju|ojju|studios|PERSONA|naver-blog' --exclude-dir=__pycache__ plugins/claude-kit/tools/usage/README.md plugins/claude-kit/tools/usage/pyproject.toml plugins/claude-kit/tools/usage/src plugins/claude-kit/tools/usage/tests | wc -l | tr -d ' '", "expect": "0"},
  {"cmd": "grep -rInE 'docs/decisions|[.]claude/(rules|skills|agents)|claude-kit/docs' --exclude-dir=__pycache__ plugins/claude-kit/tools/usage/README.md plugins/claude-kit/tools/usage/pyproject.toml plugins/claude-kit/tools/usage/src plugins/claude-kit/tools/usage/tests | wc -l | tr -d ' '", "expect": "0"},
  {"cmd": "find plugins/claude-kit/tools/usage -type f -not -path '*/.*' -not -path '*__pycache__*' | wc -l | tr -d ' '", "expect": "8"},
  {"cmd": "uv run --directory plugins/claude-kit/tools/usage --no-sync pytest -q >/dev/null 2>&1 && echo pass || echo fail", "expect": "pass"},
  {"cmd": "uv run --directory plugins/claude-kit/tools/usage --no-sync ruff check . >/dev/null 2>&1 && uv run --directory plugins/claude-kit/tools/usage --no-sync ruff format --check . >/dev/null 2>&1 && echo pass || echo fail", "expect": "pass"},
  {"cmd": "uv run --directory plugins/claude-kit/tools/usage --no-sync ty check >/dev/null 2>&1 && echo pass || echo fail", "expect": "pass"}
]}
```

## 근거

**사실** — 계측 동작을 바꾸지 않는 변경은 같은 transcript 파일을 변경 전후의 도구에 넣고 `--json` 출력을 대조해 검증할 수 있다.

**사실** — `usage`는 `uv tool install`로 설치돼 실행되므로 실행 경로에 `/tools/`가 들어가지 않는다. 실행 경로에서 도구 이름과 하위 명령을 읽어내는 판정은 이 저장소에서 한 건도 잡지 못한다.

**장점** — 세는 규칙을 테스트 한 곳에만 적으므로, 규칙을 바꿀 때 갱신할 위치가 하나다. 산출물을 저장소에 두지 않으므로 공개 저장소에 실제 파일 경로와 작업 내용이 커밋될 경로가 없다.

**단점** — 세는 규칙을 알려면 테스트 파일을 읽어야 하고, `README.md`만 읽어서는 알 수 없다. `--marks-bash`는 쓰는 쪽이 정규식을 직접 써야 하므로, 저장소마다 그 정규식을 어딘가에 적어 둬야 한다.

## 기각

- **플러그인 설치 경로로 도구를 실행한다** — 마켓플레이스가 `source: directory`이면 `installLocation`이 원본 경로 그대로여서 `~/.claude/plugins/marketplaces/claude-kit`이 존재하지 않는다. 플러그인 캐시 경로는 버전마다 달라져 명령이 깨진다. `uv tool install`로 설치해 `usage`를 직접 호출한다.

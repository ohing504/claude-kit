# 세션 사용량 계측 도구의 정본과 경계

## 결정

- **계측 규칙의 정본은 `plugins/claude-kit/tools/usage/tests/test_session.py`다** — 무엇을 어떻게 세는지는 이 테스트 파일이 정한다. 같은 규칙을 소스 주석이나 `README.md`에 다시 적지 않는다. 새 지표가 필요하면 테스트를 먼저 쓰고 그 다음 도구에 넣는다.
- **모든 수치에 "세션 기록에 남은 것만"이라는 경계를 붙인다** — 이 도구는 `~/.claude/projects/<슬러그>/<세션ID>.jsonl`을 읽어 센다. 그 파일에 남지 않은 것은 세지 않는다. 경계를 붙이지 않은 수치를 인용하지 않는다.
- **도구가 만드는 산출물을 저장소 안에 두지 않는다** — 이 저장소는 공개돼 있고, 세션 기록에는 실제 파일 경로와 작업 내용과 경우에 따라 비밀이 들어간다. 도구는 stdout으로만 출력한다.
- **플러그인 버전과 패키지 버전을 같이 올린다** — `plugins/claude-kit/.claude-plugin/plugin.json`의 `version`과 `plugins/claude-kit/tools/usage/pyproject.toml`의 `version`은 항상 같은 값이다. 현재 둘 다 `0.7.0`.
- **도구 안의 파일은 저장소 문서를 링크하거나 경로로 가리키지 않는다** — 이 도구는 `uv tool install`로 저장소 밖에 설치돼 실행되므로, 설치된 사본에서 `docs/`와 `.claude/`의 경로가 존재하지 않는다.
- **`ty check`는 통과 조건이 아니라 개수 고정 검사다** — 진단 3건이 남아 있다(`unsupported-operator` 2건, `unsound-return-statement` 1건). 개수가 늘어도 줄어도 이 문서를 갱신한다.

## 확인

```check
{"checks": [
  {"cmd": "[ \"$(grep -oE '\"version\": *\"[^\"]+\"' plugins/claude-kit/.claude-plugin/plugin.json | grep -oE '[0-9][^\"]*')\" = \"$(grep -oE '^version *= *\"[^\"]+\"' plugins/claude-kit/tools/usage/pyproject.toml | grep -oE '[0-9][^\"]*')\" ] && echo same || echo differ", "expect": "same"},
  {"cmd": "grep -rIniE 'oh-my-creator|minju|ojju|studios|PERSONA|naver-blog' --exclude-dir=__pycache__ plugins/claude-kit/tools/usage/README.md plugins/claude-kit/tools/usage/pyproject.toml plugins/claude-kit/tools/usage/src plugins/claude-kit/tools/usage/tests | wc -l | tr -d ' '", "expect": "0"},
  {"cmd": "grep -rInE 'docs/decisions|[.]claude/(rules|skills|agents)|claude-kit/docs' --exclude-dir=__pycache__ plugins/claude-kit/tools/usage/README.md plugins/claude-kit/tools/usage/pyproject.toml plugins/claude-kit/tools/usage/src plugins/claude-kit/tools/usage/tests | wc -l | tr -d ' '", "expect": "0"},
  {"cmd": "find plugins/claude-kit/tools/usage -type f -not -path '*/.*' -not -path '*__pycache__*' | wc -l | tr -d ' '", "expect": "8"},
  {"cmd": "uv run --directory plugins/claude-kit/tools/usage --no-sync pytest -q 2>&1 | grep -cE '^98 passed'", "expect": "1"},
  {"cmd": "uv run --directory plugins/claude-kit/tools/usage --no-sync ty check 2>&1 | grep -E '^Found '", "expect": "Found 3 diagnostics"}
]}
```

## 근거

**사실** — 원본은 사적 저장소 `ojju-studio`의 `plugins/oh-my-creator/tools/usage`이고, 이관 원본 커밋은 `d78fcdb1`이다.

**사실** — 이관본을 검증한 방법은 같은 transcript 파일을 원본 도구와 이관본에 각각 넣고 `--json` 출력을 대조한 것이다. 두 출력은 완전히 같았고 크기는 56304 bytes였다. 테스트는 98개 전부 통과했다.

**사실** — 테스트 픽스처에 있던 사적 저장소 고유 문자열은 익명 문자열로 치환했다. 치환한 값은 `demo:writer`, `demo:reader-a`, `demo:reader-b`, `demo:stage`를 포함한다.

**사실** — `ty` 진단은 원본이 4건이고 이관본이 3건이다. 두 소스는 주석 교체 외에 같고, `[tool.ty.environment]`와 `[tool.ty.rules]` 설정도 같고, `ty` 버전도 `0.0.66`으로 같다. 개수가 달라진 원인은 `ty`가 프로젝트 루트를 잡는 방식 차이로 보인다. 계측 동작에는 영향이 없다 — 같은 transcript 파일로 두 도구의 `--json` 출력을 대조해 완전히 같았고 테스트 98개가 모두 통과한다.

**사실** — `ty` 진단을 이관 커밋에서 고치지 않았다. 고치면 이관 커밋의 diff가 파일을 옮긴 것이 아니게 되고, 원본과 출력을 대조하는 검증이 "소스를 고치지 않았으므로 출력이 같다"를 보이지 못한다.

**사실** — 이관 후 `ruff format`이 `tests/test_session.py` 하나를 재포맷했다. 익명화로 문자열이 짧아져 원본의 줄바꿈이 불필요해졌기 때문이다. 재포맷을 적용한 뒤에도 `ruff check`는 `All checks passed!`이고 테스트는 98개가 통과한다.

**장점** — 세는 규칙을 테스트 한 곳에만 적으므로, 규칙을 바꿀 때 갱신할 위치가 하나다. 산출물을 저장소에 두지 않으므로 공개 저장소에 실제 파일 경로와 작업 내용이 커밋될 경로가 없다.

**단점** — 세는 규칙을 알려면 테스트 파일을 읽어야 하고, `README.md`만 읽어서는 알 수 없다. `ty` 진단 개수가 검사에 들어 있어 진단을 고칠 때마다 이 문서를 함께 고쳐야 한다.

## 기각

- **`ojju-studio`의 원본을 이 이관과 함께 삭제한다** — 그 저장소의 변경은 그 저장소 세션에서 한다. 여기서 같이 고치면 두 세션이 같은 파일을 바꿔 충돌한다. 원본 삭제와 참조 전환은 그 세션에 남긴 작업이다.
- **플러그인 설치 경로로 도구를 실행한다** — 마켓플레이스가 `source: directory`이면 `installLocation`이 원본 경로 그대로여서 `~/.claude/plugins/marketplaces/claude-kit`이 존재하지 않는다. 플러그인 캐시 경로는 버전마다 달라져 명령이 깨진다. `uv tool install`로 설치해 `usage`를 직접 호출한다.

---
paths:
  - "plugins/claude-kit/tools/usage/**"
---

# 세션 사용량 계측 도구

- 세는 규칙을 바꾸려면 `tests/test_session.py`를 먼저 고친다. 소스만 고치지 않는다.
- 이 디렉터리 안의 파일에서 저장소 문서(`docs/`, `.claude/`)를 링크하거나 경로로 가리키지 않는다. 이 도구는 `uv tool install`로 저장소 밖에 설치돼 실행된다.
- `pyproject.toml`의 `version`은 이 도구만의 버전이다. 플러그인 버전(`plugins/claude-kit/.claude-plugin/plugin.json`)과 같을 필요가 없다. 올릴 때 `uv lock`을 같이 돌려 `uv.lock`의 사본을 맞춘다.
- 테스트 픽스처에 실제 파일 경로, 실제 세션 ID, 제품명, 사람 이름을 넣지 않는다.

상세는 `docs/decisions/session-usage-measurement.md`.

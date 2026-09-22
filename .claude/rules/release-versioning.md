# 플러그인 버전과 릴리즈

`plugins/claude-kit/.claude-plugin/plugin.json`의 `version`을 손으로 고치지 않는다. `main`에 push되면 release-please가 릴리즈 PR을 열어 그 필드와 `CHANGELOG.md`를 함께 갱신하고, 그 PR을 머지하면 `claude-kit--v<version>` 태그와 GitHub Release를 만든다.

- **릴리즈 PR은 내용을 고치지 않고 그대로 머지한다.** 제목과 본문을 다시 쓰면 release-please가 자기 PR로 인식하지 못한다.
- **버전을 정하는 것은 squash subject 하나다.** squash merge라 개별 커밋은 `main`에 남지 않는다. PR 안에 `feat` 커밋이 있어도 subject가 `fix(...)`면 patch만 올라간다 — subject는 net diff에서 가장 큰 변경을 반영해 쓴다.
- **type과 bump**: `feat` → minor. `fix`와 나머지 → patch. `feat!:` 또는 본문 `BREAKING CHANGE:` → 1.0.0 전까지는 minor(`bump-minor-pre-major`).
- **`plugins/` 아래는 배포물이다.** `SKILL.md`는 스킬의 실행 지침이라 바꾸면 동작이 바뀐다. 규격을 더하거나 바꾸면 `feat`, 결함을 고치면 `fix`로 쓴다. `docs`는 `README.md`, `docs/`, `.claude/` 처럼 배포되지 않는 문서에만 쓴다.
- 특정 버전으로 강제할 때만 빈 커밋 본문에 `Release-As: 1.0.0`을 넣는다.

설정은 `release-please-config.json`, 현재 버전 상태는 `.release-please-manifest.json`.

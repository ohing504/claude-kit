# memory-routing

메모리 작동 모델·저장 형식 참조 문서. 판정 규칙·점검 항목·revise 절차는 skill.md 인라인.

## 1. 메모리 작동 모델 (전제)

- 메모리 경로: `~/.claude/projects/<cwd-encoded>/memory/` — 프로젝트(cwd)별 격리.
- 매 세션 자동 로드: 그 프로젝트의 `MEMORY.md` 인덱스 *한 개만*. 개별 메모리 파일은 자동 로드 아님 — 관련 시 recall로 `<system-reminder>`에 surface.
- 전역 항상-로드 레이어: `~/.claude/CLAUDE.md` (모든 프로젝트 모든 세션 로드, 수기 관리).
- 저장 주체: 메모리는 Claude가 세션 중 *자율적으로* 저장한다(사용자 동의·지시 없이). 저장 시점에 보편/고유를 가르는 장치는 없다.
- 함의: 비용은 *프로젝트당 인덱스 길이*가 좌우(누적 폭발 아님). 낭비의 핵심은 *보편 규칙의 cross-silo 중복*이며, 자율 저장 탓에 이 중복은 구조적으로 쌓인다 — 그래서 본 시스템은 사후 정리(audit/revise) 도구다.

## 2. 저장 형식 (tier 2 프로젝트 메모리)

revise가 재배치·통합 시 네이티브 메모리 형식을 보존하기 위한 참조.

- 메모리 파일: frontmatter(`name`/`description`/`metadata.type`) + 본문 1개 사실. feedback/project는 본문에 `**Why:**`·`**How to apply:**` 동반.
- `MEMORY.md` 인덱스: 한 줄/항목(`- [제목](file.md) — 훅`). 콘텐츠 본문 금지. lean 유지.
- 관련 메모리는 본문에서 `[[name]]`로 링크.

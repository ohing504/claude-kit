# claude-kit

일상에서 재사용하는 Claude Code 스킬 모음.

## 설치

```bash
claude plugin marketplace add ohing504/claude-kit
claude plugin install claude-kit@claude-kit
```

프로젝트별 활성화는 `.claude/settings.json`:

```json
{
  "enabledPlugins": {
    "claude-kit@claude-kit": true
  }
}
```

## 스킬

세 스킬 모두 Claude Code 세션에서 자연어로 호출한다.

### iphone-notes-digest (macOS 전용)

Apple Notes 메모를 추출하고, 안의 링크·영상(인스타 릴스 캡션, 음성으로만 설명하는 영상은 STT까지)을 해석해 메모별 다이제스트(사실) 문서로 정리한다. 살릴지/버릴지 판단(흡수·삭제)은 그 문서를 보는 사용자(또는 사용자의 노트 시스템) 몫 — 스킬은 사실만 기록한다.

### whiteboard

디버깅·설계·선택지 비교처럼 글로는 따라가기 힘든 논의를, 바로 그리지 않고 "지금 무엇이 막혔는지"를 대화에서 먼저 읽어 *무엇을 어느 수준으로* 그릴지 합의한 뒤, 차트·다이어그램·비교 매트릭스를 담은 자기완결 HTML 한 장으로 시각화한다. 핵심은 예쁜 렌더가 아니라 *무엇을 그릴지*를 정확히 집어내는 것. 생성한 HTML은 headless 렌더 검증으로 다이어그램이 실제로 그려졌는지 확인한다.

### ai-doc-improver

AI agent가 읽는 문서(CLAUDE.md·SKILL.md·에이전트 정의·README·spec·코드 주석)를 토큰 밀도·가독성 기준으로 점검해, 삭제·외부화·계층 분해 후보를 항목별로 제시하고 확인을 받은 뒤 리라이트한다. 핵심은 줄 수를 줄이는 게 아니라 토큰 밀도를 높이는 것 — 한 줄로 이어붙이는 압축은 안티패턴이고, 통짜 문장을 표제+sub-bullet 계층으로 분해하고 군더더기를 삭제·외부화하는 게 본질이다. 내용 손실 없이 형식만 손대며, 무엇을 지울지는 사용자가 확인한 것만 반영한다.

## 필수 환경

`iphone-notes-digest`만 **macOS 전용**이다 (Apple Notes 자동화에 의존). 나머지 두 스킬은 OS 독립적이다.

- **macOS** — Apple Notes(메모) 앱과 AppleScript 자동화. Apple Silicon이면 영상 STT가 Metal 가속(mlx-whisper)으로 더 빠르다.
- **[uv](https://docs.astral.sh/uv/)** — Python 도구를 격리 venv로 부트스트랩한다. `brew install uv`
- **ffmpeg** — 영상/오디오 처리. `brew install ffmpeg`
- **Apple Notes 접근 권한** — 첫 실행 시 macOS가 "터미널이 메모를 제어하려 합니다" 자동화 권한을 묻는다. 허용해야 메모를 추출할 수 있다.

> yt-dlp·whisper 등 나머지 Python 의존성은 첫 실행 때 `~/.cache/capture-kit` 격리 venv에 자동 설치된다 — 전역 환경을 건드리지 않는다.

`whiteboard`는 생성한 HTML의 **렌더 검증**(`verify_render.sh`)에만 **Chrome/Chromium**을 쓴다 — 없으면 검증을 건너뛰고 브라우저로 직접 확인하라고 안내한다. `ai-doc-improver`는 별도 의존성이 없다.

## 사용 예시

```
메모앱에 쌓인 메모 정리해줘
  → 폴더 선택 → 수집 → 링크·영상 해석 → 메모별 다이제스트 문서 생성

이 선택지들 한눈에 비교하게 그려줘
  → 무엇을 그릴지 합의 → 비교 매트릭스 HTML 한 장 생성

이 CLAUDE.md AI가 읽기 좋게 다이어트해줘
  → 토큰밀도·가독성 audit → 항목별 개선안 제시 → 확인 → 리라이트
```

## 트러블슈팅

- **메모가 안 추출됨 / 권한 오류** — 시스템 설정 → 개인정보 보호 및 보안 → 자동화에서 터미널(또는 Claude Code 실행 앱)의 "메모" 제어를 허용했는지 확인한다.
- **잠긴 메모 / 이메일 계정 메모가 빠짐** — 의도된 동작이다. 추출 못 한 메모 개수를 다이제스트에 정직하게 적는다("전부 봤다"는 착시 방지).
- **`uv: command not found`** — `brew install uv` 후 새 셸에서 재시도.
- **영상 STT가 느림 / 실패** — `ffmpeg`가 설치돼 있는지 확인(`ffmpeg -version`). Intel Mac은 mlx 가속 대신 faster-whisper로 동작해 더 느릴 수 있다.

## 라이선스

MIT

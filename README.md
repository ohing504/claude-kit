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

모든 스킬은 Claude Code 세션에서 자연어로 호출한다.

### whiteboard

복잡한 설명·설계·선택지 비교처럼 글로는 따라가기 힘든 논의를, 바로 그리지 않고 "무엇을 어느 수준으로" 그릴지 대화에서 합의한 뒤 차트·다이어그램·비교 매트릭스를 담은 자기완결 HTML 한 장으로 시각화한다. 생성한 HTML은 headless 렌더 검증으로 실제로 그려졌는지 확인한다.

### html-to-image

완성된 HTML(파일·URL·문자열)을 카드뉴스·앱스토어·OG처럼 비율이 고정된 이미지(PNG/JPEG)로 캡처한다. 폰트·이미지 렌더 완료를 기다려 깨짐을 막고, 여러 장 batch를 지원한다.

### ai-doc-improver

AI agent가 읽는 문서(CLAUDE.md·SKILL.md·에이전트 정의·README·주석)를 토큰 밀도·가독성 기준으로 점검해, 삭제·외부화·계층 분해 후보를 항목별로 제시하고 확인을 받은 뒤 리라이트한다. 줄 수를 줄이는 게 아니라 토큰 밀도를 높이는 게 핵심.

### memory-manager

`~/.claude` 파일 기반 메모리의 cross-silo 중복·오배치·인덱스 bloat를 audit하고, 사용자 확인을 받은 뒤 정리(revise)한다.

### iphone-notes-digest (macOS 전용)

Apple Notes 메모를 추출하고, 안의 링크·영상(인스타 릴스 캡션, 음성으로만 설명하는 영상은 STT까지)을 해석해 메모별 다이제스트(사실) 문서로 정리한다. 살릴지/버릴지 판단은 그 문서를 보는 사용자(또는 노트 시스템) 몫 — 스킬은 사실만 기록한다.

### browser-session

patchright/playwright의 persistent context로 로그인 세션을 프로파일에 저장·재사용하고, 세션 유효성 체크·로그인 대기·실행 중 만료 감지·재인증까지 다룬다. 로그인이 필요한 사이트 크롤링·브라우저 자동화를 구현할 때 참조하는 가이드(Python/JS 양쪽 템플릿).

### commit

변경을 commit하고, 발화 범위에 따라 push·PR 생성까지 확장한다. commit message·PR 본문은 git diff·log 사실만 반영하고 세션 대화·디버깅 과정은 차단한다(session-context bleed guard). "커밋해줘"는 commit만, "PR 올려줘"는 push+PR — outward 액션 전 확인. staging 범위는 프로젝트 CLAUDE.md 규약(동시 작업·폴더째 add 금지 등)을 우선 따른다.

### squash-merge

PR을 squash merge하고, squash 메시지를 net diff 사실만으로 정리(PR 내부 중간 commit·되돌린 작업 차단)한 뒤 로컬 [gone] 브랜치·worktree 정리와 main 동기화까지 한 흐름으로 처리한다. merge 실행 전 확인한다.

## 필수 환경

`iphone-notes-digest`만 **macOS 전용**이다 (Apple Notes 자동화에 의존). 나머지는 OS 독립적이다.

- **macOS** — Apple Notes 앱과 AppleScript 자동화. Apple Silicon이면 영상 STT가 Metal 가속(mlx-whisper)으로 더 빠르다.
- **[uv](https://docs.astral.sh/uv/)** — Python 도구를 격리 venv로 부트스트랩한다. `brew install uv`
- **ffmpeg** — 영상/오디오 처리. `brew install ffmpeg`
- **Apple Notes 접근 권한** — 첫 실행 시 macOS가 "터미널이 메모를 제어하려 합니다" 자동화 권한을 묻는다. 허용해야 메모를 추출할 수 있다.

> yt-dlp·whisper 등 나머지 Python 의존성은 첫 실행 때 `~/.cache/capture-kit` 격리 venv에 자동 설치된다 — 전역 환경을 건드리지 않는다.

브라우저를 쓰는 스킬: `whiteboard`는 렌더 검증(`verify_render.sh`)에 **Chrome/Chromium**, `html-to-image`는 **playwright + chromium**, `browser-session`은 **patchright(또는 playwright) + Chrome**을 쓴다. `ai-doc-improver`·`memory-manager`는 별도 의존성이 없다.

## 사용 예시

```
메모앱에 쌓인 메모 정리해줘
  → 폴더 선택 → 수집 → 링크·영상 해석 → 메모별 다이제스트 문서 생성

이 선택지들 한눈에 비교하게 그려줘
  → 무엇을 그릴지 합의 → 비교 매트릭스 HTML 한 장 생성

이 CLAUDE.md AI가 읽기 좋게 다이어트해줘
  → 토큰밀도·가독성 audit → 항목별 개선안 제시 → 확인 → 리라이트

로그인 세션 유지하면서 이 사이트 크롤링해줘
  → 프로파일에 세션 저장·재사용 → 만료 시 재인증 → 수집
```

## 트러블슈팅

- **메모가 안 추출됨 / 권한 오류** — 시스템 설정 → 개인정보 보호 및 보안 → 자동화에서 터미널(또는 Claude Code 실행 앱)의 "메모" 제어를 허용했는지 확인한다.
- **잠긴 메모 / 이메일 계정 메모가 빠짐** — 의도된 동작이다. 추출 못 한 메모 개수를 다이제스트에 정직하게 적는다("전부 봤다"는 착시 방지).
- **`uv: command not found`** — `brew install uv` 후 새 셸에서 재시도.
- **영상 STT가 느림 / 실패** — `ffmpeg`가 설치돼 있는지 확인(`ffmpeg -version`). Intel Mac은 mlx 가속 대신 faster-whisper로 동작해 더 느릴 수 있다.

## 라이선스

MIT

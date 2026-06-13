# claude-kit

일상에서 재사용하는 Claude Code 스킬·워크플로우 모음.

## 설치

```bash
claude plugin marketplace add ohing504/claude-kit
claude plugin install capture-kit@claude-kit
```

프로젝트별 활성화는 `.claude/settings.json`:

```json
{
  "enabledPlugins": {
    "capture-kit@claude-kit": true
  }
}
```

## 플러그인

### capture-kit

흩어진 캡처(아이폰 메모 등)를 추출 → 해석 → 보고로 정리.

- **iphone-notes-digest** — Apple Notes 메모를 추출하고, 안의 링크·영상(인스타 릴스 캡션, 음성으로만 설명하는 영상은 STT까지)을 해석해 메모별 다이제스트(사실) 문서로 정리한다. 살릴지/버릴지 판단(흡수·삭제)은 그 문서를 보는 사용자(또는 사용자의 노트 시스템) 몫 — 스킬은 사실만 기록한다.

## 필수 환경

`iphone-notes-digest`는 **macOS 전용**이다 (Apple Notes 자동화에 의존). 처음 실행할 때 아래가 필요하다.

- **macOS** — Apple Notes(메모) 앱과 AppleScript 자동화. Apple Silicon이면 영상 STT가 Metal 가속(mlx-whisper)으로 더 빠르다.
- **[uv](https://docs.astral.sh/uv/)** — Python 도구를 격리 venv로 부트스트랩한다. `brew install uv`
- **ffmpeg** — 영상/오디오 처리. `brew install ffmpeg`
- **Apple Notes 접근 권한** — 첫 실행 시 macOS가 "터미널이 메모를 제어하려 합니다" 자동화 권한을 묻는다. 허용해야 메모를 추출할 수 있다.

> yt-dlp·whisper 등 나머지 Python 의존성은 첫 실행 때 `~/.cache/capture-kit` 격리 venv에 자동 설치된다 — 전역 환경을 건드리지 않는다.

## 사용 예시

Claude Code 세션에서 자연어로 호출한다.

```
메모앱에 쌓인 메모 정리해줘
  → 폴더 선택 → 수집 → 링크·영상 해석 → 메모별 다이제스트 문서 생성

아이폰 메모에 인스타 릴스/링크 잔뜩 있는데 뭐였는지 모르겠어
  → 각 콘텐츠의 캡션·STT를 해석해 "이게 뭐였는지"를 사실로 정리

(다이제스트 확인 후) 처리한 메모 지워줘
  → 넘긴 메모만 dispose_notes.sh로 삭제(가드 + DRY RUN 내장)
```

결과물은 메모별 섹션으로 정리된 다이제스트(사실) 문서 한 장이다. **무엇을 살리고 버릴지는 이 문서를 본 사용자(또는 사용자의 PKM)가 정한다** — 스킬은 판단하지 않는다.

## 트러블슈팅

- **메모가 안 추출됨 / 권한 오류** — 시스템 설정 → 개인정보 보호 및 보안 → 자동화에서 터미널(또는 Claude Code 실행 앱)의 "메모" 제어를 허용했는지 확인한다.
- **잠긴 메모 / 이메일 계정 메모가 빠짐** — 의도된 동작이다. 추출 못 한 메모 개수를 다이제스트에 정직하게 적는다("전부 봤다"는 착시 방지).
- **`uv: command not found`** — `brew install uv` 후 새 셸에서 재시도.
- **영상 STT가 느림 / 실패** — `ffmpeg`가 설치돼 있는지 확인(`ffmpeg -version`). Intel Mac은 mlx 가속 대신 faster-whisper로 동작해 더 느릴 수 있다.

## 라이선스

MIT

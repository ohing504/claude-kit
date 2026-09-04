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

세션에서 자연어로 호출한다. 상세는 각 스킬의 `SKILL.md`에 있다.

### 📊 시각화

| 스킬 | 하는 일 |
|---|---|
| **whiteboard** | 복잡한 논의·선택지 비교를, 무엇을 그릴지 합의한 뒤 자기완결 HTML 한 장으로 시각화(렌더 검증까지) |
| **html-to-image** | 완성 HTML을 카드뉴스·OG처럼 비율 고정 이미지(PNG/JPEG)로 캡처 |

### 📝 AI 문서·프롬프트

| 스킬 | 하는 일 |
|---|---|
| **ai-doc-improver** | AI가 읽는 문서(CLAUDE.md, SKILL.md 등)를 토큰 밀도, instruction 준수율, 서술 정확도로 점검해 정리 |
| **prompt-forge** | 대충 던진 요청을 인터뷰로 파고들어 의도 명세(intent spec)로 — 문구가 아니라 의도를 벼린다 · [소개](https://htmlpreview.github.io/?https://github.com/ohing504/claude-kit/blob/main/plugins/claude-kit/skills/prompt-forge/prompt-forge-guide.html) |
| **memory-manager** | `~/.claude` 파일 메모리의 중복·오배치·인덱스 bloat 정리 |

### ✅ 품질 게이트

| 스킬 | 하는 일 |
|---|---|
| **deep-verify** | 완료 보고 전 스펙 재대조·자기 반박·증거 수집을 강제("될 것 같다" 차단) |
| **reflect** | **AI가 쓰는 반성문** — 지침을 어겼을 때 변명 없이 증거로 진단하고 개선안을 목적지로 라우팅(로그로 재발 추적) · [소개](https://htmlpreview.github.io/?https://github.com/ohing504/claude-kit/blob/main/plugins/claude-kit/skills/reflect/reflect-guide.html) |

### 📥 캡처

| 스킬 | 하는 일 |
|---|---|
| **iphone-notes-digest** _(macOS)_ | Apple Notes 메모·링크·영상(음성만 있는 건 STT까지)을 메모별 다이제스트로 정리 |
| **idea-note** | 거친 아이디어를 짧은 인터뷰로 구체화해 저장소 GitHub Discussions에 기록(파일은 Discussions를 못 쓸 때만) |

### 🔧 Git·브라우저

| 스킬 | 하는 일 |
|---|---|
| **browser-session** | 로그인 세션을 프로파일에 저장·재사용하는 크롤링·자동화 가이드(Python/JS) |
| **commit** | 변경을 커밋(발화 범위 따라 push·PR), 세션 대화 맥락 차단 |
| **git-issue** | 이슈 제목, 본문, 라벨 규격(제목은 증상 서술문, 본문 4블록) + 생성 시점 가드 hook |
| **squash-merge** | PR squash merge + 메시지 정리 + 로컬 정리·main 동기화 |

## 도구

스킬과 별개로, 명령줄에서 직접 실행하는 도구다.

| 도구 | 하는 일 |
|---|---|
| **usage** | 세션 하나가 쓴 API 호출 수, 토큰, 소요를 메인과 서브에이전트로 나눠 낸다. 캐시 쓰기는 5분과 1시간 TTL로 가른다. `usage index`는 세션 기록 전체를 SQLite 한 파일에 적재한다 |

```bash
uv tool install "git+https://github.com/ohing504/claude-kit#subdirectory=plugins/claude-kit/tools/usage"
usage session <세션ID>
```

이 도구가 내는 모든 수치에는 "세션 기록에 남은 것만"이라는 경계가 붙는다. 세션 기록에 남지 않은 것은 세지 않는다.

상세는 [`plugins/claude-kit/tools/usage/README.md`](plugins/claude-kit/tools/usage/README.md).

## 개발용 검사

hook 스크립트의 테스트다. usage 도구의 검사 명령은 [그 README](plugins/claude-kit/tools/usage/README.md)에 있다.

```bash
python3 plugins/claude-kit/hooks/tests/test_issue_guard.py
python3 plugins/claude-kit/hooks/tests/test_squash_merge_guard.py
```

## 사용 예시

```text
이 선택지들 한눈에 비교하게 그려줘        → whiteboard
이 CLAUDE.md AI가 읽기 좋게 다이어트해줘   → ai-doc-improver
이거 시킬 프롬프트 짜줘                   → prompt-forge
메모앱에 쌓인 메모 정리해줘               → iphone-notes-digest
이거 나중에 해보면 좋겠는데 적어둬        → idea-note
로그인 세션 유지하면서 이 사이트 크롤링해줘 → browser-session
```

## 필수 환경

`iphone-notes-digest`만 **macOS 전용**(Apple Notes 자동화), 나머지는 OS 독립적이다.

- **[uv](https://docs.astral.sh/uv/)** — Python 도구를 격리 venv로 부트스트랩. `brew install uv`
- **ffmpeg** — 영상/오디오 처리. `brew install ffmpeg`
- **Apple Notes 권한** — 첫 실행 시 macOS 자동화 권한 허용 필요.
- **브라우저** — `whiteboard`(렌더 검증)·`html-to-image`·`browser-session`은 Chrome/Chromium을 쓴다.

> yt-dlp·whisper 등 Python 의존성은 첫 실행 때 `~/.cache/capture-kit` 격리 venv에 자동 설치된다 — 전역 환경을 건드리지 않는다.

## 트러블슈팅 (iphone-notes-digest)

- **메모 안 추출 / 권한 오류** — 시스템 설정 → 개인정보 보호 및 보안 → 자동화에서 "메모" 제어를 허용했는지 확인.
- **잠긴 메모 / 이메일 계정 메모 빠짐** — 의도된 동작. 추출 못 한 개수를 다이제스트에 정직하게 적는다("전부 봤다" 착시 방지).
- **`uv: command not found`** — `brew install uv` 후 새 셸에서 재시도.
- **영상 STT 느림 / 실패** — `ffmpeg` 설치 확인(`ffmpeg -version`). Intel Mac은 faster-whisper로 동작해 느릴 수 있다.

## 라이선스

MIT

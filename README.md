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

## 라이선스

MIT

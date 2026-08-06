#!/usr/bin/env bash
# gh issue create / edit 가드의 선별기. 판정은 issue_guard.py가 한다.
#
# 이 hook은 모든 Bash 호출에서 실행되고 그중 gh issue는 극히 일부다. 그래서 여기서는
# 대상 문자열 유무만 보고 없으면 아무 프로세스도 띄우지 않는다 — 실측 6.5ms.
# 넘길 때만 python을 exec한다(34ms). 인용부호와 heredoc과 플래그 파싱은 전부 저쪽이다.
set -euo pipefail

input=$(cat)

case "$input" in
  *"gh issue create"*|*"gh issue edit"*|*"gh api"*) ;;
  *) exit 0 ;;
esac

if ! command -v python3 >/dev/null 2>&1; then
  jq -nc '{
    systemMessage: "issue-guard: python3이 없어 이슈 본문 길이 검사를 건너뜁니다.",
    hookSpecificOutput: { hookEventName: "PreToolUse" }
  }'
  exit 0
fi

exec python3 "$(dirname "${BASH_SOURCE[0]}")/issue_guard.py" <<<"$input"

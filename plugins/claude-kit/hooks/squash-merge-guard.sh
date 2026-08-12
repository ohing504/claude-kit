#!/usr/bin/env bash
# gh pr merge --squash 가드의 선별기. 판정은 squash_merge_guard.py가 한다.
#
# 이 hook은 모든 Bash 호출에서 실행되고 그중 gh pr merge는 극히 일부다. 그래서 여기서는
# 대상 문자열 유무만 보고 없으면 아무 프로세스도 띄우지 않는다. 넘길 때만 python을
# exec한다. 인용부호와 heredoc과 플래그 파싱은 전부 저쪽이다 — 부분일치로 판정하던
# 시절엔 이 가드를 설명하는 커밋 메시지가 자기 자신에게 차단됐다.
set -euo pipefail

input=$(cat)

# 판정부보다 좁게 잡으면 그만큼이 검사 없이 통과한다 — 판정부는 `gh   pr\tmerge`처럼
# 공백이 늘어난 형태도 호출로 읽으므로 여기서는 순서만 보고 간격은 보지 않는다.
case "$input" in
  *gh*pr*merge*) ;;
  *) exit 0 ;;
esac

if ! command -v python3 >/dev/null 2>&1; then
  jq -nc '{
    systemMessage: "squash-merge-guard: python3이 없어 squash merge 검사를 건너뜁니다.",
    hookSpecificOutput: { hookEventName: "PreToolUse" }
  }'
  exit 0
fi

exec python3 "$(dirname "${BASH_SOURCE[0]}")/squash_merge_guard.py" <<<"$input"

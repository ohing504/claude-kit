#!/usr/bin/env bash
# gh issue create 가드.
#
# 산문 규약은 이슈 생성을 못 막는다는 실측이 근거다 — 한 저장소에서 생성 139건 중
# 72%가 사용자 요청 없이 만들어졌고, 사용자가 "이슈 계속 새로 만들지 말라"고 쓴
# 바로 그 메시지에서도 생성됐다. 같은 저장소가 만든 이슈의 29%를 나중에 삭제했다.
#
# 두 축으로 나눈다:
#   길이 초과      → deny.  기계 판정이라 오탐이 없다.
#   사용자 미요청  → 경고.  판정이 부정확해 차단하면 정당한 생성까지 막힌다.
set -euo pipefail

BODY_LIMIT=1200  # 4블록(무엇을/완료 조건/시작 지점/하지 말 것)이면 충분한 상한.
                 # 붕괴한 저장소 본문 중앙값 1,957자, 정상 운영 저장소 880~1,061자.

input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // ""')

case "$cmd" in
  *"gh issue create"*) ;;
  *) exit 0 ;;
esac

# ── 본문 길이 ────────────────────────────────────────────────────────────────
body=""
if body_file=$(printf '%s' "$cmd" | grep -oE -- '(--body-file|(^|[[:space:]])-F)[[:space:]]+[^[:space:]]+' | tail -1 | awk '{print $NF}'); then
  if [ -n "$body_file" ] && [ "$body_file" != "-" ] && [ -f "$body_file" ]; then
    body=$(cat "$body_file")
  fi
fi

# heredoc 형태: --body "$(cat <<'EOF' ... EOF)". 실측상 가장 흔한 생성 패턴이다.
# 종료 태그를 여는 줄에서 읽어 그 태그로 닫는다 (EOF 외 라벨과 <<- 형태도 처리).
if [ -z "$body" ]; then
  body=$(printf '%s' "$cmd" | awk '
    !started && /<</ {
      if (match($0, /<<-?\047?"?[A-Za-z_][A-Za-z_0-9]*"?\047?/)) {
        tag = substr($0, RSTART, RLENGTH)
        gsub(/[<>\-\047"]/, "", tag)
        started = 1
      }
      next
    }
    started && $0 == tag { exit }
    started { print }
  ')
fi

# 인라인 --body "..." 형태
if [ -z "$body" ]; then
  body=$(printf '%s' "$cmd" | perl -0777 -ne 'print $1 if /(?:--body|(?:^|\s)-b)[= ]"((?:[^"\\]|\\.)*)"/s' 2>/dev/null || true)
fi

if [ -n "$body" ]; then
  len=$(printf '%s' "$body" | LC_ALL=en_US.UTF-8 wc -m | tr -d ' ')
  if [ "$len" -gt "$BODY_LIMIT" ]; then
    reason="이슈 본문이 ${len}자로 상한 ${BODY_LIMIT}자를 넘습니다. 본문이 길수록 낡을 면적이 커지고 머지율이 떨어집니다(길이를 줄이면 단위당 +9%).

넘친 내용은 대개 이 넷 중 하나입니다 — 다음 자리로 보내세요.
  시점 실측(N줄, N토큰, permalink) → 재실행 명령(\`wc -l <path>\`)으로 대체
  미결과 결정                     → ADR. 완료 조건 첫 칸을 '결정하고 ADR에 남긴다'로
  환경과 아키텍처 배경             → CLAUDE.md 또는 AGENTS.md
  진행 상황                       → 적지 않음. 상태는 라벨에서 읽습니다

작성 규격은 /git-issue 스킬."

    jq -nc --arg r "$reason" '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason: $r
      }
    }'
    exit 0
  fi
fi

# ── 사용자가 요청했는가 (경고만) ──────────────────────────────────────────────
transcript=$(printf '%s' "$input" | jq -r '.transcript_path // ""')
[ -n "$transcript" ] && [ -f "$transcript" ] || exit 0

# 마지막 실제 사용자 발화. content가 문자열인 것만 — 배열은 tool_result다.
# tail -r은 BSD, tac은 GNU. 둘 다 없으면 이 검사를 건너뛴다.
if command -v tac >/dev/null 2>&1; then
  reverse=tac
elif tail -r </dev/null >/dev/null 2>&1; then
  reverse="tail -r"
else
  exit 0
fi

last_user=$($reverse "$transcript" 2>/dev/null \
  | jq -r 'select(.type=="user") | select((.message.content | type) == "string") | .message.content' 2>/dev/null \
  | head -1 || true)

[ -n "$last_user" ] || exit 0

if printf '%s' "$last_user" | grep -qiE '이슈|issue|남겨|등록해|백로그|backlog'; then
  exit 0
fi

jq -nc '{
  systemMessage: "직전 발화에 이슈 요청이 없습니다. 지금 세션에서 끝낼 일이면 커밋 메시지가 기록이고, 이슈는 다음 세션에 넘길 것만 만듭니다.",
  hookSpecificOutput: { hookEventName: "PreToolUse" }
}'
exit 0

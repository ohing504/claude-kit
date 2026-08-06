#!/usr/bin/env bash
# gh issue create / edit 가드.
#
# 산문 규약은 이슈 생성을 못 막는다는 실측이 근거다 — 한 저장소에서 생성 139건 중
# 72%가 사용자 요청 없이 만들어졌고, 사용자가 "이슈 계속 새로 만들지 말라"고 쓴
# 바로 그 메시지에서도 생성됐다. 같은 저장소가 만든 이슈의 29%를 나중에 삭제했다.
#
# 두 축으로 나눈다:
#   길이 초과      → deny.  기계 판정이라 오탐이 없다. create와 edit 둘 다 잰다 —
#                           create만 재면 edit --body-file로 상한을 우회한다.
#   사용자 미요청  → 경고.  판정이 부정확해 차단하면 정당한 생성까지 막힌다.
#                           create에만. edit은 기존 이슈 정리라 요청 발화가 없는 게 정상이다.
set -euo pipefail

BODY_LIMIT=1200  # 4블록(무엇을/완료 조건/시작 지점/하지 말 것)이면 충분한 상한.
                 # 붕괴한 저장소 본문 중앙값 1,957자, 정상 운영 저장소 880~1,061자.

input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // ""')

case "$cmd" in
  *"gh issue create"*) action=create ;;
  *"gh issue edit"*)   action=edit ;;
  *"gh api"*)          action=api ;;
  *) exit 0 ;;
esac

deny() {
  jq -nc --arg r "$1" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $r
    }
  }'
  exit 0
}

# ── gh api 우회 ──────────────────────────────────────────────────────────────
# gh issue를 거치지 않고 본문을 쓰는 경로. 길이를 재는 대신 경로 자체를 막는다.
# 조회와 라벨 목적 호출은 body 필드가 없어 걸리지 않고, 코멘트는 길이 규격 대상이 아니다.
if [ "$action" = api ]; then
  case "$cmd" in
    *comments*) exit 0 ;;
    *issues*) ;;
    *) exit 0 ;;
  esac
  printf '%s' "$cmd" \
    | grep -qE -- '(-f|-F|--field|--raw-field)[= ]+["'"'"']?body=' \
    || exit 0
  deny "\`gh api\`로 이슈 본문을 쓰면 본문 길이 규격(${BODY_LIMIT}자)이 검사되지 않습니다.

\`gh issue create --body-file <path>\` 또는 \`gh issue edit <N> --body-file <path>\`로 쓰세요.

작성 규격은 /git-issue 스킬."
fi

# ── 문자 수 세기 ─────────────────────────────────────────────────────────────
# wc -m은 로케일이 UTF-8일 때만 문자를 센다. 아니면 바이트를 세어 한글 본문이
# 3배로 계산되고 정상 길이가 차단된다. 1문자 프로브로 쓸 수 있는 로케일을 고른다.
char_locale=""
for loc in C.UTF-8 en_US.UTF-8 "${LC_ALL:-}" "${LANG:-}"; do
  [ -n "$loc" ] || continue
  if [ "$(printf '\303\244' | LC_ALL="$loc" wc -m 2>/dev/null | tr -d ' ')" = "1" ]; then
    char_locale=$loc
    break
  fi
done

check_len() {
  [ -n "$1" ] || return 0
  [ -n "$char_locale" ] || return 0
  len=$(printf '%s' "$1" | LC_ALL="$char_locale" wc -m | tr -d ' ')
  [ "$len" -gt "$BODY_LIMIT" ] || return 0

  deny "이슈 본문이 ${len}자로 상한 ${BODY_LIMIT}자를 넘습니다. 본문이 길수록 낡을 면적이 커지고 머지율이 떨어집니다(길이를 줄이면 단위당 +9%).

넘친 내용은 대개 이 넷 중 하나입니다 — 다음 자리로 보내세요.
  시점 실측(N줄, N토큰, permalink) → 재실행 명령(\`wc -l <path>\`)으로 대체
  미결과 결정                     → ADR. 완료 조건 첫 칸을 '결정하고 ADR에 남긴다'로
  환경과 아키텍처 배경             → CLAUDE.md 또는 AGENTS.md
  진행 상황                       → 적지 않음. 상태는 라벨에서 읽습니다

작성 규격은 /git-issue 스킬."
}

# ── 본문 길이: --body-file / -F ──────────────────────────────────────────────
# --body-file <path> / --body-file=<path> / -F 단축형 모두 받는다.
# 한 명령에 여러 번 나오면(`&&` 체인) 전부 잰다 — 마지막 하나만 재면 앞의 것이 통과한다.
body_files=$(printf '%s' "$cmd" \
  | grep -oE -- '(--body-file|(^|[[:space:]])-F)[=[:space:]][[:space:]]*[^[:space:]]+' \
  | sed -E 's/^.*(--body-file|-F)[=[:space:]][[:space:]]*//' || true)

body_file=""  # 마지막 경로. 아래 heredoc 캡처에서 리다이렉트 대상 판별에 쓴다.
while IFS= read -r f; do
  [ -n "$f" ] || continue
  f=${f%\"}; f=${f#\"}
  f=${f%\'}; f=${f#\'}

  # 표준입력으로 넘긴 본문은 hook이 읽을 수 없어 길이를 잴 방법이 없다. 파일 경로를 요구한다.
  if [ "$f" = "-" ]; then
    deny "본문을 표준입력(\`--body-file -\`)으로 넘기면 길이 규격(${BODY_LIMIT}자)을 검사할 수 없습니다.

본문을 파일로 쓰고 \`--body-file <path>\`로 넘기세요.

작성 규격은 /git-issue 스킬."
  fi

  body_file=$f
  [ -f "$f" ] || continue
  check_len "$(cat "$f")"
done <<EOF
$body_files
EOF

# ── 본문 길이: heredoc ───────────────────────────────────────────────────────
# --body "$(cat <<'EOF' ... EOF)" 형태. 실측상 가장 흔한 생성 패턴이다.
# 이슈 본문과 무관한 heredoc(다른 파일 작성 등)을 재지 않도록, 여는 줄이 본문
# 플래그거나 위에서 찾은 body-file 경로로 리다이렉트할 때만 캡처한다.
# 종료 태그는 여는 줄에서 읽어 그 태그로 닫는다 (EOF 외 라벨과 <<- 형태도 처리).
check_len "$(printf '%s' "$cmd" | awk -v want="$body_file" '
  !started && /<</ && ($0 ~ /--body|-b[ =]|gh issue (create|edit)/ || (want != "" && index($0, want) > 0)) {
    if (match($0, /<<-?\047?"?[A-Za-z_][A-Za-z_0-9]*"?\047?/)) {
      raw = substr($0, RSTART, RLENGTH)
      indented = (index(raw, "<<-") == 1)
      tag = raw
      gsub(/[<>\-\047"]/, "", tag)
      started = 1
    }
    next
  }
  started {
    line = $0
    if (indented) sub(/^[ \t]+/, "", line)
    if (line == tag) exit
    print
  }
')"

# ── 본문 길이: 인라인 --body "..." / --body '...' ────────────────────────────
check_len "$(printf '%s' "$cmd" | perl -0777 -ne 'print(($1 // $2)) if /(?:--body|(?:^|\s)-b)[= ](?:"((?:[^"\\]|\\.)*)"|\x27([^\x27]*)\x27)/s' 2>/dev/null || true)"

# ── 사용자가 요청했는가 (create만, 경고만) ───────────────────────────────────
[ "$action" = create ] || exit 0

transcript=$(printf '%s' "$input" | jq -r '.transcript_path // ""')
[ -n "$transcript" ] && [ -f "$transcript" ] || exit 0

# 마지막 실제 사용자 발화. content가 문자열인 것만 — 배열은 tool_result다.
# isMeta는 슬래시 커맨드 caveat나 훅 주입 컨텍스트라 실제 발화가 아니다.
# @json으로 한 줄에 담아야 여러 줄 발화의 둘째 줄 이후가 잘리지 않는다.
# tail -r은 BSD, tac은 GNU. 둘 다 없으면 이 검사를 건너뛴다.
if command -v tac >/dev/null 2>&1; then
  reverse=tac
elif tail -r </dev/null >/dev/null 2>&1; then
  reverse="tail -r"
else
  exit 0
fi

last_user=$($reverse "$transcript" 2>/dev/null \
  | jq -r 'select(.type=="user") | select(.isMeta != true) | select((.message.content | type) == "string") | .message.content | @json' 2>/dev/null \
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

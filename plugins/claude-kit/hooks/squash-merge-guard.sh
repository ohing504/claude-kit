#!/usr/bin/env bash
# gh pr merge --squash without --subject/--body bypasses the squash-merge skill's
# net-diff message hygiene (default squash msg bleeds individual commits + session
# context). Block it so the skill flow isn't silently skipped.
set -euo pipefail

input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // ""')

# Only inspect gh pr merge invocations.
case "$cmd" in
  *"gh pr merge"*) ;;
  *) exit 0 ;;
esac

# squash selected? (long --squash or short -s)
if ! printf '%s' "$cmd" | grep -Eq -- '(--squash|(^|[[:space:]])-s([[:space:]]|=|$))'; then
  exit 0
fi

has_subject=0
has_body=0
printf '%s' "$cmd" | grep -Eq -- '(--subject|(^|[[:space:]])-t([[:space:]]|=))' && has_subject=1
printf '%s' "$cmd" | grep -Eq -- '(--body([[:space:]]|=)|--body-file|(^|[[:space:]])-b([[:space:]]|=)|(^|[[:space:]])-F([[:space:]]|=))' && has_body=1

# Both present → skill-compliant, allow through.
if [ "$has_subject" -eq 1 ] && [ "$has_body" -eq 1 ]; then
  exit 0
fi

reason="--subject/--body 없는 squash merge — /squash-merge 스킬로 진행하세요."

jq -nc --arg r "$reason" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: $r
  }
}'
exit 0

#!/usr/bin/env bash
#
# list_folders.sh — Apple Notes 폴더 목록과 각 폴더의 메모 수를 출력한다.
# 어떤 폴더를 처리할지 사용자가 고르도록 *먼저* 보여주는 용도.
# (잠긴 폴더는 osascript에 잡히지 않아 자동으로 빠진다.)
#
# 출력 예:
#   Notes (37)
#   레시피 (12)
#   여행 (8)

set -euo pipefail

osascript <<'EOF'
tell application "Notes"
    set out to ""
    repeat with f in every folder
        set out to out & name of f & " (" & (count of notes of f) & ")" & linefeed
    end repeat
    return out
end tell
EOF

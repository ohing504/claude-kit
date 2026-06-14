#!/usr/bin/env bash
#
# list_folders.sh — Apple Notes 폴더 목록을 account별로 묶어 출력한다.
# 어떤 폴더를 처리할지 사용자가 고르도록 *먼저* 보여주는 용도.
#
# account를 함께 보이는 이유: 메모앱엔 iCloud 외에 Gmail/Exchange 같은
# 이메일 계정 폴더가 섞여 있고, 폴더명이 account 간 겹칠 수 있다(양쪽 다 "Notes").
# account 없이 폴더명만 보이면 엉뚱한 폴더를 고르거나 빠뜨린다.
# 잠긴 메모 수도 함께 표기해, 본문을 못 보는 메모가 몇 건인지 미리 알린다.
# (잠긴 폴더 자체는 osascript에 잡히지 않아 여기서도 빠진다.)
#
# 출력 예:
#   [iCloud]
#   레시피 (12)
#   여행 (8, 잠김 2)
#   [Google]
#   Notes (0)

set -euo pipefail

osascript <<'EOF'
tell application "Notes"
    set out to ""
    repeat with a in every account
        set out to out & "[" & (name of a) & "]" & linefeed
        repeat with f in folders of a
            set noteTotal to count of notes of f
            set lockedCount to count of (notes of f whose password protected is true)
            if lockedCount > 0 then
                set out to out & (name of f) & " (" & noteTotal & ", 잠김 " & lockedCount & ")" & linefeed
            else
                set out to out & (name of f) & " (" & noteTotal & ")" & linefeed
            end if
        end repeat
    end repeat
    return out
end tell
EOF

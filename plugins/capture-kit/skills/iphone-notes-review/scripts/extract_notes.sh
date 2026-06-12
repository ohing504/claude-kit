#!/usr/bin/env bash
#
# extract_notes.sh — Apple Notes(맥/아이폰 iCloud 동기화)에서 메모를 추출해
# 구조화된 텍스트로 표준출력에 내보낸다. 읽기 전용 — 원본 메모를 건드리지 않는다.
#
# 사용:
#   extract_notes.sh            # 전체 메모
#   extract_notes.sh "폴더명"   # 특정 폴더만
#
# 출력: 메모마다 아래 블록 (구분자 @@@NOTE@@@)
#   @@@NOTE@@@
#   title: ...
#   created: ...
#   folder: ...
#   body:
#   <HTML 본문 — 링크는 <a href="..."> 로 들어 있음>
#
# 주의: 첫 실행 시 macOS가 Notes 자동화 권한을 묻는다(허용 필요).
# AppleScript의 `plaintext`는 repeat 변수 참조로 읽으면 깨지므로 `body`(HTML)를 쓴다.

set -euo pipefail

FOLDER="${1:-}"

# 폴더를 바깥에서 순회한다. note 쪽에서 `name of container`를 읽으면 -1700으로
# 깨지므로(컨테이너 참조가 unicode text로 변환 안 됨), 폴더 객체에서 그 안의
# 노트를 돌면 폴더명을 확실히 얻는다.
osascript <<EOF
tell application "Notes"
    set out to ""
    if "${FOLDER}" is "" then
        set folderList to every folder
    else
        set folderList to {folder "${FOLDER}"}
    end if
    repeat with f in folderList
        set fname to name of f
        set theNotes to notes of f
        repeat with i from 1 to (count of theNotes)
            set n to item i of theNotes
            set out to out & "@@@NOTE@@@" & linefeed
            set out to out & "title: " & (name of n) & linefeed
            set out to out & "created: " & (creation date of n as string) & linefeed
            set out to out & "folder: " & fname & linefeed
            set out to out & "body:" & linefeed & (body of n) & linefeed
        end repeat
    end repeat
    return out
end tell
EOF

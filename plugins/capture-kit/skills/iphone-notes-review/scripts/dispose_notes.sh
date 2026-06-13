#!/usr/bin/env bash
#
# dispose_notes.sh — 자산화가 끝난 메모를 메모앱(Apple Notes)에서 제거한다.
#
# 경계: 메모앱 컨트롤(삭제 포함)은 이 스킬 영역이다. vault·세션에서 raw osascript를
# 즉석에서 짜지 말고 이 검증된 커맨드를 쓴다(재사용·안전·동작 패턴 고정).
# '무엇을 어디로 자산화할지'는 스킬 밖(사용자/vault) 결정 — 이 스크립트는 '삭제 실행'만.
#
# 안전:
#   - 기본은 DRY RUN — 매칭 대상만 출력하고 삭제하지 않는다. 실제 삭제는 --confirm 필요.
#   - 매칭은 노트 '본문에 토큰 포함'. 토큰은 보통 링크 고유 ID(예: 릴스 ID)라 특정 노트만 정확히 겨냥.
#   - 삭제된 노트는 메모앱 "최근 삭제됨"으로 가 30일 복구 가능.
#
# 사용:
#   dispose_notes.sh <토큰> [토큰...]            # DRY RUN — 대상만 보여줌
#   dispose_notes.sh --confirm <토큰> [토큰...]  # 실제 삭제
#
# 처분 단위는 '자산화 완료분'이다 — 자산화가 끝난 링크의 고유 토큰만 넘긴다.
# 한 메모의 일부 링크만 자산화됐다면(나머지 미처리), 그 메모는 아직 넘기지 않는다.

set -uo pipefail

CONFIRM=0
if [[ "${1:-}" == "--confirm" ]]; then CONFIRM=1; shift; fi
if [[ $# -eq 0 ]]; then
  echo "사용: dispose_notes.sh [--confirm] <토큰> [토큰...]" >&2
  echo "      토큰은 노트 본문에 든 고유 문자열(예: 인스타 릴스 ID). DRY RUN이 기본." >&2
  exit 1
fi

# 토큰들을 AppleScript 리스트 리터럴로 변환(따옴표·역슬래시 이스케이프)
LIST="{"
for t in "$@"; do
  e=${t//\\/\\\\}; e=${e//\"/\\\"}
  LIST+="\"$e\", "
done
LIST="${LIST%, }}"

# 폴더 객체를 순회한다 — `notes`(전체)·`notes of folder "이름"` 참조는 -1728로 깨진다.
# 삭제는 읽기 루프가 끝난 뒤 모아서 수행한다(반복 중 삭제하면 컬렉션이 깨짐).
osascript <<EOF
tell application "Notes"
    set tokens to $LIST
    set matched to {}
    repeat with f in (every folder)
        set fname to name of f
        -- 이미 삭제된 사본을 다시 잡지 않도록 '최근 삭제됨' 폴더는 건너뛴다
        if fname is "Recently Deleted" or fname contains "삭제" then
        else
        set theNotes to notes of f
        repeat with i from 1 to (count of theNotes)
            set n to item i of theNotes
            set b to body of n
            repeat with t in tokens
                if b contains (t as string) then
                    set end of matched to n
                    exit repeat
                end if
            end repeat
        end repeat
        end if
    end repeat
    if (count of matched) is 0 then return "매칭된 메모 없음"
    set out to ""
    repeat with n in matched
        set out to out & "  - " & (name of n) & linefeed
    end repeat
    if $CONFIRM is 1 then
        repeat with n in matched
            delete n
        end repeat
        return "삭제됨 (" & (count of matched) & "건, 최근 삭제됨으로 이동):" & linefeed & out
    else
        return "DRY RUN — 대상 " & (count of matched) & "건 (삭제하려면 --confirm 추가):" & linefeed & out
    end if
end tell
EOF

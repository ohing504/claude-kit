#!/usr/bin/env bash
#
# extract_scans.sh — 한 메모에 붙은 "스캔 문서"와 이미지 첨부의 *원본*을 꺼낸다.
# collect.sh/extract_notes.sh는 본문 텍스트·링크만 다루고, Apple 스캔 문서
# (문서 스캔, UTI com.apple.paper.doc.scan)는 AppleScript `attachments`에 0개로
# 잡히고 `body`는 -1700 에러라 아예 안 보인다. 이 스크립트는 NoteStore.sqlite를
# 읽기전용으로 조회해 그 메모의 스캔/이미지 원본 파일을 출력 디렉토리로 복사한다.
#
# 사용:
#   extract_scans.sh "<메모 제목>" [출력디렉토리]
#   extract_scans.sh "x-coredata://.../ICNote/p348" [출력디렉토리]   # AppleScript id도 가능
#
# 출력(기본 ./notes-scans/<Z_PK>/):
#   scan_<contentUUID8>_<n>.<ext>   스캔 문서의 페이지별 원본 (여러 장)
#   image_<n>.<ext>                 일반 이미지 첨부 원본
#   FallbackPDF_<contentUUID8>.pdf  (원본 페이지를 못 찾은 스캔의 폴백 PDF)
#
# 중요 — 페이지 순서: 스캔 원본은 번들 안 해시 파일명이라 파일시스템 순서 ≠ 실제
# 페이지 순서다. 순서·분류(계약서/증명서/…)는 이 스크립트가 정하지 않는다 —
# 꺼낸 이미지를 다이제스트 작성 LLM이 눈으로 읽어 정렬한다(extract_frames와 같은
# 경계: 추출=스크립트, 판독=LLM). FallbackPDF는 폴백이라 페이지가 누락될 수
# 있으니(관측: 7장 스캔에 3장만 담김) 원본(Assets.bundle)을 항상 우선한다.

set -euo pipefail

QUERY="${1:?사용: extract_scans.sh \"<메모 제목 또는 AppleScript-id>\" [출력디렉토리]}"
STORE="$HOME/Library/Group Containers/group.com.apple.notes"
SQLITE_DB="$STORE/NoteStore.sqlite"
# ?mode=ro + 사이드카(-wal/-shm) 제자리 = 최근 변경(WAL)까지 반영. immutable=1 금지.
DB_URI="file:$SQLITE_DB?mode=ro"

[ -f "$SQLITE_DB" ] || { echo "NoteStore.sqlite 없음: $SQLITE_DB" >&2; exit 1; }

sql() { sqlite3 "$DB_URI" "$1"; }
q() { printf '%s' "$1" | sed "s/'/''/g"; }  # SQL 문자열 이스케이프

# ── 1) 입력 → 메모 Z_PK ────────────────────────────────────────────────
if [[ "$QUERY" =~ /ICNote/p([0-9]+)$ ]]; then
    NOTEPK="${BASH_REMATCH[1]}"
else
    PKS="$(sql "SELECT Z_PK FROM ZICCLOUDSYNCINGOBJECT WHERE ZTITLE1='$(q "$QUERY")';")"
    n_pk=$(printf '%s\n' "$PKS" | grep -c .)
    if [ "$n_pk" -eq 0 ]; then
        echo "제목이 '$QUERY'인 메모를 못 찾음. (list_folders.sh로 폴더 확인, 동기화 지연 가능)" >&2
        exit 2
    elif [ "$n_pk" -gt 1 ]; then
        echo "제목 '$QUERY'가 여러 건. Z_PK로 다시 지정하세요:" >&2
        printf '%s\n' "$PKS" | while read -r pk; do echo "  x-coredata://.../ICNote/p$pk"; done >&2
        exit 3
    fi
    NOTEPK="$PKS"
fi

# 암호 메모 가드
if [ "$(sql "SELECT COALESCE(ZISPASSWORDPROTECTED,0) FROM ZICCLOUDSYNCINGOBJECT WHERE Z_PK=$NOTEPK;")" = "1" ]; then
    echo "메모(Z_PK=$NOTEPK)가 암호 보호됨 — 잠금 해제 전엔 첨부 추출 불가." >&2
    exit 4
fi

OUTDIR="${2:-./notes-scans/$NOTEPK}"
mkdir -p "$OUTDIR"
# 단일 계정이면 glob이 안전. 다계정이면 메모의 ZACCOUNT7로 계정 UUID를 잡는다.
ACCT_UUID="$(sql "SELECT acc.ZIDENTIFIER FROM ZICCLOUDSYNCINGOBJECT n JOIN ZICCLOUDSYNCINGOBJECT acc ON acc.Z_PK=n.ZACCOUNT7 WHERE n.Z_PK=$NOTEPK;")"
ACCT="$STORE/Accounts/$ACCT_UUID"
[ -d "$ACCT" ] || ACCT="$(ls -d "$STORE/Accounts"/*/ 2>/dev/null | head -1)"

ext_of() { file -b --mime-type "$1" | sed 's|.*/||;s|jpeg|jpg|'; }

echo "메모 Z_PK=$NOTEPK → $OUTDIR"
n_scan=0 n_img=0 n_pending=0

# ── 2) 스캔 문서 ──────────────────────────────────────────────────────
# 우선순위:
#  (1) 메모앱이 공유 시 만든 크롭·보정 완전본 PDF — 메모앱이 화면에 보여주는 바로 그
#      결과물. 스캔 문서를 메모앱에서 공유(공유→복사/파일에 저장)하면
#      Data/tmp/TemporaryItems/**/HardLinkURLTemp/<UUID>/<n>/<제목>.pdf 에 생성된다.
#      전 페이지가 deskew·크롭돼 있어 가장 좋다. (사용자가 한 번 공유해야 존재)
#  (2) Assets.bundle 원본 JPEG — 크롭 *전* 촬영 원본. 페이지 수는 완전하지만 책상·손이
#      같이 찍혀 지저분하다. 크롭 변환은 번들 DB(Reference)에 CRDT로만 있어 파일론 미적용.
#  (3) FallbackPDF — 크롭됐지만 렌더된 페이지만 담겨 누락 가능(관측: 7장 중 3장).
NOTES_TMP="$HOME/Library/Containers/com.apple.Notes/Data/tmp/TemporaryItems"
while IFS='|' read -r UUID GEN; do
    [ -n "$UUID" ] || continue
    CROP="$(ls "$NOTES_TMP"/*/HardLinkURLTemp/"$UUID"/*/*.pdf 2>/dev/null | head -1)"
    BUNDLE="$ACCT/Paper/Bundles/$UUID.bundle/Assets.bundle"
    if [ -n "$CROP" ] && [ -f "$CROP" ]; then
        cp "$CROP" "$OUTDIR/scan_${UUID:0:8}_crop.pdf"; n_scan=$((n_scan+1))
        echo "  ✓ ${UUID:0:8}: 메모앱 크롭 완전본 PDF 사용" >&2
    elif [ -d "$BUNDLE" ] && [ -n "$(ls -A "$BUNDLE" 2>/dev/null)" ]; then
        i=1
        for f in "$BUNDLE"/*; do
            [ -f "$f" ] || continue
            cp "$f" "$OUTDIR/scan_${UUID:0:8}_$i.$(ext_of "$f")"; i=$((i+1)); n_scan=$((n_scan+1))
        done
        echo "  ⚠️ ${UUID:0:8}: 크롭 전 원본 $((i-1))장 사용 — 크롭 완전본을 원하면 메모앱에서 이 스캔을 '공유→복사' 후 재실행" >&2
    else
        PDF="$ACCT/FallbackPDFs/$UUID/$GEN/FallbackPDF.pdf"
        [ -f "$PDF" ] || PDF="$(ls "$ACCT/FallbackPDFs/$UUID"/*/FallbackPDF.pdf 2>/dev/null | head -1)"
        if [ -n "$PDF" ] && [ -f "$PDF" ]; then
            cp "$PDF" "$OUTDIR/FallbackPDF_${UUID:0:8}.pdf"; n_scan=$((n_scan+1))
            echo "  ⚠️ ${UUID:0:8}: 원본 번들 없음 → FallbackPDF만 복사(페이지 누락 가능)" >&2
        else
            echo "  ⚠️ ${UUID:0:8}: 스캔 원본·폴백 모두 로컬에 없음 — iCloud 미다운로드(메모앱에서 열어 다운로드 필요)" >&2
            n_pending=$((n_pending+1))
        fi
    fi
done < <(sql "SELECT ZIDENTIFIER||'|'||COALESCE(ZFALLBACKPDFGENERATION,'') FROM ZICCLOUDSYNCINGOBJECT WHERE ZNOTE=$NOTEPK AND ZTYPEUTI='com.apple.paper.doc.scan';")

# ── 3) 이미지 첨부(Media/): 첨부행 → 미디어행 조인 ─────────────────────
while IFS='|' read -r MUUID MGEN MFILE; do
    [ -n "$MUUID" ] || continue
    SRC="$ACCT/Media/$MUUID/$MGEN/$MFILE"
    [ -f "$SRC" ] || SRC="$(ls "$ACCT/Media/$MUUID"/*/"$MFILE" 2>/dev/null | head -1)"
    [ -f "$SRC" ] || SRC="$(ls "$ACCT/Media/$MUUID/$MFILE" 2>/dev/null | head -1)"  # 구형 레이아웃
    if [ -n "$SRC" ] && [ -f "$SRC" ]; then
        n_img=$((n_img+1)); cp "$SRC" "$OUTDIR/image_${n_img}.$(ext_of "$SRC")"
    else
        echo "  ⚠️ 이미지 첨부 원본 없음(미다운로드): $MUUID/$MFILE" >&2; n_pending=$((n_pending+1))
    fi
done < <(sql "SELECT m.ZIDENTIFIER||'|'||COALESCE(m.ZGENERATION1,'')||'|'||COALESCE(m.ZFILENAME,'') FROM ZICCLOUDSYNCINGOBJECT a JOIN ZICCLOUDSYNCINGOBJECT m ON m.Z_PK=a.ZMEDIA WHERE a.ZNOTE=$NOTEPK AND a.ZMEDIA IS NOT NULL AND COALESCE(a.ZTYPEUTI,'') NOT LIKE 'com.apple.paper%';")

echo "완료: 스캔 페이지 $n_scan · 이미지 $n_img · 미다운로드 $n_pending → $OUTDIR"
[ "$n_pending" -gt 0 ] && echo "※ 미다운로드분은 메모앱에서 해당 메모를 열어 원본을 내려받은 뒤 다시 실행하세요." >&2
exit 0

#!/usr/bin/env bash
# squash-merge/post_merge.sh — 머지한 PR의 원격 브랜치를 지우고, 메인 체크아웃에서 실행했을 때만
# 로컬 브랜치 삭제와 base 동기화를 한다.
#
# 워크트리는 어떤 경우에도 지우지 않는다. 다른 세션이 쓰는 중일 수 있고, 데스크톱 앱과 CLI가
# 각자 정리하기 때문이다. 미커밋 변경은 어느 경로에서도 건드리지 않는다.
#
# 사용: post_merge.sh <head-branch> <base-branch> <PR headRefOid>
# 종료코드: 0=처리 완료(건너뛴 항목은 출력으로 보고), 2=입력 오류
set -u

HEAD_BRANCH="${1:-}"
BASE="${2:-}"
HEAD_OID="${3:-}"
if [ -z "$HEAD_BRANCH" ] || [ -z "$BASE" ] || [ -z "$HEAD_OID" ]; then
  echo "usage: post_merge.sh <head-branch> <base-branch> <head-oid>" >&2
  exit 2
fi

delete_remote_branch() {
  # repo auto-delete가 켜져 있으면 이미 없다. 있을 때만 지워 실패 출력을 만들지 않는다.
  if git ls-remote --exit-code --heads origin "$HEAD_BRANCH" >/dev/null 2>&1; then
    git push origin --delete "$HEAD_BRANCH" >/dev/null 2>&1 \
      && echo "원격 브랜치 삭제: $HEAD_BRANCH" \
      || echo "원격 브랜치 삭제 실패: $HEAD_BRANCH — 직접 확인이 필요합니다"
  fi
  git remote prune origin >/dev/null 2>&1
}

# 사람용 `git worktree list`는 경로를 공백으로 이어 붙이므로 --porcelain으로 읽는다.
main_worktree() {
  git worktree list --porcelain | grep -m1 '^worktree ' | cut -d' ' -f2-
}

worktree_of_branch() {
  git worktree list --porcelain \
    | awk -v b="refs/heads/$1" '/^worktree /{w=substr($0,10)} $0=="branch "b{print w; exit}'
}

is_dirty() {
  [ -n "$(git status --porcelain)" ]
}

# squash 머지 뒤 브랜치는 base의 조상이 아니라 `branch -d`로 판정할 수 없다. 대신 PR에 들어간
# 커밋(headRefOid) 안에 있는지로 판정해, PR에 없는 로컬 커밋을 지우지 않는다.
in_pr() {
  local tip
  tip=$(git rev-parse "refs/heads/$HEAD_BRANCH")
  [ "$tip" = "$HEAD_OID" ] || git merge-base --is-ancestor "$tip" "$HEAD_OID" 2>/dev/null
}

update_base_ref() {
  git fetch origin "$BASE:$BASE" >/dev/null 2>&1 \
    && echo "로컬 $BASE 갱신 (체크아웃은 그대로)" \
    || echo "$BASE 동기화 건너뜀 — fast-forward할 수 없거나 다른 워크트리가 쓰는 중입니다"
}

delete_remote_branch

CURRENT_WT=$(git rev-parse --show-toplevel)
MAIN_WT=$(main_worktree)

if [ "$CURRENT_WT" != "$MAIN_WT" ]; then
  # base는 대개 메인 체크아웃이 소유해 여기서 갱신되지 않고, 새 워크트리는 원격 base에서 시작한다.
  if [ -e "$(git rev-parse --absolute-git-dir)/claude-desktop-worktree" ]; then
    echo "데스크톱 앱 워크트리 — 이 폴더와 브랜치는 세션을 보관한 뒤 앱이 정리합니다"
  else
    echo "linked 워크트리 — 이 폴더와 브랜치는 세션 종료 프롬프트에서 정리하세요"
  fi
  exit 0
fi

CURRENT_BRANCH=$(git branch --show-current)

if git show-ref --verify --quiet "refs/heads/$HEAD_BRANCH"; then
  OWNER=$(worktree_of_branch "$HEAD_BRANCH")
  if [ -n "$OWNER" ] && [ "$OWNER" != "$MAIN_WT" ]; then
    echo "브랜치 보존: $HEAD_BRANCH — 다른 워크트리가 쓰는 중입니다: $OWNER"
  elif ! in_pr; then
    echo "브랜치 보존: $HEAD_BRANCH — PR에 없는 커밋이 있습니다"
  elif [ "$CURRENT_BRANCH" = "$HEAD_BRANCH" ]; then
    if is_dirty; then
      echo "브랜치 보존: $HEAD_BRANCH — 미커밋 변경이 있습니다"
    elif git checkout "$BASE" >/dev/null 2>&1; then
      CURRENT_BRANCH="$BASE"
      git branch -D "$HEAD_BRANCH" >/dev/null && echo "로컬 브랜치 삭제: $HEAD_BRANCH"
    else
      echo "브랜치 보존: $HEAD_BRANCH — $BASE로 체크아웃하지 못했습니다"
    fi
  else
    git branch -D "$HEAD_BRANCH" >/dev/null && echo "로컬 브랜치 삭제: $HEAD_BRANCH"
  fi
fi

if [ "$CURRENT_BRANCH" != "$BASE" ]; then
  update_base_ref
elif is_dirty; then
  echo "$BASE 동기화 건너뜀 — 미커밋 변경이 있습니다"
elif git pull --ff-only origin "$BASE" >/dev/null 2>&1; then
  echo "$BASE 동기화 완료"
else
  echo "$BASE 동기화 건너뜀 — fast-forward할 수 없습니다"
fi

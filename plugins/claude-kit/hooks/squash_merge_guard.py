#!/usr/bin/env python3
"""gh pr merge --squash 가드의 판정부.

두 가지를 막는다:

  --subject/--body 없음  기본 squash 메시지는 개별 commit을 이어붙여 PR 내부 단계와
                         세션 맥락이 그대로 새어 나온다. /squash-merge 스킬이 net diff로
                         메시지를 쓰게 한다.
  --delete-branch        원격만이 아니라 로컬까지 정리하는데, 그 과정에서 gh가 현재
                         워크트리에서 base를 checkout하고 `git pull`을 실행한다. 다른
                         세션의 미커밋 변경이 있으면 그 pull이 실패하고(`pull.rebase=true`
                         환경에서 rebase 거부) 체크아웃된 브랜치만 바뀐 채 남는다.
                         원격 삭제는 `git push origin --delete`, 로컬 정리는 스킬 Step 5.

호출은 squash-merge-guard.sh가 한다. 그쪽은 대상 문자열 유무만 보고 여기로 넘긴다.
"""
import json
import re
import sys

from gh_command import segments, split_heredocs

SKILL_REF = "작성 규격은 /squash-merge 스킬."

PR_MERGE = r"pr[ \t]+merge\b"

# 단축 플래그는 묶여 올 수 있다(`-sd`). 하나만 보고 판단하면 묶음이 검사를 통과한다.
SQUASH_FLAG = re.compile(r"--squash|(?:^|\s)-[A-Za-z]*s[A-Za-z]*(?:\s|=|$)")
DELETE_BRANCH_FLAG = re.compile(r"--delete-branch|(?:^|\s)-[A-Za-z]*d[A-Za-z]*(?:\s|=|$)")
# 값을 받는 플래그라 묶음 중간에 오지 않는다. 여기서 넓게 잡으면 없는 것을 있다고 읽어
# 통과시키므로 좁게 둔다.
SUBJECT_FLAG = re.compile(r"--subject|(?:^|\s)-t(?:\s|=)")
BODY_FLAG = re.compile(r"--body(?:\s|=)|--body-file|(?:^|\s)-[bF](?:\s|=)")


def deny(reason):
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}


def judge(payload):
    """hook 출력 dict를 돌려준다. 낼 것이 없으면 None."""
    command = payload.get("tool_input", {}).get("command", "")
    cmd_exec, _ = split_heredocs(command)

    for segment in segments(cmd_exec, PR_MERGE):
        if not SQUASH_FLAG.search(segment):
            continue
        if DELETE_BRANCH_FLAG.search(segment):
            return deny(
                "squash merge에 `--delete-branch`(`-d`)를 쓰지 마세요. 이 옵션은 원격뿐 "
                "아니라 로컬까지 정리하면서 현재 워크트리에서 base를 checkout하고 "
                "`git pull`을 실행합니다 — 다른 세션의 미커밋 변경이 있으면 실패하고 "
                "체크아웃된 브랜치만 바뀐 채 남습니다.\n"
                "\n"
                "원격 head는 머지 뒤 `git push origin --delete <branch>`로 지우고, 로컬 "
                "브랜치와 worktree 정리는 스킬 Step 5로 하세요.\n"
                "\n" + SKILL_REF)
        if not (SUBJECT_FLAG.search(segment) and BODY_FLAG.search(segment)):
            return deny(
                "`--subject`/`--body` 없는 squash merge는 GitHub 기본 메시지(개별 commit "
                "이어붙이기)를 씁니다. PR 내부 단계와 되돌린 작업이 그대로 남습니다.\n"
                "\n"
                "net diff만 보고 메시지를 쓴 뒤 `--subject`와 `--body`로 넘기세요.\n"
                "\n" + SKILL_REF)
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    result = judge(payload)
    if result is not None:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

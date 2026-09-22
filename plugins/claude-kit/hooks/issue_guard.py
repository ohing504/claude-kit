#!/usr/bin/env python3
"""gh issue create / edit 가드의 판정부.

산문 규약은 이슈 생성을 못 막는다는 실측이 근거다 — 한 저장소에서 생성 139건 중
72%가 사용자 요청 없이 만들어졌고, 사용자가 "이슈 계속 새로 만들지 말라"고 쓴
바로 그 메시지에서도 생성됐다. 같은 저장소가 만든 이슈의 29%를 나중에 삭제했다.

judge()가 이 순서로 본다:
  본문을 못 읽는 경로 → deny.  `gh api`와 `--body-file -`는 본문이 hook을 거치지
                               않아 아래 둘을 아예 잴 수 없다. 값 대신 경로를 막는다.
  길이 초과           → deny.  기계 판정이라 오탐이 없다. create와 edit 둘 다 잰다 —
                               create만 재면 edit --body-file로 상한을 우회한다.
  `## 왜` 누락        → create는 deny, edit은 경고. edit은 옛 규격으로 열린 이슈를
                               고치는 경로라, 막으면 정리 자체를 못 한다.
  사용자 미요청       → 경고.  판정이 부정확해 차단하면 정당한 생성까지 막힌다.
                               create에만. edit은 기존 이슈 정리라 요청 발화가 없는 게 정상이다.

호출은 issue-guard.sh가 한다. 그쪽은 대상 문자열 유무만 보고 여기로 넘긴다.
"""
import json
import os
import re
import sys

from gh_command import COMMAND_POSITION, segments, split_heredocs

# 왜/완료 조건/시작 지점/하지 말 것을 쓰면 들어가는 상한.
# 이슈가 쌓이기만 한 저장소는 본문 중앙값 1,957자, 정상 운영 저장소는 880~1,061자.
# 옛 상한 1,200자에는 실측상 대부분의 본문이 걸렸다 — 한 저장소의 열린 이슈 30건이
# 중앙값 858자인데 최대가 1,199자로 상한에 붙어 있었다. 잘려나간 것은 군더더기가
# 아니라 `## 왜`의 원인과 손해였다.
BODY_LIMIT = 1600
# 선택지를 나열하고 각각의 근거 좌표를 붙이는 블록이 있으면 그만큼 더 쓴다.
PARLEY_LIMIT = 1900

# 이 헤딩이 있으면 상한이 PARLEY_LIMIT으로 올라간다.
PARLEY_HEADING = "## 착수 전 합의할 것"
# 이 헤딩이 없으면 create를 막는다. 없는 본문은 제목이 이미 가진 것만 되풀이한다.
WHY_HEADING = "## 왜"

SKILL_REF = "작성 규격은 /git-issue 스킬."

BODY_FILE_FLAG = re.compile(r"(?:--body-file|(?:^|\s)-F)[=\s]\s*(\S+)")
INLINE_BODY_FLAG = re.compile(
    r"(?:--body|(?:^|\s)-b)[= ](?:\"((?:[^\"\\]|\\.)*)\"|'([^']*)')", re.S)
API_BODY_FIELD = re.compile(r"(?:-f|-F|--field|--raw-field)[= ]+[\"']?body=")
# `--input`은 임의 JSON을 보내므로 본문이 들어 있어도 길이를 잴 수 없다.
API_INPUT_FLAG = re.compile(r"(?:^|\s)--input[=\s]")
# 코멘트 엔드포인트만 면제한다. 문자열 어디든 `comments`가 있으면 면제하면
# `-f body="$(cat docs/comments.md)"` 같은 경로 이름으로 우회된다.
API_COMMENTS_ENDPOINT = re.compile(r"issues/\d+/comments")
# 본문 파일 플래그를 찾을 구간을 정하는 호출 패턴.
GH_INVOCATION = r"(?:issue[ \t]+(?:create|edit)|api)\b"
# 명령 앞머리의 `NAME=value`. 실측상 본문 경로에 쓰인 셸 변수 213건 중 206건이
# 같은 명령 안에서 이렇게 할당된다.
ASSIGNMENT = re.compile(r"(?:^|[\n;&|(])[ \t]*(\w+)=(\"[^\"]*\"|'[^']*'|[^\s;&|]*)")
VAR_REFERENCE = re.compile(r"\$\{(\w+)\}|\$(\w+)")
# heredoc 여는 줄이 이슈 본문을 담는다는 신호
BODY_HEREDOC_OPENER = re.compile(r"--body|-b[ =]|gh[ \t]+issue[ \t]+(?:create|edit)")

ISSUE_REQUESTED = re.compile(r"이슈|issue|남겨|등록해|백로그|backlog", re.I)


class Deny(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def detect_actions(cmd_exec):
    """명령 하나에 여러 호출이 섞일 수 있으므로(`&&` 체인) 전부 모은다."""
    return {action
            for action, pattern in (("create", r"issue[ \t]+create\b"),
                                    ("edit", r"issue[ \t]+edit\b"),
                                    ("api", r"api\b"))
            if re.search(COMMAND_POSITION + pattern, cmd_exec)}


def expand_vars(text, env):
    """아는 변수만 치환한다. 모르는 것은 그대로 둬서 해석 실패로 드러나게 한다."""
    return VAR_REFERENCE.sub(
        lambda m: env.get(m.group(1) or m.group(2), m.group(0)), text)


def shell_assignments(cmd_exec):
    env = {}
    for m in ASSIGNMENT.finditer(cmd_exec):
        env[m.group(1)] = expand_vars(m.group(2).strip("\"'"), env)
    return env


def resolve_path(raw, cwd, env):
    """본문 파일 경로를 실제로 열 수 있는 형태로 바꾼다. 못 하면 None."""
    path = os.path.expanduser(expand_vars(raw, env))
    if "$" in path:
        return None
    if os.path.isabs(path):
        return path
    return os.path.join(cwd, path) if cwd else None


def limit_for(body):
    return PARLEY_LIMIT if PARLEY_HEADING in body else BODY_LIMIT


def check_length(body):
    limit = limit_for(body)
    if not body or len(body) <= limit:
        return
    raise Deny(
        f"이슈 본문이 {len(body)}자로 상한 {limit}자를 넘습니다. 본문이 길수록 "
        "코드와 어긋나는 문장이 늘고 머지율이 떨어집니다(길이를 줄이면 단위당 +9%).\n"
        "\n"
        "넘친 내용은 대개 아래 중 하나입니다 — 옮겨 적을 곳을 함께 적었습니다.\n"
        "  시점 실측(N줄, N토큰, permalink) → 재실행 명령(`wc -l <path>`)으로 대체\n"
        "  확정된 결정과 그 근거            → ADR. 이슈는 그 경로만 가리킵니다\n"
        "  환경과 아키텍처 배경             → CLAUDE.md 또는 AGENTS.md\n"
        "  진행 상황                       → 적지 않음. 상태는 라벨에서 읽습니다\n"
        "\n"
        f"아직 안 정한 것은 빼지 말고 `{PARLEY_HEADING}` 블록에 남기세요 — "
        f"그 블록이 있는 이슈는 상한이 {PARLEY_LIMIT}자입니다.\n"
        "\n" + SKILL_REF)


def check_why_block(body, actions, warnings):
    """`## 왜`가 없으면 제목만 되풀이한 본문이 통과한다.

    create는 막고 edit은 경고만 한다 — edit은 옛 규격으로 열린 이슈를 고치는
    경로라, 막으면 정리 자체를 못 한다.
    """
    if not body or WHY_HEADING in body:
        return
    message = (
        f"이슈 본문에 `{WHY_HEADING}` 블록이 없습니다. 무엇이 안 되는지는 제목이 "
        "이미 갖고 있어, 그것만 되풀이한 본문으로는 착수 세션이 손해를 재지 "
        "못합니다.\n"
        "\n"
        f"`{WHY_HEADING}`에는 무엇이 안 되고(현상), 왜 그렇고(원인), 그래서 무엇이 "
        "막히는지(손해)를 씁니다.\n"
        "\n" + SKILL_REF)
    if "create" in actions:
        raise Deny(message)
    warnings.append(message)


def check_api_bypass(cmd_exec):
    """gh issue를 거치지 않고 본문을 쓰는 경로. 길이를 재는 대신 경로 자체를 막는다.

    조회와 라벨 목적 호출은 body 필드가 없어 걸리지 않고, 코멘트는 길이 규격 대상이 아니다.
    """
    if API_COMMENTS_ENDPOINT.search(cmd_exec) or "issues" not in cmd_exec:
        return
    if not (API_BODY_FIELD.search(cmd_exec) or API_INPUT_FLAG.search(cmd_exec)):
        return
    raise Deny(
        "`gh api`로 이슈 본문을 쓰면 본문 길이와 블록 구성이 검사되지 않습니다.\n"
        "\n"
        "`gh issue create --body-file <path>` 또는 `gh issue edit <N> --body-file <path>`로 쓰세요.\n"
        "\n" + SKILL_REF)


def collect_bodies(cmd_exec, heredocs, cwd, warnings):
    """명령이 이슈 본문으로 넘기는 문자열을 전부 모은다.

    한 명령에 여러 호출이 섞일 수 있어(`&&` 체인) 하나만 모으면 나머지가 검사를
    통과한다. 제목도 같은 플래그 형태로 넘어와 섞이는데, 걸러내지 않고 그대로 모은다
    — 부르는 쪽이 길이는 전부 재고 블록 구성은 가장 긴 것만 본다.

    읽지 못한 본문은 warnings에 남긴다. 단 읽을 방법이 아예 없는 경로는 Deny다.
    """
    # --body-file <path> / --body-file=<path> / -F 단축형 모두 받는다.
    body_files = [m.group(1).strip("\"'")
                  for segment in segments(cmd_exec, GH_INVOCATION)
                  for m in BODY_FILE_FLAG.finditer(segment)]
    env = shell_assignments(cmd_exec)
    bodies = []

    for raw in body_files:
        if raw == "-":
            # 표준입력으로 넘긴 본문은 hook이 읽을 수 없어 검사할 방법이 없다.
            raise Deny(
                "본문을 표준입력(`--body-file -`)으로 넘기면 길이와 블록 구성을 "
                "검사할 수 없습니다.\n"
                "\n"
                "본문을 파일로 쓰고 `--body-file <path>`로 넘기세요.\n"
                "\n" + SKILL_REF)
        path = resolve_path(raw, cwd, env)
        try:
            with open(path, encoding="utf-8") as f:
                bodies.append(f.read())
            continue
        except (OSError, TypeError):
            pass
        # hook은 명령 실행 전에 돈다. 같은 명령이 만들 파일은 아직 없는 게 정상이고,
        # 그 본문은 아래 heredoc에서 모은다. 그게 아니면 못 읽었다는 사실을 알린다.
        if not any(raw in opener for opener, _ in heredocs):
            warnings.append(
                f"본문 파일 `{raw}`를 열지 못해 길이를 검사하지 못했습니다.")

    # 이슈 본문과 무관한 heredoc(다른 파일 작성 등)을 모으지 않도록, 여는 줄이 본문
    # 플래그거나 위에서 찾은 body-file 경로로 리다이렉트할 때만 모은다.
    for opener, body in heredocs:
        if BODY_HEREDOC_OPENER.search(opener) or any(p in opener for p in body_files):
            bodies.append(body)

    for m in INLINE_BODY_FLAG.finditer(cmd_exec):
        bodies.append(m.group(1) or m.group(2))

    return bodies


def check_bodies(cmd_exec, heredocs, cwd, actions, warnings):
    bodies = collect_bodies(cmd_exec, heredocs, cwd, warnings)
    # 전부 잰다 — 첫 하나만 재면 `&&` 체인 뒤쪽 본문이 통과한다.
    for body in bodies:
        check_length(body)
    if bodies:
        # 제목이 섞여 있어도 본문보다 짧다. 가장 긴 것 하나만 블록 구성을 본다 —
        # 제목에 `## 왜`를 요구하지 않는다.
        check_why_block(max(bodies, key=len), actions, warnings)


def last_user_message(transcript_path):
    """마지막 실제 사용자 발화.

    content가 문자열인 것만 — 배열은 tool_result다. isMeta는 슬래시 커맨드 caveat나
    훅 주입 컨텍스트라 실제 발화가 아니다.
    """
    if not transcript_path:
        return None
    last = None
    try:
        with open(transcript_path, encoding="utf-8") as f:
            for line in f:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("type") != "user" or event.get("isMeta"):
                    continue
                content = event.get("message", {}).get("content")
                if isinstance(content, str):
                    last = content
    except OSError:
        return None
    return last


def judge(payload):
    """hook 출력 dict를 돌려준다. 낼 것이 없으면 None."""
    command = payload.get("tool_input", {}).get("command", "")
    cmd_exec, heredocs = split_heredocs(command)
    actions = detect_actions(cmd_exec)
    if not actions:
        return None

    warnings = []
    try:
        # 한 명령에 gh api와 gh issue가 함께 있어도 둘 다 검사한다 —
        # 앞의 issue 호출만 보고 넘기면 뒤의 api 우회가 통과한다.
        if "api" in actions:
            check_api_bypass(cmd_exec)
        if actions & {"create", "edit"}:
            check_bodies(cmd_exec, heredocs, payload.get("cwd", ""), actions, warnings)
    except Deny as d:
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": d.reason,
        }}

    if "create" in actions:
        last = last_user_message(payload.get("transcript_path", ""))
        if last and not ISSUE_REQUESTED.search(last):
            warnings.append(
                "직전 발화에 이슈 요청이 없습니다. 지금 세션에서 끝낼 일이면 커밋 "
                "메시지가 기록이고, 이슈는 다음 세션에 넘길 것만 만듭니다.")

    if not warnings:
        return None
    return {
        "systemMessage": "\n".join(warnings),
        "hookSpecificOutput": {"hookEventName": "PreToolUse"},
    }


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

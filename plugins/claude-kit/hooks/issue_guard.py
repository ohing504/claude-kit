#!/usr/bin/env python3
"""gh issue create / edit 가드의 판정부.

산문 규약은 이슈 생성을 못 막는다는 실측이 근거다 — 한 저장소에서 생성 139건 중
72%가 사용자 요청 없이 만들어졌고, 사용자가 "이슈 계속 새로 만들지 말라"고 쓴
바로 그 메시지에서도 생성됐다. 같은 저장소가 만든 이슈의 29%를 나중에 삭제했다.

두 축으로 나눈다:
  길이 초과      → deny.  기계 판정이라 오탐이 없다. create와 edit 둘 다 잰다 —
                          create만 재면 edit --body-file로 상한을 우회한다.
  사용자 미요청  → 경고.  판정이 부정확해 차단하면 정당한 생성까지 막힌다.
                          create에만. edit은 기존 이슈 정리라 요청 발화가 없는 게 정상이다.

호출은 issue-guard.sh가 한다. 그쪽은 대상 문자열 유무만 보고 여기로 넘긴다.
"""
import json
import os
import re
import sys

# 4블록(무엇을/완료 조건/시작 지점/하지 말 것)이면 충분한 상한.
# 붕괴한 저장소 본문 중앙값 1,957자, 정상 운영 저장소 880~1,061자.
BODY_LIMIT = 1200

SKILL_REF = "작성 규격은 /git-issue 스킬."

# `<<<`(here-string)는 heredoc이 아니다. 앞에 `<`가 더 있으면 여는 줄로 보지 않는다 —
# 오인하면 뒤따르는 줄이 전부 본문으로 먹혀 그 줄의 gh 호출이 판정에서 빠진다.
HEREDOC_OPEN = re.compile(r"(?<!<)<<(-?)(['\"]?)([A-Za-z_]\w*)\2")

# gh가 명령 위치(줄 시작, `;` `&&` `||` `|` `(` `{` `$(` 백틱 뒤)에 올 때만 호출로 본다.
# 부분일치로 판정하면 이 문자열을 언급만 하는 명령(커밋 메시지, grep, 문서 편집)이 걸린다.
# 명령 앞에 붙는 실행 래퍼(`env FOO=1`, `time`, `sudo`)와 변수 할당은 건너뛴다.
COMMAND_POSITION = (r"(?:^|[\n;&|(){`]|\$\()[ \t]*"
                    r"(?:(?:sudo|env|command|nohup|time|timeout)[ \t]+)*"
                    r"(?:\w+=\S*[ \t]+)*gh[ \t]+")

BODY_FILE_FLAG = re.compile(r"(?:--body-file|(?:^|\s)-F)[=\s]\s*(\S+)")
INLINE_BODY_FLAG = re.compile(
    r"(?:--body|(?:^|\s)-b)[= ](?:\"((?:[^\"\\]|\\.)*)\"|'([^']*)')", re.S)
API_BODY_FIELD = re.compile(r"(?:-f|-F|--field|--raw-field)[= ]+[\"']?body=")
# `--input`은 임의 JSON을 보내므로 본문이 들어 있어도 길이를 잴 수 없다.
API_INPUT_FLAG = re.compile(r"(?:^|\s)--input[=\s]")
# 코멘트 엔드포인트만 면제한다. 문자열 어디든 `comments`가 있으면 면제하면
# `-f body="$(cat docs/comments.md)"` 같은 경로 이름으로 우회된다.
API_COMMENTS_ENDPOINT = re.compile(r"issues/\d+/comments")
# gh 호출 하나가 끝나는 지점. 본문 파일 플래그는 이 구간 안에서만 찾는다 —
# 명령 전체에서 찾으면 체인에 섞인 `curl -F`의 값을 본문 경로로 읽는다.
SEGMENT_END = re.compile(r";|&&|\|\||\n|\|(?!\|)")
GH_INVOCATION = re.compile(COMMAND_POSITION + r"(?:issue[ \t]+(?:create|edit)|api)\b")
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


def split_heredocs(command):
    """명령을 (실행되는 부분, [(여는 줄, 본문), ...])으로 나눈다.

    명령 문자열에는 실행되는 명령과 데이터가 섞여 있다. heredoc 본문은 실행되는
    부분이 아니므로 판정에서 뺀다 — 이 hook을 설명하는 커밋 메시지가 자기 자신에게
    차단되는 일이 실제로 있었다. 플래그는 항상 본문 밖에 있으므로 본문 추출도
    실행되는 부분으로 한다.

    한 줄에 여러 개가 열릴 수 있다(`cmd <<A <<B`). 첫 하나만 추적하면 나머지 본문이
    실행부에 남아 길이를 재지 못한다. 여는 순서대로 대기열에 넣고 차례로 닫는다.
    """
    exec_lines, heredocs, pending = [], [], []
    current, body = None, None
    for line in command.split("\n"):
        if current is not None:
            tag, indented, opener = current
            if (line.lstrip("\t ") if indented else line) == tag:
                heredocs.append((opener, "\n".join(body)))
                current, body = (pending.pop(0), []) if pending else (None, None)
                continue
            body.append(line)
            continue
        exec_lines.append(line)
        opened = [(m.group(3), m.group(1) == "-", line)
                  for m in HEREDOC_OPEN.finditer(line)]
        if opened:
            pending.extend(opened)
            current, body = pending.pop(0), []
    if current is not None:  # 닫히지 않은 채 끝났다
        heredocs.append((current[2], "\n".join(body)))
    return "\n".join(exec_lines), heredocs


def detect_actions(cmd_exec):
    """명령 하나에 여러 호출이 섞일 수 있으므로(`&&` 체인) 전부 모은다."""
    return {action
            for action, pattern in (("create", r"issue[ \t]+create\b"),
                                    ("edit", r"issue[ \t]+edit\b"),
                                    ("api", r"api\b"))
            if re.search(COMMAND_POSITION + pattern, cmd_exec)}


def gh_segments(cmd_exec):
    """gh 호출마다 그 호출이 끝나는 지점까지의 구간을 돌려준다."""
    segments = []
    for m in GH_INVOCATION.finditer(cmd_exec):
        rest = cmd_exec[m.end():]
        end = SEGMENT_END.search(rest)
        segments.append(rest[:end.start()] if end else rest)
    return segments


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


def check_length(body):
    if not body or len(body) <= BODY_LIMIT:
        return
    raise Deny(
        f"이슈 본문이 {len(body)}자로 상한 {BODY_LIMIT}자를 넘습니다. 본문이 길수록 "
        "낡을 면적이 커지고 머지율이 떨어집니다(길이를 줄이면 단위당 +9%).\n"
        "\n"
        "넘친 내용은 대개 이 넷 중 하나입니다 — 다음 자리로 보내세요.\n"
        "  시점 실측(N줄, N토큰, permalink) → 재실행 명령(`wc -l <path>`)으로 대체\n"
        "  미결과 결정                     → ADR. 완료 조건 첫 칸을 '결정하고 ADR에 남긴다'로\n"
        "  환경과 아키텍처 배경             → CLAUDE.md 또는 AGENTS.md\n"
        "  진행 상황                       → 적지 않음. 상태는 라벨에서 읽습니다\n"
        "\n" + SKILL_REF)


def check_api_bypass(cmd_exec):
    """gh issue를 거치지 않고 본문을 쓰는 경로. 길이를 재는 대신 경로 자체를 막는다.

    조회와 라벨 목적 호출은 body 필드가 없어 걸리지 않고, 코멘트는 길이 규격 대상이 아니다.
    """
    if API_COMMENTS_ENDPOINT.search(cmd_exec) or "issues" not in cmd_exec:
        return
    if not (API_BODY_FIELD.search(cmd_exec) or API_INPUT_FLAG.search(cmd_exec)):
        return
    raise Deny(
        f"`gh api`로 이슈 본문을 쓰면 본문 길이 규격({BODY_LIMIT}자)이 검사되지 않습니다.\n"
        "\n"
        "`gh issue create --body-file <path>` 또는 `gh issue edit <N> --body-file <path>`로 쓰세요.\n"
        "\n" + SKILL_REF)


def check_bodies(cmd_exec, heredocs, cwd, warnings):
    # --body-file <path> / --body-file=<path> / -F 단축형 모두 받는다.
    # 한 명령에 여러 번 나오면(`&&` 체인) 전부 잰다 — 마지막 하나만 재면 앞의 것이 통과한다.
    body_files = [m.group(1).strip("\"'")
                  for segment in gh_segments(cmd_exec)
                  for m in BODY_FILE_FLAG.finditer(segment)]
    env = shell_assignments(cmd_exec)
    for raw in body_files:
        if raw == "-":
            # 표준입력으로 넘긴 본문은 hook이 읽을 수 없어 길이를 잴 방법이 없다.
            raise Deny(
                f"본문을 표준입력(`--body-file -`)으로 넘기면 길이 규격({BODY_LIMIT}자)을 "
                "검사할 수 없습니다.\n"
                "\n"
                "본문을 파일로 쓰고 `--body-file <path>`로 넘기세요.\n"
                "\n" + SKILL_REF)
        path = resolve_path(raw, cwd, env)
        try:
            with open(path, encoding="utf-8") as f:
                check_length(f.read())
            continue
        except (OSError, TypeError):
            pass
        # hook은 명령 실행 전에 돈다. 같은 명령이 만들 파일은 아직 없는 게 정상이고,
        # 그 본문은 아래 heredoc 경로로 잰다. 그게 아니면 잴 수 없었다는 사실을 알린다.
        if not any(raw in opener for opener, _ in heredocs):
            warnings.append(
                f"본문 파일 `{raw}`를 열지 못해 길이를 검사하지 못했습니다.")

    # 이슈 본문과 무관한 heredoc(다른 파일 작성 등)을 재지 않도록, 여는 줄이 본문
    # 플래그거나 위에서 찾은 body-file 경로로 리다이렉트할 때만 잰다.
    for opener, body in heredocs:
        if BODY_HEREDOC_OPENER.search(opener) or any(p in opener for p in body_files):
            check_length(body)

    # body-file과 같은 이유로 전부 잰다 — 첫 하나만 재면 체인 뒤쪽 본문이 통과한다.
    for m in INLINE_BODY_FLAG.finditer(cmd_exec):
        check_length(m.group(1) or m.group(2))


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
            check_bodies(cmd_exec, heredocs, payload.get("cwd", ""), warnings)
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

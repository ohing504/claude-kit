#!/usr/bin/env python3
"""gh 호출 가드가 공유하는 셸 명령 파싱.

명령 문자열에는 실행되는 명령과 데이터(heredoc 본문, 커밋 메시지 인용)가 섞여 있다.
부분일치로 판정하면 그 명령을 언급만 하는 명령이 걸린다 — 두 가드 모두에서 자기 자신을
설명하는 커밋 메시지가 차단되는 일이 실제로 있었다.
"""
import re

# `<<<`(here-string)는 heredoc이 아니다. 앞에 `<`가 더 있으면 여는 줄로 보지 않는다 —
# 오인하면 뒤따르는 줄이 전부 본문으로 먹혀 그 줄의 gh 호출이 판정에서 빠진다.
HEREDOC_OPEN = re.compile(r"(?<!<)<<(-?)(['\"]?)([A-Za-z_]\w*)\2")

# gh가 명령 위치(줄 시작, `;` `&&` `||` `|` `(` `{` `$(` 백틱 뒤)에 올 때만 호출로 본다.
# 명령 앞에 붙는 실행 래퍼(`env FOO=1`, `time`, `sudo`)와 변수 할당은 건너뛴다.
COMMAND_POSITION = (r"(?:^|[\n;&|(){`]|\$\()[ \t]*"
                    r"(?:(?:sudo|env|command|nohup|time|timeout)[ \t]+)*"
                    r"(?:\w+=\S*[ \t]+)*gh[ \t]+")

# gh 호출 하나가 끝나는 지점. 플래그는 이 구간 안에서만 찾는다 — 명령 전체에서 찾으면
# 체인에 섞인 다른 명령의 플래그(`git push -d`)를 gh의 것으로 읽는다.
SEGMENT_END = re.compile(r";|&&|\|\||\n|\|(?!\|)")


def split_heredocs(command):
    """명령을 (실행되는 부분, [(여는 줄, 본문), ...])으로 나눈다.

    heredoc 본문은 실행되는 부분이 아니므로 판정에서 뺀다. 플래그는 항상 본문 밖에
    있으므로 플래그 검사도 실행되는 부분으로 한다.

    한 줄에 여러 개가 열릴 수 있다(`cmd <<A <<B`). 첫 하나만 추적하면 나머지 본문이
    실행부에 남는다. 여는 순서대로 대기열에 넣고 차례로 닫는다.
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


def segments(cmd_exec, pattern):
    """`pattern`에 맞는 gh 호출마다 그 호출이 끝나는 지점까지의 구간을 돌려준다."""
    found = []
    for m in re.finditer(COMMAND_POSITION + pattern, cmd_exec):
        rest = cmd_exec[m.end():]
        end = SEGMENT_END.search(rest)
        found.append(rest[:end.start()] if end else rest)
    return found

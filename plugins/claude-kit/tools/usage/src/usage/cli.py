"""세션 하나를 재거나 코퍼스 전체를 데이터베이스에 적재하거나 코퍼스에서 잔존 비용 순위를 뽑는다."""

import argparse
import json
import re
import sqlite3
import sys
import unicodedata
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from typing import Any

from usage.corpus import BY_CHOICES, CheckResult, check, report
from usage.index import index_corpus
from usage.quota import Attribution, attribute_interval, run_collect
from usage.session import Session, Totals, find_transcript, read_session


def _width(s: str) -> int:
    """한글은 한 글자가 두 칸을 차지한다 — 글자 수로 채우면 열이 어긋난다."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _cut(s: str, width: int) -> str:
    out = ""
    used = 0
    for c in s:
        w = _width(c)
        if used + w > width:
            break
        out += c
        used += w
    return out


def _pad(s: str, width: int, right: bool = False) -> str:
    fill = " " * max(width - _width(s), 0)
    return fill + s if right else s + fill


def _n(v: int) -> str:
    if v >= 1_000_000:
        return f"{v / 1_000_000:.2f}M"
    if v >= 1_000:
        return f"{v / 1_000:.1f}k"
    return str(v)


def _out(t: Totals) -> str:
    """못 믿는 `output`에 물음표를 단다. 이 값으로 전후를 대조하면 결론이 통째로 틀린다."""
    return _n(t.output) + ("" if t.output_reliable else "?")


def _images(t: Totals) -> str:
    """서브에이전트 행에 붙는 이미지 값. 사진을 안 연 에이전트는 빈 칸으로 둔다.

    서브에이전트 블록에는 머리글 줄이 없어 열 이름을 셀 수 없다 — 단위를 값에 달아 그 자리만
    보고 읽히게 하고, 단위가 붙은 다른 열(`분`)과 같은 오른쪽 끝에 붙인다.
    """
    return f"{t.images}장 {_n(t.image_tokens)}" if t.images else ""


def _prompt(t: Totals) -> str:
    """첫 요청에 실린 컨텍스트. 그 에이전트가 무엇을 얼마나 받고 시작했는지가 이 값이다."""
    return _n(t.requests[0].context) if t.requests else ""


def _model(t: Totals) -> str:
    """가장 많이 쓴 모델 하나. `claude-` 접두는 어느 행에나 같아 자리만 차지한다."""
    if not t.models:
        return ""
    name = max(t.models.items(), key=lambda kv: kv[1])[0]
    return name.removeprefix("claude-")


def _row(label: str, t: Totals) -> str:
    ttl = f"{_n(t.cache_write)} ({_n(t.cache_write_5m)}/{_n(t.cache_write_1h)})"
    return (
        f"{_pad(label, 16)} {_pad(str(t.calls), 6, right=True)}"
        f" {_pad(_n(t.cache_read), 10, right=True)} {_pad(ttl, 22, right=True)}"
        f" {_pad(_out(t), 9, right=True)} {_pad(_n(t.thinking), 13, right=True)}"
        f" {_pad(_n(t.produced_chars), 8, right=True)} {_pad(_n(t.input), 8, right=True)}"
    )


def _top(counts: dict[str, int], limit: int = 8) -> str:
    items = sorted(counts.items(), key=lambda kv: -kv[1])[:limit]
    return ", ".join(f"{k} {v}" for k, v in items) or "없음"


def _report(s: Session) -> str:
    lines = [
        f"세션 {s.session_id} — {s.main.minutes:.1f}분"
        f" (모델 {s.main.model_minutes:.1f}분, 도구 {s.main.tool_minutes:.1f}분,"
        f" 위임 {s.main.delegated_minutes:.1f}분, 사용자 대기 {s.idle_minutes:.1f}분)",
        f"경로 {s.path}",
        "",
        f"{'':<16} {_pad('호출', 6, right=True)} {_pad('cache read', 10, right=True)}"
        f" {_pad('cache write (5m/1h)', 22, right=True)} {_pad('output', 9, right=True)}"
        f" {_pad('그중 thinking', 13, right=True)} {_pad('낸 글자', 8, right=True)}"
        f" {_pad('input', 8, right=True)}",
        _row("메인", s.main),
    ]
    if s.agents:
        lines.append(_row(f"서브 {len(s.agents)}개", _agents_total(s)))
        lines.append(_row("합계", s.combined))
        lines += ["", "서브에이전트"]
        for a in s.agents:
            order = f"{a.order:>2}" if a.order else " ?"
            kind = a.kind.split(":")[-1]
            lines.append(
                f" {order}  {_pad(kind, 20)} {_pad(_cut(a.label, 14), 14)}"
                f" {_pad(_prompt(a.totals), 8, right=True)} {_pad(_model(a.totals), 9)}"
                f" {_pad(str(a.totals.calls), 4, right=True)}"
                f" {_pad(_n(a.totals.cache_read), 8, right=True)}"
                f" {_pad(_n(a.totals.cache_write), 8, right=True)}"
                f" {_pad(_out(a.totals), 7, right=True)}"
                f" {_pad(_n(a.totals.thinking), 7, right=True)}"
                f" {_pad(_n(a.totals.produced_chars), 7, right=True)}"
                f" {_pad(_images(a.totals), 11, right=True)}"
                f" {a.totals.working_minutes:>6.1f}분"
                f" (+대기 {a.totals.idle_minutes:.1f}분)  {_top(a.totals.tools, 4)}"
            )
    lines += [
        "",
        f"모델 (메인)  {_top(s.main.models)}",
        f"도구 (메인)  {_top(s.main.tools)}",
        f"도구 결과 (메인)  {_chars(s.main.result_chars)}",
    ]
    b = s.main.bash
    if b.total:
        lines.append(
            f"Bash 잇기 (메인)  단독 {b.single}, `;` {b.joined_semicolon}, `&&` {b.joined_and}"
            f" / 이은 호출의 구획 마커 {b.marked}/{b.joined}"
            f" ({b.marked * 100 // b.joined if b.joined else 0}%)"
        )
    f = s.main.tools_per_request
    if f.calling:
        lines.append(
            "도구 담기 (메인)  요청당 "
            + ", ".join(f"{size}개 {n}" for size, n in f.spread.items())
            + f" / 둘 이상 담은 요청 {f.joined}/{f.calling}"
            f" ({f.joined * 100 // f.calling}%)"
        )
    if s.combined.images:
        lines.append(
            f"이미지  {s.combined.images}장 {_n(s.combined.image_tokens)} 토큰"
            f" (메인 {s.main.images}장 {_n(s.main.image_tokens)})"
        )
    again = sorted(
        ((p, n) for p, n in s.main.file_reads.items() if n > 1), key=lambda kv: (-kv[1], kv[0])
    )
    if again:
        lines += ["", f"두 번 이상 연 파일 (메인)  {len(again)}개"]
        for path, n in again[:15]:
            lines.append(f" {n:>3}회  {path}")
    lines += ["", _curve(s)]
    if s.main.slow_calls:
        lines += ["", "1분 넘게 돈 도구 호출 (메인)"]
        for c in s.main.slow_calls[:10]:
            lines.append(f" {c.minutes:>5.1f}분  {_pad(c.name, 8)} {_cut(c.detail, 90)}")
    if s.combined.stale_requests:
        lines += [
            "",
            f"경고  output_tokens가 낸 글자와 어긋난 응답 {s.combined.stale_requests}개."
            " `?`가 붙은 값은 그만큼 실제보다 작다",
        ]
    if s.missing:
        lines += [
            "",
            f"경고  띄운 서브에이전트 {', '.join(s.missing)}의 transcript를 찾지 못했다."
            " 그만큼 합계에서 빠져 있다",
        ]
    return "\n".join(lines)


def _marks_report(s: Session) -> str:
    """단계 경계 후보. 이 번호를 `--from`과 `--until`에 그대로 넣는다."""
    lines = [f"세션 {s.session_id} — 경계 후보 {len(s.marks)}개", ""]
    for m in s.marks:
        lines.append(f" {m.order:>4}  {_pad(m.name, 6)} {_cut(m.detail, 90)}")
    return "\n".join(lines)


def _chars(counts: dict[str, int]) -> str:
    items = sorted(counts.items(), key=lambda kv: -kv[1])[:8]
    return ", ".join(f"{k} {_n(v)}자" for k, v in items) or "없음"


def _curve(s: Session) -> str:
    """요청 순서별 컨텍스트. 어디서 커졌고 어디서 압축이 버렸는지가 이 줄에서만 보인다."""
    reqs = s.main.requests
    if not reqs:
        return "컨텍스트  요청 없음"
    top = max(r.context for r in reqs) or 1
    marks = set(s.compaction_at)
    bar = "".join(
        "!" if r.order in marks else "▁▂▃▄▅▆▇█"[min(7, r.context * 8 // top)] for r in reqs
    )
    head = f"컨텍스트  최대 {_n(top)} (요청 {len(reqs)}개)"
    if marks:
        head += f", 압축 {', '.join(str(o) + '번째' for o in s.compaction_at)}"
    lines = [head, bar]
    spawns = [r.order for r in reqs if "Agent" in r.tools]
    if spawns:
        lines.append(f"위임한 요청  {', '.join(str(o) for o in spawns)}번째")
    return "\n".join(lines)


def _agents_total(s: Session) -> Totals:
    c, m = s.combined, s.main
    return Totals(
        calls=c.calls - m.calls,
        input=c.input - m.input,
        output=c.output - m.output,
        produced_chars=c.produced_chars - m.produced_chars,
        stale_requests=c.stale_requests - m.stale_requests,
        thinking=c.thinking - m.thinking,
        cache_read=c.cache_read - m.cache_read,
        cache_write=c.cache_write - m.cache_write,
        cache_write_5m=c.cache_write_5m - m.cache_write_5m,
        cache_write_1h=c.cache_write_1h - m.cache_write_1h,
        images=c.images - m.images,
        image_tokens=c.image_tokens - m.image_tokens,
    )


# `tool_spans`는 `datetime` 쌍이라 `json.dumps`가 막힌다. `tool_calls`는 인덱스가 행을 만들 때
# 쓰는 호출 단위 목록이라 한 세션의 JSON에 실으면 출력이 배로 커지고 읽을 것이 묻힌다.
_NOT_IN_JSON = {"tool_spans", "tool_calls"}


def _serializable(items: list[tuple[str, object]]) -> dict[str, object]:
    """JSON으로 낼 수 없는 값과 이 출력이 담지 않는 중간값을 뺀 dict."""
    return {k: v for k, v in items if k not in _NOT_IN_JSON}


# 웹 검색, 페이지 읽기처럼 세션 기록(jsonl)에 남지 않는 소비가 있다 — `usage`가 내는 모든
# 수치에는 이 경계가 붙는다. 청구 총액과 대조하면 어긋나고, 그것은 결함이 아니라 자료의 한계다.
_MEASURED = (
    "이 값은 세션 기록(~/.claude/projects/**/*.jsonl)에 남은 것만 잰다."
    " 웹 검색, 페이지 읽기 같은 내부 경로의 소비는 기록에 남지 않아 여기 포함되지 않는다."
)


def _summary_line(s: dict[str, Any]) -> str:
    pct = s["compaction_ratio"] * 100
    return (
        f"요약  세션 {s['sessions']}개(압축 {s['sessions_with_compaction']}개, {pct:.1f}%),"
        f" 스코프 {s['scopes']}개, 요청 {_n(int(s['requests']))}개"
    )


# 인덱스는 저장소 안에 두지 않는다 — 세션 기록에는 실제 파일 경로와 작업 내용이 들어간다.
_DEFAULT_DB = Path.home() / ".claude" / "usage-index.db"
_DEFAULT_ROOT = Path.home() / ".claude" / "projects"
# 코퍼스 인덱스와 다른 파일에 둔다 — 인덱스는 세션 파일에서 다시 만들 수 있는 캐시지만, 한도
# 표본은 그 시각이 지나면 영영 다시 만들 수 없다.
_DEFAULT_QUOTA_DB = Path.home() / ".claude" / "usage-quota.db"


def _add_db(p: argparse.ArgumentParser) -> None:
    p.add_argument("--db", default=str(_DEFAULT_DB), help=f"데이터베이스 파일 (기본 {_DEFAULT_DB})")


def _add_index(p: argparse.ArgumentParser) -> None:
    _add_db(p)
    p.add_argument(
        "--root", default=str(_DEFAULT_ROOT), help=f"세션 파일이 든 폴더 (기본 {_DEFAULT_ROOT})"
    )


def _add_corpus(p: argparse.ArgumentParser) -> None:
    _add_db(p)
    p.add_argument(
        "--by", choices=BY_CHOICES, help="이 축으로 접어 순위를 낸다. 없으면 축마다 요약을 낸다"
    )
    p.add_argument(
        "--top", type=int, default=20, metavar="N", help="축마다 상위 N개만 낸다 (기본 20)"
    )
    p.add_argument("--since", metavar="YYYY-MM-DD", help="이 날짜의 세션부터 센다")
    p.add_argument("--until", metavar="YYYY-MM-DD", help="이 날짜의 세션까지만 센다")
    p.add_argument("--project", metavar="슬러그", help="이 프로젝트의 세션만 센다")
    p.add_argument(
        "--group-by",
        choices=("first-skill", "agent-kind", "project"),
        help="--by spread와 함께 쓴다. 기본 project",
    )
    p.add_argument("--table", action="store_true", help="사람이 읽을 표로 낸다")
    p.add_argument(
        "--check",
        action="store_true",
        help="항등식 위반을 찾는다. 위반이 있으면 종료 코드가 0이 아니다",
    )


def _check_dict(r: CheckResult) -> dict[str, object]:
    return {
        "measured": _MEASURED,
        "ok": r.ok,
        "scopes": r.scopes,
        "eviction_events": r.eviction_events,
        "unattributed_residual": r.unattributed_residual,
        "total_residual": r.total_residual,
        "thinking_residual_as_kept": r.thinking_residual_as_kept,
        "thinking_residual_as_stripped": r.thinking_residual_as_stripped,
        "violations": r.violations,
    }


def _check_report(r: CheckResult) -> str:
    lines = [
        _MEASURED,
        f"스코프 {r.scopes}개, 위반 {len(r.violations)}건",
        f"잔존 총합 {_n(r.total_residual)}, 퇴장 {r.eviction_events}건,"
        f" unattributed {_n(r.unattributed_residual)}",
        f"thinking 가설 오차  남는다 {_n(r.thinking_residual_as_kept)},"
        f" 벗겨진다 {_n(r.thinking_residual_as_stripped)} (작은 쪽이 맞는 가설)",
    ]
    for v in r.violations:
        scope = f"{v['session_id']}" + (f"/{v['agent_id']}" if v["agent_id"] else "")
        lines.append(f"  {scope}: expected={v['expected']} got={v['got']}")
    return "\n".join(lines)


def _corpus_row(row: dict[str, Any]) -> str:
    if "kind" in row:  # --by agent
        return (
            f"{_pad(str(row['kind']), 24)} {_pad(_n(int(row['paid_by_parent'])), 10, True)}"
            f" {_pad(_n(int(row['spent_by_self'])), 10, True)} calls={row['calls']} scopes={row['scopes']}"
        )
    if "mean" in row:  # --by spread
        example = row.get("example")
        where = f"{example['session_id']}#{example['order']}" if example else ""
        return (
            f"{_pad(str(row['key']), 24)} {_pad(_n(int(row['residual'])), 10, True)}"
            f" scopes={row['scopes']} mean={row['mean']:.0f} min={row['min']:.0f}"
            f" median={row['median']:.0f} p95={row['p95']:.0f} max={row['max']:.0f} {where}"
        )
    example = row.get("example")
    where = f"{example['session_id']}#{example['order']}" if example else ""
    return (
        f"{_pad(str(row['key']), 24)} {_pad(_n(int(row['residual'])), 10, True)}"
        f" size={_n(int(row['size']))} count={row['count']} sessions={row['sessions']} {where}"
    )


def _corpus_report(data: dict[str, object]) -> str:
    lines = [_MEASURED]
    summary_row = data.get("summary")
    if isinstance(summary_row, dict):
        lines.append(_summary_line(summary_row))
    for axis, rows in data.items():
        if not isinstance(rows, list):
            continue
        lines.append(f"== {axis} ==")
        lines.extend(_corpus_row(row) for row in rows)
    return "\n".join(lines)


# 세션 기록(jsonl)과 달리 이 값은 statusLine이 다시 그려질 때만 남는다 — 그 사이의 소진은
# 놓친다. `usage session`의 `_MEASURED`와 같은 자리에서, 같은 이유로 출력에 싣는다.
_QUOTA_MEASURED = (
    "이 값은 statusLine이 다시 그려질 때 남은 표본만 잰다."
    " `-p` 모드와 백그라운드 세션에는 애초에 표본이 없다."
    " 같은 시각에 다른 세션, 다른 기기, 웹 Claude를 함께 썼다면 그 소진도 섞여 있을 수 있다."
)


def _quota_dict(attr: Attribution) -> dict[str, object]:
    return {
        "measured": _QUOTA_MEASURED,
        "session_id": attr.session_id,
        "from": attr.from_ts,
        "until": attr.until_ts,
        "windows": [asdict(d) for d in attr.deltas],
        "unmeasurable": attr.unmeasurable,
        "parallel_sessions": attr.parallel_sessions,
    }


def _quota_table(attr: Attribution) -> str:
    lines = [
        _QUOTA_MEASURED,
        f"세션 {attr.session_id} — {attr.from_ts} ~ {attr.until_ts}",
    ]
    for d in attr.deltas:
        lines.append(f"  {d.window_kind}  {d.start_pct:.1f}% -> {d.end_pct:.1f}% (+{d.delta:.1f}p)")
    for reason in attr.unmeasurable:
        lines.append(f"  측정 불가  {reason}")
    if attr.parallel_sessions:
        lines.append(f"병렬 세션  {', '.join(attr.parallel_sessions)}")
    return "\n".join(lines)


def _resolve_transcript(session_arg: str) -> Path:
    """세션 ID 또는 transcript 파일 경로를 받아 파일 경로를 낸다. 못 찾으면 `FileNotFoundError`."""
    given = Path(session_arg)
    if given.is_file():
        return given
    if "/" in session_arg or session_arg.endswith(".jsonl"):
        # 경로를 준 것이므로 세션 ID로 다시 찾지 않는다 — 엉뚱한 위치를 탓하게 된다
        raise FileNotFoundError(f"{given} 파일을 찾지 못했다")
    return find_transcript(session_arg)


def _normalize_project_arg(argv: list[str]) -> list[str]:
    """프로젝트 슬러그는 절대경로 기반이라 항상 '-'로 시작해, 띄어 쓰면 argparse가 다음 옵션으로 오인한다."""
    out = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--project" and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            out.append(f"--project={argv[i + 1]}")
            i += 2
            continue
        out.append(tok)
        i += 1
    return out


def _split_dashdash(argv: list[str]) -> tuple[list[str], list[str] | None]:
    """`--` 뒤의 자식 커맨드를 argparse가 보기 전에 떼어낸다 (`usage quota --collect -- <cmd>`)."""
    if "--" in argv:
        i = argv.index("--")
        return argv[:i], argv[i + 1 :]
    return argv, None


def main(argv: list[str] | None = None) -> int:
    argv = _normalize_project_arg(sys.argv[1:] if argv is None else argv)
    argv, child_cmd = _split_dashdash(argv)
    root = argparse.ArgumentParser(prog="usage", description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    _add_index(sub.add_parser("index", help="코퍼스 전체를 데이터베이스에 적재한다"))
    _add_corpus(sub.add_parser("corpus", help="코퍼스에서 잔존 비용 순위를 뽑는다"))
    q = sub.add_parser("quota", help="statusLine payload에서 구독 한도 소진 표본을 뜬다")
    q.add_argument(
        "--db", default=str(_DEFAULT_QUOTA_DB), help=f"데이터베이스 파일 (기본 {_DEFAULT_QUOTA_DB})"
    )
    q.add_argument(
        "--collect",
        action="store_true",
        help="stdin의 statusLine payload를 표본으로 남긴다."
        " `-- <cmd>`가 있으면 그 payload를 그대로 자식에 넘기고 자식의 출력을 통과시킨다",
    )
    q.add_argument("--session", metavar="ID", help="이 세션 ID의 구간 소진량을 낸다")
    q.add_argument(
        "--from", dest="since", type=int, metavar="N", help="--session과 함께, N번째 요청부터"
    )
    q.add_argument("--until", type=int, metavar="M", help="--session과 함께, M번째 요청까지")
    q.add_argument("--table", action="store_true", help="사람이 읽을 표로 낸다")
    p = sub.add_parser("session", help="세션 하나를 잰다")
    p.add_argument("session", help="세션 ID 또는 transcript 파일 경로")
    p.add_argument("--table", action="store_true", help="사람이 읽을 표로 낸다")
    p.add_argument(
        "--until",
        type=int,
        metavar="N",
        help="N번째 요청까지만 센다. 그 뒤에 뜬 서브에이전트도 뺀다",
    )
    p.add_argument(
        "--from",
        dest="since",
        type=int,
        metavar="N",
        help="N번째 요청부터 센다. 그 앞에서 뜬 서브에이전트도 뺀다",
    )
    p.add_argument(
        "--marks",
        action="store_true",
        help="단계 경계 후보를 요청 번호와 함께 낸다. 그 번호를 --from과 --until에 넣는다",
    )
    p.add_argument(
        "--marks-bash",
        metavar="정규식",
        help="이 정규식에 맞는 Bash 호출도 경계 후보로 낸다. 잡는 그룹이 있으면 잡은 값을"
        " 공백으로 이어 이름으로 쓰고, 없으면 맞은 문자열 전체를 이름으로 쓴다",
    )
    args = root.parse_args(argv)
    if args.command == "index":
        idx_report = index_corpus(Path(args.root), Path(args.db))
        print(json.dumps({"db": args.db, **asdict(idx_report)}, ensure_ascii=False))
        return 0
    if args.command == "quota":
        if args.collect and args.session:
            print("--collect와 --session은 같이 쓸 수 없다", file=sys.stderr)
            return 1
        if args.collect:
            return run_collect(Path(args.db), child_cmd)
        if not args.session:
            print("--collect 또는 --session이 필요하다", file=sys.stderr)
            return 1
        try:
            path = _resolve_transcript(args.session)
        except FileNotFoundError as e:
            print(e, file=sys.stderr)
            return 1
        s = read_session(path, until=args.until, since=args.since)
        if not s.main.requests:
            print("그 구간에 요청이 없다", file=sys.stderr)
            return 1
        # 표본은 statusLine payload의 session_id로 쌓인다 — 그 값은 transcript 파일명(확장자
        # 제외)과 같다. `args.session`이 세션 ID 대신 파일 경로였으면 조회 키가 달라진다.
        with closing(sqlite3.connect(args.db)) as conn:
            attr = attribute_interval(
                conn, path.stem, s.main.requests[0].timestamp, s.main.requests[-1].timestamp
            )
        print(
            _quota_table(attr) if args.table else json.dumps(_quota_dict(attr), ensure_ascii=False)
        )
        return 0
    if args.command == "corpus":
        if args.group_by is not None and args.by != "spread":
            print("--group-by는 --by spread와 함께 쓴다", file=sys.stderr)
            return 1
        with closing(sqlite3.connect(args.db)) as conn:
            if args.check:
                result = check(conn, since=args.since, until=args.until, project=args.project)
                print(
                    _check_report(result)
                    if args.table
                    else json.dumps(_check_dict(result), ensure_ascii=False)
                )
                return 0 if result.ok else 1
            data = report(
                args.by,
                conn,
                since=args.since,
                until=args.until,
                project=args.project,
                group_by=args.group_by,
            )
        trimmed = {k: (v[: args.top] if isinstance(v, list) else v) for k, v in data.items()}
        print(
            _corpus_report(trimmed)
            if args.table
            else json.dumps({"measured": _MEASURED} | trimmed, ensure_ascii=False, indent=2)
        )
        return 0
    if args.marks_bash is not None:
        if not args.marks:
            print("--marks-bash는 --marks와 함께 쓴다", file=sys.stderr)
            return 1
        try:
            re.compile(args.marks_bash)
        except re.error as bad:
            print(f"--marks-bash의 정규식을 읽지 못했다: {bad}", file=sys.stderr)
            return 1
    if args.until is not None and args.until < 1:
        print("--until은 1 이상이어야 한다", file=sys.stderr)
        return 1
    if args.since is not None and args.since < 1:
        print("--from은 1 이상이어야 한다", file=sys.stderr)
        return 1
    if args.since is not None and args.until is not None and args.since > args.until:
        print("--from이 --until보다 크면 잴 요청이 없다", file=sys.stderr)
        return 1

    try:
        path = _resolve_transcript(args.session)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1

    s = read_session(path, until=args.until, since=args.since, marks_bash=args.marks_bash)
    if args.marks:
        print(_marks_report(s))
    elif args.table:
        print(_MEASURED)
        print(_report(s))
    else:
        out = (
            {"measured": _MEASURED}
            | asdict(s, dict_factory=_serializable)
            | {
                "path": str(s.path),
                "idle_minutes": s.idle_minutes,
                "working_minutes": s.working_minutes,
                "combined": asdict(s.combined, dict_factory=_serializable),
            }
        )
        print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""인덱스를 질의해 스코프별 잔존 비용 원장을 만들고 축으로 접는다.

세션 하나, 그 안의 서브에이전트 하나가 스코프 하나다. `usage index`가 적재한 SQLite를 읽어
스코프마다 `residual.build()`를 돌리고, 그 결과를 스킬/도구/파일/프로젝트 같은 축으로 접는다.

`teammate`, `error`, `empty` 세션은 뺀다. `teammate`를 안 빼면 메인 세션의 agent 행으로 이미
들어간 요청이 자기 세션으로 또 담겨 두 번 세어진다.
"""

import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from .residual import Ledger, build, thinking_diagnostic
from .session import Request, ToolCall

_EXCLUDED_STATUS = ("teammate", "error", "empty")

BY_CHOICES = (
    "skill",
    "agent",
    "tool",
    "file",
    "project",
    "period",
    "length",
    "compaction",
    "spread",
)


@dataclass
class Scope:
    """세션 하나, 또는 그 안의 서브에이전트 하나가 낸 원장."""

    session_id: str
    agent_id: str | None
    agent_kind: str
    project_slug: str
    date: str  # 첫 요청의 날짜(YYYY-MM-DD). --since/--until, --by period가 쓴다
    ledger: Ledger
    contexts: list[int] = field(
        default_factory=list
    )  # 요청마다의 실측 context_tokens. --check가 쓴다
    thinking_diag: tuple[int, int] = (
        0,
        0,
    )  # (남는다 가설 오차, 벗겨진다 가설 오차). --check가 쓴다

    @property
    def request_count(self) -> int:
        return len(self.contexts)


@dataclass
class Example:
    """이 값이 어느 세션의 몇 번째 요청에서 나왔는지 — 원본 세션 파일로 되짚는 근거."""

    session_id: str
    order: int


@dataclass
class Bucket:
    """축 하나의 값 하나. 크기 순위와 잔존 순위가 나란히 실려야 어긋난 것을 알아챈다."""

    key: str
    residual: int = 0
    size: int = 0
    count: int = 0
    sessions: set[str] = field(default_factory=set)
    example: Example | None = None

    def add(self, residual: int, size: int, session_id: str, order: int) -> None:
        self.residual += residual
        self.size += size
        self.count += 1
        self.sessions.add(session_id)
        if self.example is None:
            self.example = Example(session_id=session_id, order=order)

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "residual": self.residual,
            "size": self.size,
            "count": self.count,
            "sessions": len(self.sessions),
            "example": {"session_id": self.example.session_id, "order": self.example.order}
            if self.example
            else None,
        }


def _load_scope(
    conn: sqlite3.Connection,
    session_id: str,
    agent_id: str | None,
    project_slug: str,
    agent_kind: str,
) -> Scope:
    where = "agent_id IS NULL" if agent_id is None else "agent_id = ?"
    params: tuple = () if agent_id is None else (agent_id,)
    req_rows = conn.execute(
        "SELECT order_in_scope, context_tokens, output_tokens, timestamp, produced_chars, model,"
        f" input_tokens, cache_read_tokens, cache_write_tokens, thinking_tokens, is_compaction_boundary"
        f" FROM requests WHERE session_id = ? AND {where} ORDER BY order_in_scope",
        (session_id, *params),
    ).fetchall()
    call_rows = conn.execute(
        f"SELECT order_in_scope, tool_name, file_path, target, result_chars, minutes"
        f" FROM tool_calls WHERE session_id = ? AND {where}",
        (session_id, *params),
    ).fetchall()

    requests = [
        Request(
            order=r[0],
            context=r[1],
            output=r[2],
            timestamp=r[3],
            produced_chars=r[4],
            model=r[5],
            input=r[6],
            cache_read=r[7],
            cache_write=r[8],
            thinking=r[9],
        )
        for r in req_rows
    ]
    boundaries = {r[0] for r in req_rows if r[10]}
    tool_calls = [
        ToolCall(order=c[0], name=c[1], path=c[2], target=c[3], result_chars=c[4], minutes=c[5])
        for c in call_rows
    ]
    ledger = build(requests, tool_calls, boundaries)
    date = requests[0].timestamp[:10] if requests else ""
    return Scope(
        session_id=session_id,
        agent_id=agent_id,
        agent_kind=agent_kind,
        project_slug=project_slug,
        date=date,
        ledger=ledger,
        contexts=[r.context for r in requests],
        thinking_diag=thinking_diagnostic(requests, tool_calls, boundaries),
    )


def iter_scopes(
    conn: sqlite3.Connection,
    since: str | None = None,
    until: str | None = None,
    project: str | None = None,
) -> Iterator[Scope]:
    """제외 대상을 뺀 세션의 메인과 서브에이전트 스코프를 전부 낸다."""
    placeholders = ",".join("?" * len(_EXCLUDED_STATUS))
    q = f"SELECT session_id, project_slug FROM sessions WHERE status NOT IN ({placeholders})"
    params: list[str] = list(_EXCLUDED_STATUS)
    if project:
        q += " AND project_slug = ?"
        params.append(project)
    for session_id, project_slug in conn.execute(q, params).fetchall():
        main = _load_scope(conn, session_id, None, project_slug, agent_kind="")
        if not main.date:
            continue  # 메인 요청이 하나도 안 담긴 세션은 스코프를 못 잰다
        if since and main.date < since:
            continue
        if until and main.date > until:
            continue
        yield main
        for agent_id, kind in conn.execute(
            "SELECT agent_id, kind FROM agents WHERE session_id = ?", (session_id,)
        ).fetchall():
            yield _load_scope(conn, session_id, agent_id, project_slug, agent_kind=kind)


def _bucket_by(buckets: dict[str, Bucket], key: str) -> Bucket:
    if key not in buckets:
        buckets[key] = Bucket(key=key)
    return buckets[key]


def by_skill(scopes: Iterator[Scope]) -> list[Bucket]:
    """스킬별 잔존 순위. 크기 순위와 나란히 내 어긋나는 스킬을 드러낸다."""
    buckets: dict[str, Bucket] = {}
    for scope in scopes:
        for item in scope.ledger.items:
            if item.tool_name != "Skill" or not item.target:
                continue
            _bucket_by(buckets, item.target).add(
                item.residual, item.size, scope.session_id, item.start_order
            )
    return sorted(buckets.values(), key=lambda b: b.residual, reverse=True)


def by_tool(scopes: Iterator[Scope]) -> list[Bucket]:
    """도구별 잔존 순위. `Skill`, `Agent`도 도구 이름 자체로 한 항목을 낸다."""
    buckets: dict[str, Bucket] = {}
    for scope in scopes:
        for item in scope.ledger.items:
            if not item.tool_name:
                continue
            _bucket_by(buckets, item.tool_name).add(
                item.residual, item.size, scope.session_id, item.start_order
            )
    return sorted(buckets.values(), key=lambda b: b.residual, reverse=True)


def by_file(scopes: Iterator[Scope]) -> list[Bucket]:
    """파일별 잔존 순위. 같은 파일을 두 번 열면 그만큼 두 번 더해진다."""
    buckets: dict[str, Bucket] = {}
    for scope in scopes:
        for item in scope.ledger.items:
            if not item.file_path:
                continue
            _bucket_by(buckets, item.file_path).add(
                item.residual, item.size, scope.session_id, item.start_order
            )
    return sorted(buckets.values(), key=lambda b: b.residual, reverse=True)


def by_project(scopes: Iterator[Scope]) -> list[Bucket]:
    """프로젝트별 잔존 총합. 서브에이전트가 쓴 것은 부모 프로젝트에 그대로 더한다."""
    buckets: dict[str, Bucket] = {}
    for scope in scopes:
        b = _bucket_by(buckets, scope.project_slug)
        b.residual += scope.ledger.total_residual
        b.size += sum(i.size for i in scope.ledger.items)
        b.count += 1
        b.sessions.add(scope.session_id)
        if b.example is None and scope.ledger.items:
            b.example = Example(
                session_id=scope.session_id, order=scope.ledger.items[0].start_order
            )
    return sorted(buckets.values(), key=lambda b: b.residual, reverse=True)


def by_period(scopes: Iterator[Scope]) -> list[Bucket]:
    """월별(YYYY-MM) 잔존 총합. 세션 시작일 기준이다."""
    buckets: dict[str, Bucket] = {}
    for scope in scopes:
        if scope.agent_id is not None or not scope.date:
            continue  # 서브에이전트는 부모 세션과 같은 달이므로 메인만 센다
        month = scope.date[:7]
        b = _bucket_by(buckets, month)
        b.residual += scope.ledger.total_residual
        b.size += sum(i.size for i in scope.ledger.items)
        b.count += 1
        b.sessions.add(scope.session_id)
        if b.example is None and scope.ledger.items:
            b.example = Example(
                session_id=scope.session_id, order=scope.ledger.items[0].start_order
            )
    return sorted(buckets.values(), key=lambda b: b.key)


_LENGTH_BUCKETS = ((20, "1-20"), (50, "21-50"), (100, "51-100"), (300, "101-300"), (None, "301+"))


def _length_key(n: int) -> str:
    for ceiling, label in _LENGTH_BUCKETS:
        if ceiling is None or n <= ceiling:
            return label
    return _LENGTH_BUCKETS[-1][1]


def by_length(scopes: Iterator[Scope]) -> list[Bucket]:
    """요청 수 구간별 요청 하나당 평균 잔존. 총합은 정의상 늘어나기만 해 무의미하다."""
    buckets: dict[str, Bucket] = {}
    for scope in scopes:
        if scope.agent_id is not None:
            continue
        n = scope.request_count
        if n == 0:
            continue
        b = _bucket_by(buckets, _length_key(n))
        b.residual += scope.ledger.total_residual
        b.size += n  # 요청 수를 size 자리에 실어 평균의 분모로 쓴다
        b.count += 1
        b.sessions.add(scope.session_id)
        if b.example is None and scope.ledger.items:
            b.example = Example(
                session_id=scope.session_id, order=scope.ledger.items[0].start_order
            )
    order = [label for _, label in _LENGTH_BUCKETS]
    return sorted(buckets.values(), key=lambda b: order.index(b.key))


def by_compaction(scopes: Iterator[Scope]) -> list[Bucket]:
    """압축 세그먼트별 요청 하나당 평균 잔존. 세그먼트가 늘수록 값이 뛰면 압축 뒤가 더 비싸다."""
    buckets: dict[str, Bucket] = {}
    for scope in scopes:
        for item in scope.ledger.items:
            key = f"segment {item.segment}"
            b = _bucket_by(buckets, key)
            b.residual += item.residual
            b.size += item.end_order - item.start_order + 1  # 요청 수. 평균의 분모로 쓴다
            b.count += 1
            b.sessions.add(scope.session_id)
            if b.example is None:
                b.example = Example(session_id=scope.session_id, order=item.start_order)
    return sorted(buckets.values(), key=lambda b: int(b.key.split()[1]))


_GROUP_KEYS = ("first-skill", "agent-kind", "project")


def by_spread(scopes: Iterator[Scope], group_by: str) -> list[Bucket]:
    """`group_by`로 나눈 스코프 사이에서 요청 하나당 잔존이 얼마나 벌어지는지.

    인덱스에 작업 종류 라벨이 없으므로 도출 가능한 키만 받는다: 첫 스킬, 서브에이전트 종류,
    프로젝트. 값은 편차 자체가 아니라 그룹별 평균이다 — 편차는 `--table` 출력에서 여러 행을
    나란히 놓고 눈으로 본다.
    """
    if group_by not in _GROUP_KEYS:
        raise ValueError(f"모르는 --group-by 값: {group_by}")
    buckets: dict[str, Bucket] = {}
    for scope in scopes:
        if group_by == "project":
            key = scope.project_slug
        elif group_by == "agent-kind":
            key = scope.agent_kind or "main"
        else:
            first_skill = next(
                (i.target for i in scope.ledger.items if i.tool_name == "Skill" and i.target), ""
            )
            key = first_skill or "(스킬 없음)"
        n = scope.request_count
        if n == 0:
            continue
        b = _bucket_by(buckets, key)
        b.residual += scope.ledger.total_residual
        b.size += n
        b.count += 1
        b.sessions.add(scope.session_id)
        if b.example is None and scope.ledger.items:
            b.example = Example(
                session_id=scope.session_id, order=scope.ledger.items[0].start_order
            )
    return sorted(buckets.values(), key=lambda b: b.residual, reverse=True)


_BY_FUNCS = {
    "skill": by_skill,
    "tool": by_tool,
    "file": by_file,
    "project": by_project,
    "period": by_period,
    "length": by_length,
    "compaction": by_compaction,
}


def report(
    by: str | None,
    conn: sqlite3.Connection,
    since: str | None = None,
    until: str | None = None,
    project: str | None = None,
    group_by: str | None = None,
) -> dict[str, object]:
    """`--by`가 없으면 전 축 요약, 있으면 그 축의 순위. 스코프는 한 번만 만든다."""
    scopes = list(iter_scopes(conn, since=since, until=until, project=project))
    if by == "agent":
        return {"agent": by_agent(scopes)}
    if by == "spread":
        gb = group_by or "project"
        return {"spread": [b.as_dict() for b in by_spread(iter(scopes), gb)], "group_by": gb}
    if by is not None:
        return {by: [b.as_dict() for b in _BY_FUNCS[by](iter(scopes))]}
    return {name: [b.as_dict() for b in func(iter(scopes))] for name, func in _BY_FUNCS.items()} | {
        "agent": by_agent(scopes)
    }


@dataclass
class AgentBucket:
    """서브에이전트 종류 하나. (a) 부모가 지불한 보고서 잔존과 (b) 그 에이전트 자신의 소비를 가른다.

    (a)와 (b)는 서로 다른 스코프에서 나와 같은 호출을 가리킨다는 보장이 없다 — 종류가 같은
    호출을 모아 낼 뿐, 메인이 직접 했을 때보다 요청이 몇 번 늘거나 줄었는지는 알 수 없다.
    """

    kind: str
    paid_by_parent: int = 0
    spent_by_self: int = 0
    calls: int = 0
    scopes: int = 0


def by_agent(scopes: list[Scope]) -> list[dict[str, object]]:
    buckets: dict[str, AgentBucket] = {}
    for scope in scopes:
        for item in scope.ledger.items:
            if item.tool_name != "Agent" or not item.target:
                continue
            b = buckets.setdefault(item.target, AgentBucket(kind=item.target))
            b.paid_by_parent += item.residual
            b.calls += 1
    for scope in scopes:
        if scope.agent_id is None or not scope.agent_kind:
            continue
        b = buckets.setdefault(scope.agent_kind, AgentBucket(kind=scope.agent_kind))
        b.spent_by_self += scope.ledger.total_residual
        b.scopes += 1
    return [
        {
            "kind": b.kind,
            "paid_by_parent": b.paid_by_parent,
            "spent_by_self": b.spent_by_self,
            "calls": b.calls,
            "scopes": b.scopes,
        }
        for b in sorted(buckets.values(), key=lambda b: b.paid_by_parent, reverse=True)
    ]


@dataclass
class CheckResult:
    """`usage corpus --check`가 내는 위반과 진단."""

    scopes: int = 0
    violations: list[dict[str, object]] = field(default_factory=list)
    eviction_events: int = 0
    unattributed_residual: int = 0
    total_residual: int = 0
    thinking_residual_as_kept: int = 0  # growth ≈ output 가설의 오차 합. 작을수록 이 가설이 맞다
    thinking_residual_as_stripped: int = 0  # growth ≈ output − thinking 가설의 오차 합

    @property
    def ok(self) -> bool:
        return not self.violations


def check(
    conn: sqlite3.Connection,
    since: str | None = None,
    until: str | None = None,
    project: str | None = None,
) -> CheckResult:
    """항등식 `Σ(잔존) == Σ context_tokens`이 스코프마다 오차 0으로 성립하는지 본다.

    양변을 독립적으로 낸다 — 잔존 총합은 원장(`residual.build()`)에서, 비교 대상은 인덱스에
    실제 적재된 `context_tokens`에서 그대로 합해, 원장 스스로를 되읽는 동어반복을 피한다.
    """
    result = CheckResult()
    for scope in iter_scopes(conn, since=since, until=until, project=project):
        result.scopes += 1
        result.eviction_events += scope.ledger.eviction_events
        result.total_residual += scope.ledger.total_residual
        result.unattributed_residual += sum(
            i.residual for i in scope.ledger.items if i.kind == "unattributed"
        )
        kept, stripped = scope.thinking_diag
        result.thinking_residual_as_kept += kept
        result.thinking_residual_as_stripped += stripped
        want = sum(scope.contexts)
        got = scope.ledger.total_residual
        if want != got:
            result.violations.append(
                {
                    "session_id": scope.session_id,
                    "agent_id": scope.agent_id,
                    "expected": want,
                    "got": got,
                }
            )
    return result


def open_db(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(db_path)

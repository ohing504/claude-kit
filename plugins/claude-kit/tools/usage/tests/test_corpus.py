"""코퍼스를 축으로 접는 규칙(`corpus.py`)이 정하는 것.

인덱스는 `usage.index._connect`로 실제 스키마를 만든 뒤 `requests`/`tool_calls` 행을 직접
심어 채운다 — 이 파일의 관심사는 SQL 파싱이 아니라 스코프를 모으고 축으로 접는 규칙이다.
"""

import sqlite3
from pathlib import Path

import pytest

from usage.corpus import by_agent, by_file, by_length, by_skill, check, iter_scopes
from usage.index import _connect


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    return _connect(tmp_path / "usage.db")


def _session(
    conn: sqlite3.Connection, session_id: str, project: str = "proj-a", status: str = "ok"
) -> None:
    conn.execute(
        "INSERT INTO sessions (session_id, project_slug, file_path, total_size, latest_mtime,"
        " indexed_at, status) VALUES (?, ?, '', 0, 0, '', ?)",
        (session_id, project, status),
    )


def _agent(
    conn: sqlite3.Connection, session_id: str, agent_id: str, kind: str = "general-purpose"
) -> None:
    conn.execute(
        "INSERT INTO agents (session_id, agent_id, kind, label, parent_agent_id, depth,"
        " order_in_session) VALUES (?, ?, ?, '', '', 1, 1)",
        (session_id, agent_id, kind),
    )


def _req(
    conn: sqlite3.Connection,
    session_id: str,
    order: int,
    context: int,
    output: int = 0,
    agent_id: str | None = None,
    ts: str = "2026-08-20T00:00:00Z",
    boundary: bool = False,
) -> None:
    conn.execute(
        "INSERT INTO requests (session_id, agent_id, order_in_scope, timestamp, model,"
        " input_tokens, cache_read_tokens, cache_write_tokens, output_tokens, thinking_tokens,"
        " produced_chars, context_tokens, is_compaction_boundary)"
        " VALUES (?, ?, ?, ?, '', 0, 0, 0, ?, 0, 0, ?, ?)",
        (session_id, agent_id, order, ts, output, context, int(boundary)),
    )


def _call(
    conn: sqlite3.Connection,
    session_id: str,
    order: int,
    name: str,
    result_chars: int,
    file_path: str = "",
    target: str = "",
    agent_id: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO tool_calls (session_id, agent_id, order_in_scope, tool_name, file_path,"
        " target, result_chars, minutes) VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
        (session_id, agent_id, order, name, file_path, target, result_chars),
    )


def test_a_skill_is_ranked_by_residual_not_by_size(db: sqlite3.Connection) -> None:
    # small: 크기는 작지만 스코프 시작 직후에 불러 오래 남는다.
    _session(db, "s1")
    _req(db, "s1", 1, 1_000)
    _req(db, "s1", 2, 1_200)
    for o in range(3, 12):
        _req(db, "s1", o, 1_200)
    _call(db, "s1", 1, "Skill", 200, target="small")

    # big: 크기는 크지만 끝나기 직전에 불러 금방 스코프가 끝난다.
    _session(db, "s2")
    for o in range(1, 10):
        _req(db, "s2", o, 1_000)
    _req(db, "s2", 10, 1_800)
    _call(db, "s2", 9, "Skill", 800, target="big")
    db.commit()

    buckets = {b.key: b for b in by_skill(iter_scopes(db))}
    assert buckets["big"].size == 800
    assert buckets["small"].size == 200
    assert buckets["small"].residual > buckets["big"].residual  # 크기는 작아도 잔존은 더 크다


def test_opening_the_same_file_twice_doubles_its_residual(db: sqlite3.Connection) -> None:
    _session(db, "s1")
    _req(db, "s1", 1, 1_000)
    _req(db, "s1", 2, 1_100)
    _req(db, "s1", 3, 1_200)
    _call(db, "s1", 1, "Read", 100, file_path="a.py")
    _call(db, "s1", 2, "Read", 100, file_path="a.py")
    db.commit()

    buckets = {b.key: b for b in by_file(iter_scopes(db))}
    assert buckets["a.py"].size == 200
    assert buckets["a.py"].count == 2


def test_teammate_and_error_and_empty_sessions_are_excluded(db: sqlite3.Connection) -> None:
    _session(db, "s1", status="ok")
    _req(db, "s1", 1, 1_000)
    _session(db, "s2", status="teammate")
    _session(db, "s3", status="error")
    _session(db, "s4", status="empty")
    db.commit()

    scopes = list(iter_scopes(db))
    assert {s.session_id for s in scopes} == {"s1"}


def test_a_subagents_ledger_is_its_own_and_not_folded_into_the_parent(
    db: sqlite3.Connection,
) -> None:
    _session(db, "s1")
    _req(db, "s1", 1, 1_000)
    _req(db, "s1", 2, 1_300)
    _call(db, "s1", 1, "Agent", 300, target="general-purpose")
    _agent(db, "s1", "a1", kind="general-purpose")
    _req(db, "s1", 1, 5_000, agent_id="a1")
    _req(db, "s1", 2, 5_800, agent_id="a1")
    db.commit()

    scopes = {(s.session_id, s.agent_id): s for s in iter_scopes(db)}
    assert scopes[("s1", None)].ledger.total_residual == 1_000 + 1_300
    assert scopes[("s1", "a1")].ledger.total_residual == 5_000 + 5_800


def test_agent_axis_splits_what_the_parent_paid_from_what_the_subagent_spent(
    db: sqlite3.Connection,
) -> None:
    _session(db, "s1")
    _req(db, "s1", 1, 1_000)
    _req(db, "s1", 2, 1_300)
    _call(db, "s1", 1, "Agent", 300, target="general-purpose")
    _agent(db, "s1", "a1", kind="general-purpose")
    _req(db, "s1", 1, 5_000, agent_id="a1")
    db.commit()

    rows = {r["kind"]: r for r in by_agent(list(iter_scopes(db)))}
    assert rows["general-purpose"]["paid_by_parent"] == 300  # 부모가 보고서로 지불한 값
    assert rows["general-purpose"]["spent_by_self"] == 5_000  # 자기 스코프에서 쓴 값


def test_length_bucket_reports_average_residual_per_request_not_a_sum(
    db: sqlite3.Connection,
) -> None:
    _session(db, "s1")
    for o in range(1, 6):
        _req(db, "s1", o, 1_000)
    db.commit()

    bucket = next(b for b in by_length(iter_scopes(db)) if b.key == "1-20")
    assert bucket.residual == 5_000
    assert bucket.size == 5  # 요청 수 — 호출부가 residual/size로 평균을 낸다


def test_every_bucket_names_a_session_and_request_to_trace_back_to(db: sqlite3.Connection) -> None:
    _session(db, "s1")
    _req(db, "s1", 1, 1_000)
    _req(db, "s1", 2, 1_200)
    _call(db, "s1", 1, "Skill", 200, target="commit")
    db.commit()

    bucket = by_skill(iter_scopes(db))[0]
    assert bucket.example is not None
    assert bucket.example.session_id == "s1"
    assert isinstance(bucket.example.order, int)


def test_check_reports_no_violations_for_a_well_formed_corpus(db: sqlite3.Connection) -> None:
    _session(db, "s1")
    _req(db, "s1", 1, 1_000)
    _req(db, "s1", 2, 1_300)
    _req(db, "s1", 3, 900)  # 압축 없는 감소 — 퇴장으로 처리돼도 항등식은 깨지지 않는다
    _call(db, "s1", 1, "Read", 300, file_path="a.py")
    db.commit()

    result = check(db)
    assert result.ok
    assert result.violations == []
    assert result.scopes == 1
    assert result.total_residual == 1_000 + 1_300 + 900
    # order 1은 도구를 불러 빠지고, order 2→3(퇴장, output/thinking 둘 다 0)만 잰다.
    assert result.thinking_residual_as_kept == 400  # |growth(-400) - output(0)|
    assert result.thinking_residual_as_stripped == 400  # |growth(-400) - (output(0)-thinking(0))|


def test_check_flags_a_scope_whose_ledger_does_not_match_recorded_context(
    db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # residual.build()는 항등식을 늘 지킨다 — 코퍼스 데이터로는 위반을 재현할 수 없다.
    # 여기서는 build() 자체를 깨진 값으로 바꿔치기해, check()가 그 불일치를 실제로 잡아내는지 본다.
    import usage.corpus as corpus_mod
    from usage.residual import Item, Ledger

    _session(db, "s1")
    _req(db, "s1", 1, 1_000)
    _req(db, "s1", 2, 1_200)
    db.commit()

    def _broken_build(requests, tool_calls, boundaries=None):
        return Ledger(items=[Item(kind="base", size=1, start_order=1, end_order=1)])

    monkeypatch.setattr(corpus_mod, "build", _broken_build)

    result = check(db)
    assert not result.ok
    assert len(result.violations) == 1
    assert result.violations[0]["session_id"] == "s1"
    assert result.violations[0]["expected"] == 1_000 + 1_200
    assert result.violations[0]["got"] == 1

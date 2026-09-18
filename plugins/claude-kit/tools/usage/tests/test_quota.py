"""statusLine payload에서 구독 한도 표본을 어떻게 뽑고 저장하는가 — 이 파일이 판정자다."""

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from usage.cli import _QUOTA_MEASURED, main
from usage.index import _connect as index_connect
from usage.quota import (
    Observation,
    Window,
    attribute_interval,
    is_same_windows,
    parse_payload,
    record,
    window_span,
    window_usage,
)


def _now() -> datetime:
    return datetime(2026, 8, 30, 12, 0, 0, tzinfo=UTC)


def _payload(**windows: dict) -> dict:
    return {"session_id": "s1", "rate_limits": windows}


def _window(pct: float, resets: int) -> dict:
    return {"used_percentage": pct, "resets_at": resets}


def test_a_payload_without_rate_limits_yields_no_observation() -> None:
    """Free 구독과 세션 첫 응답 전에는 `rate_limits`가 없다 — 정상 상태라 크래시하면 안 된다."""
    assert parse_payload({"session_id": "s1"}, _now()) is None


def test_a_payload_without_session_id_yields_no_observation() -> None:
    assert parse_payload({"rate_limits": {"five_hour": _window(10, 100)}}, _now()) is None


def test_only_the_windows_that_are_present_are_kept() -> None:
    """세 창 중 하나만 와도 나머지를 0%로 채우면 안 된다 — 부재와 0%는 다른 값이다."""
    obs = parse_payload(_payload(five_hour=_window(23.5, 1738425600)), _now())
    assert obs is not None
    assert obs.windows == {"five_hour": Window(used_percentage=23.5, resets_at=1738425600)}


def test_context_window_tokens_ride_along_with_the_observation() -> None:
    """3단계 환산의 재료라 같은 관측 시각에 담는다."""
    data = _payload(five_hour=_window(1, 1)) | {
        "context_window": {
            "current_usage": {
                "input_tokens": 8500,
                "output_tokens": 1200,
                "cache_creation_input_tokens": 5000,
                "cache_read_input_tokens": 2000,
            }
        }
    }
    obs = parse_payload(data, _now())
    assert obs is not None
    assert (obs.input_tokens, obs.output_tokens, obs.cache_write_tokens, obs.cache_read_tokens) == (
        8500,
        1200,
        5000,
        2000,
    )


def test_missing_context_window_leaves_token_fields_empty() -> None:
    obs = parse_payload(_payload(five_hour=_window(1, 1)), _now())
    assert obs is not None
    assert obs.input_tokens is None


def test_same_windows_are_recognized_as_a_duplicate() -> None:
    a = parse_payload(_payload(five_hour=_window(23.5, 100)), _now())
    b = parse_payload(_payload(five_hour=_window(23.5, 100)), _now())
    assert a is not None and b is not None
    assert is_same_windows(a, b)


def test_a_changed_percentage_is_not_a_duplicate() -> None:
    a = parse_payload(_payload(five_hour=_window(23.5, 100)), _now())
    b = parse_payload(_payload(five_hour=_window(24.0, 100)), _now())
    assert a is not None and b is not None
    assert not is_same_windows(a, b)


def test_a_window_disappearing_is_not_a_duplicate() -> None:
    """창이 초기화되면 JSON에서 그 창이 사라진다 — 창 집합이 줄어든 것도 변화다."""
    a = parse_payload(_payload(five_hour=_window(99.0, 100), seven_day=_window(50.0, 200)), _now())
    b = parse_payload(_payload(five_hour=_window(1.0, 500)), _now())
    assert a is not None and b is not None
    assert not is_same_windows(a, b)


def test_there_is_no_prior_observation_the_first_time() -> None:
    obs = parse_payload(_payload(five_hour=_window(1, 1)), _now())
    assert obs is not None
    assert not is_same_windows(None, obs)


def _query(db: Path, sql: str) -> list[tuple]:
    with sqlite3.connect(db) as c:
        return c.execute(sql).fetchall()


def test_the_first_observation_is_stored_in_both_tables(tmp_path: Path) -> None:
    db = tmp_path / "quota.db"
    obs = parse_payload(_payload(five_hour=_window(23.5, 1738425600)), _now())
    assert obs is not None
    assert record(obs, db) is True
    assert _query(db, "SELECT session_id, input_tokens FROM quota_observations") == [("s1", None)]
    assert _query(
        db, "SELECT session_id, window_kind, used_percentage, resets_at FROM quota_windows"
    ) == [("s1", "five_hour", 23.5, 1738425600)]


def test_an_identical_observation_is_not_stored_again(tmp_path: Path) -> None:
    db = tmp_path / "quota.db"
    obs = parse_payload(_payload(five_hour=_window(23.5, 1738425600)), _now())
    assert obs is not None
    assert record(obs, db) is True
    later = parse_payload(_payload(five_hour=_window(23.5, 1738425600)), _now())
    assert later is not None
    assert record(later, db) is False
    assert _query(db, "SELECT COUNT(*) FROM quota_observations") == [(1,)]


def test_a_changed_window_is_stored_as_a_new_observation(tmp_path: Path) -> None:
    db = tmp_path / "quota.db"
    first = parse_payload(_payload(five_hour=_window(23.5, 1738425600)), _now())
    assert first is not None
    record(first, db)
    later = datetime(2026, 8, 30, 12, 5, 0, tzinfo=UTC)
    second = parse_payload(_payload(five_hour=_window(30.0, 1738425600)), later)
    assert second is not None
    assert record(second, db) is True
    assert _query(db, "SELECT COUNT(*) FROM quota_observations") == [(2,)]


def test_different_sessions_do_not_dedupe_against_each_other(tmp_path: Path) -> None:
    db = tmp_path / "quota.db"
    obs1 = parse_payload(_payload(five_hour=_window(1.0, 1)), _now())
    assert obs1 is not None
    record(obs1, db)
    obs2 = Observation(
        observed_at=obs1.observed_at,
        session_id="s2",
        windows=obs1.windows,
    )
    assert record(obs2, db) is True
    assert _query(db, "SELECT COUNT(DISTINCT session_id) FROM quota_observations") == [(2,)]


def test_collect_records_a_sample_and_passes_the_payload_through(
    tmp_path: Path, capsysbinary
) -> None:
    """statusLine을 tee한다 — 자식의 stdout은 표본을 뜨는 것과 무관하게 그대로 나가야 한다."""
    db = tmp_path / "quota.db"
    payload = json.dumps(_payload(five_hour=_window(10, 100)) | {"foo": "bar"}).encode()
    import io

    import usage.cli as cli_mod

    class _Stdin:
        buffer = io.BytesIO(payload)

    orig_stdin = cli_mod.sys.stdin
    cli_mod.sys.stdin = _Stdin()
    try:
        code = main(["quota", "--db", str(db), "--collect", "--", "cat"])
    finally:
        cli_mod.sys.stdin = orig_stdin
    assert code == 0
    out = capsysbinary.readouterr().out
    assert json.loads(out) == json.loads(payload)
    assert _query(db, "SELECT session_id FROM quota_observations") == [("s1",)]


def test_collect_without_a_child_command_only_records(tmp_path: Path, capsysbinary) -> None:
    db = tmp_path / "quota.db"
    payload = json.dumps(_payload(five_hour=_window(10, 100))).encode()
    import io

    import usage.cli as cli_mod

    class _Stdin:
        buffer = io.BytesIO(payload)

    orig_stdin = cli_mod.sys.stdin
    cli_mod.sys.stdin = _Stdin()
    try:
        code = main(["quota", "--db", str(db), "--collect"])
    finally:
        cli_mod.sys.stdin = orig_stdin
    assert code == 0
    assert capsysbinary.readouterr().out == b""
    assert _query(db, "SELECT session_id FROM quota_observations") == [("s1",)]


def _record_at(db: Path, session_id: str, at: datetime, **windows: dict) -> None:
    obs = parse_payload(_payload(**windows) | {"session_id": session_id}, at)
    assert obs is not None
    record(obs, db)


def test_two_samples_in_range_give_a_positive_delta(tmp_path: Path) -> None:
    db = tmp_path / "quota.db"
    _record_at(db, "s1", datetime(2026, 8, 30, 12, 0, 0, tzinfo=UTC), five_hour=_window(10, 999))
    _record_at(db, "s1", datetime(2026, 8, 30, 12, 5, 0, tzinfo=UTC), five_hour=_window(15, 999))
    with sqlite3.connect(db) as conn:
        attr = attribute_interval(
            conn, "s1", "2026-08-30T11:00:00.000Z", "2026-08-30T13:00:00.000Z"
        )
    assert attr.unmeasurable == []
    assert [(d.window_kind, d.start_pct, d.end_pct, d.delta) for d in attr.deltas] == [
        ("five_hour", 10.0, 15.0, 5.0)
    ]


def test_fewer_than_two_samples_is_unmeasurable(tmp_path: Path) -> None:
    db = tmp_path / "quota.db"
    _record_at(db, "s1", datetime(2026, 8, 30, 12, 0, 0, tzinfo=UTC), five_hour=_window(10, 999))
    with sqlite3.connect(db) as conn:
        attr = attribute_interval(
            conn, "s1", "2026-08-30T11:00:00.000Z", "2026-08-30T13:00:00.000Z"
        )
    assert attr.deltas == []
    assert attr.unmeasurable


def test_a_window_that_resets_mid_interval_is_unmeasurable(tmp_path: Path) -> None:
    """`resets_at`이 구간 안에서 달라지면 두 값은 다른 창이다 — 차분이 소진량이 아니다."""
    db = tmp_path / "quota.db"
    _record_at(db, "s1", datetime(2026, 8, 30, 12, 0, 0, tzinfo=UTC), five_hour=_window(90, 100))
    _record_at(db, "s1", datetime(2026, 8, 30, 12, 5, 0, tzinfo=UTC), five_hour=_window(5, 900))
    with sqlite3.connect(db) as conn:
        attr = attribute_interval(
            conn, "s1", "2026-08-30T11:00:00.000Z", "2026-08-30T13:00:00.000Z"
        )
    assert attr.deltas == []
    assert any("초기화" in r for r in attr.unmeasurable)


def test_a_negative_delta_is_unmeasurable(tmp_path: Path) -> None:
    db = tmp_path / "quota.db"
    _record_at(db, "s1", datetime(2026, 8, 30, 12, 0, 0, tzinfo=UTC), five_hour=_window(50, 999))
    _record_at(db, "s1", datetime(2026, 8, 30, 12, 5, 0, tzinfo=UTC), five_hour=_window(40, 999))
    with sqlite3.connect(db) as conn:
        attr = attribute_interval(
            conn, "s1", "2026-08-30T11:00:00.000Z", "2026-08-30T13:00:00.000Z"
        )
    assert attr.deltas == []
    assert attr.unmeasurable


def test_a_window_absent_from_both_ends_is_silently_skipped(tmp_path: Path) -> None:
    """구간 전체에 그 창이 한 번도 없었으면 측정 대상이 아니다 — 실패로 세지 않는다."""
    db = tmp_path / "quota.db"
    _record_at(
        db,
        "s1",
        datetime(2026, 8, 30, 12, 0, 0, tzinfo=UTC),
        five_hour=_window(10, 999),
        seven_day=_window(20, 888),
    )
    _record_at(
        db,
        "s1",
        datetime(2026, 8, 30, 12, 5, 0, tzinfo=UTC),
        five_hour=_window(15, 999),
        seven_day=_window(25, 888),
    )
    with sqlite3.connect(db) as conn:
        attr = attribute_interval(
            conn, "s1", "2026-08-30T11:00:00.000Z", "2026-08-30T13:00:00.000Z"
        )
    assert {d.window_kind for d in attr.deltas} == {"five_hour", "seven_day"}
    assert attr.unmeasurable == []


def test_other_sessions_observed_in_the_same_span_are_listed_as_parallel(tmp_path: Path) -> None:
    db = tmp_path / "quota.db"
    _record_at(db, "s1", datetime(2026, 8, 30, 12, 0, 0, tzinfo=UTC), five_hour=_window(10, 999))
    _record_at(db, "s2", datetime(2026, 8, 30, 12, 2, 0, tzinfo=UTC), five_hour=_window(30, 999))
    _record_at(db, "s1", datetime(2026, 8, 30, 12, 5, 0, tzinfo=UTC), five_hour=_window(15, 999))
    with sqlite3.connect(db) as conn:
        attr = attribute_interval(
            conn, "s1", "2026-08-30T11:00:00.000Z", "2026-08-30T13:00:00.000Z"
        )
    assert attr.parallel_sessions == ["s2"]


def test_samples_outside_the_requested_span_are_not_counted(tmp_path: Path) -> None:
    db = tmp_path / "quota.db"
    _record_at(db, "s1", datetime(2026, 8, 30, 9, 0, 0, tzinfo=UTC), five_hour=_window(1, 999))
    _record_at(db, "s1", datetime(2026, 8, 30, 12, 0, 0, tzinfo=UTC), five_hour=_window(10, 999))
    _record_at(db, "s1", datetime(2026, 8, 30, 12, 5, 0, tzinfo=UTC), five_hour=_window(15, 999))
    with sqlite3.connect(db) as conn:
        attr = attribute_interval(
            conn, "s1", "2026-08-30T11:00:00.000Z", "2026-08-30T13:00:00.000Z"
        )
    assert [(d.start_pct, d.end_pct) for d in attr.deltas] == [(10.0, 15.0)]


def test_cli_session_report_keys_on_the_transcript_filename_not_the_given_path(
    tmp_path: Path, capsys
) -> None:
    """statusLine payload의 session_id는 transcript 파일명(확장자 제외)과 같다 — `--session`에
    경로를 줘도 그 파일명으로 조회해야 한다."""
    transcript = tmp_path / "deadbeef-0001.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "type": "assistant",
                "timestamp": "2026-08-30T12:00:00.000Z",
                "message": {
                    "role": "assistant",
                    "model": "claude-opus-5",
                    "usage": {"output_tokens": 1},
                },
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "assistant",
                "timestamp": "2026-08-30T12:10:00.000Z",
                "message": {
                    "role": "assistant",
                    "model": "claude-opus-5",
                    "usage": {"output_tokens": 1},
                },
            }
        ),
        encoding="utf-8",
    )
    db = tmp_path / "quota.db"
    _record_at(
        db,
        "deadbeef-0001",
        datetime(2026, 8, 30, 12, 0, 30, tzinfo=UTC),
        five_hour=_window(10, 999),
    )
    _record_at(
        db,
        "deadbeef-0001",
        datetime(2026, 8, 30, 12, 9, 30, tzinfo=UTC),
        five_hour=_window(22, 999),
    )
    code = main(["quota", "--db", str(db), "--session", str(transcript)])
    assert code == 0
    got = json.loads(capsys.readouterr().out)
    assert got["windows"] == [
        {
            "window_kind": "five_hour",
            "start_pct": 10.0,
            "end_pct": 22.0,
            "delta": 12.0,
            "resets_at": 999,
        }
    ]


def test_a_broken_payload_does_not_break_the_pass_through(tmp_path: Path, capsysbinary) -> None:
    """statusLine이 죽으면 사용자가 이 도구를 떼어내고, 그러면 표본이 아예 안 쌓인다."""
    db = tmp_path / "quota.db"
    payload = b"not json at all"
    import io

    import usage.cli as cli_mod

    class _Stdin:
        buffer = io.BytesIO(payload)

    orig_stdin = cli_mod.sys.stdin
    cli_mod.sys.stdin = _Stdin()
    try:
        code = main(["quota", "--db", str(db), "--collect", "--", "cat"])
    finally:
        cli_mod.sys.stdin = orig_stdin
    assert code == 0
    assert capsysbinary.readouterr().out == payload
    assert not db.exists() or _query(db, "SELECT COUNT(*) FROM quota_observations") == [(0,)]


def test_an_unrunnable_child_command_does_not_crash(tmp_path: Path) -> None:
    """자식 커맨드가 실행조차 안 되면(오탈자, 권한 없음) 표본은 이미 남았으니 예외로 죽지 않는다."""
    db = tmp_path / "quota.db"
    payload = json.dumps(_payload(five_hour=_window(10, 100))).encode()
    import io

    import usage.cli as cli_mod

    class _Stdin:
        buffer = io.BytesIO(payload)

    orig_stdin = cli_mod.sys.stdin
    cli_mod.sys.stdin = _Stdin()
    try:
        code = main(["quota", "--db", str(db), "--collect", "--", "/no/such/binary-xyz"])
    finally:
        cli_mod.sys.stdin = orig_stdin
    assert code == 1
    assert _query(db, "SELECT session_id FROM quota_observations") == [("s1",)]


def test_observations_within_the_same_second_do_not_collide(tmp_path: Path) -> None:
    """statusLine의 300ms 디바운스로 같은 초에 서로 다른 표본이 올 수 있다 — 마이크로초까지 담아 구분한다."""
    db = tmp_path / "quota.db"
    first = parse_payload(
        _payload(five_hour=_window(10, 100)), datetime(2026, 8, 30, 12, 0, 0, 100000, tzinfo=UTC)
    )
    second = parse_payload(
        _payload(five_hour=_window(20, 100)), datetime(2026, 8, 30, 12, 0, 0, 900000, tzinfo=UTC)
    )
    assert first is not None and second is not None
    assert record(first, db) is True
    assert record(second, db) is True
    assert _query(db, "SELECT COUNT(*) FROM quota_observations") == [(2,)]


def test_the_child_commands_own_project_flag_is_not_merged_by_normalize(tmp_path: Path) -> None:
    """`--project`를 argparse가 보기 전에 합치는 정규화는 `--` 뒤 자식 커맨드에는 적용되면 안 된다."""
    db = tmp_path / "quota.db"
    payload = json.dumps(_payload(five_hour=_window(10, 100))).encode()
    import io

    import usage.cli as cli_mod

    class _Stdin:
        buffer = io.BytesIO(payload)

    orig_stdin = cli_mod.sys.stdin
    cli_mod.sys.stdin = _Stdin()
    try:
        code = main(
            [
                "quota",
                "--db",
                str(db),
                "--collect",
                "--",
                "python3",
                "-c",
                "import sys; sys.exit(0)",
                "--project",
                "foo",
            ]
        )
    finally:
        cli_mod.sys.stdin = orig_stdin
    assert code == 0


def test_session_range_is_validated_the_same_way_as_the_session_command(tmp_path: Path) -> None:
    """`quota --session`도 `session`과 같은 `--from`/`--until` 범위 검증을 받는다."""
    db = tmp_path / "quota.db"
    code = main(
        ["quota", "--db", str(db), "--session", "deadbeef-0001", "--from", "50", "--until", "5"]
    )
    assert code == 1


# --- 창 하나가 쓴 양 ---------------------------------------------------------


def _resets_at() -> int:
    """2026-09-19 01:00 KST — 주간 창은 토요일 01:00 KST에 초기화된다."""
    return int(datetime(2026, 9, 18, 16, 0, tzinfo=UTC).timestamp())


def _sample(db: Path, pct: float, kind: str = "seven_day", resets: int | None = None) -> None:
    record(
        Observation(
            session_id="s1",
            windows={kind: Window(used_percentage=pct, resets_at=resets or _resets_at())},
            observed_at=datetime(2026, 9, 18, 15, 58, tzinfo=UTC).isoformat(),
        ),
        db,
    )


def _request(
    conn: sqlite3.Connection,
    timestamp: str,
    *,
    model: str = "claude-opus-5",
    read: int = 900,
    output: int = 100,
) -> None:
    conn.execute(
        "INSERT INTO requests (session_id, agent_id, order_in_scope, timestamp, model,"
        " input_tokens, cache_read_tokens, cache_write_tokens, output_tokens, thinking_tokens,"
        " produced_chars, context_tokens, is_compaction_boundary)"
        " VALUES ('s1', NULL, 1, ?, ?, 0, ?, 0, ?, 0, 0, 0, 0)",
        (timestamp, model, read, output),
    )
    conn.commit()


def test_a_seven_day_window_starts_seven_days_before_it_resets() -> None:
    start, end = window_span(_resets_at(), "seven_day")
    assert start == datetime(2026, 9, 11, 16, 0, tzinfo=UTC)
    assert end == datetime(2026, 9, 18, 16, 0, tzinfo=UTC)


def test_a_five_hour_window_starts_five_hours_before_it_resets() -> None:
    start, _end = window_span(_resets_at(), "five_hour")
    assert start == datetime(2026, 9, 18, 11, 0, tzinfo=UTC)


def test_only_requests_inside_the_window_are_counted(tmp_path: Path) -> None:
    """창 시작은 포함하고 초기화 시각은 제외한다 — 초기화 시각의 요청은 다음 창 몫이다."""
    _sample(tmp_path / "q.db", 50.0)
    with closing(index_connect(tmp_path / "i.db")) as idx:
        _request(idx, "2026-09-11T15:59:59.999Z")  # 창 시작 직전
        _request(idx, "2026-09-11T16:00:00.000Z")  # 창 시작 — 포함
        _request(idx, "2026-09-15T00:00:00.000Z")  # 창 안 — 포함
        _request(idx, "2026-09-18T16:00:00.000Z")  # 초기화 시각 — 제외
        with closing(sqlite3.connect(tmp_path / "q.db")) as q:
            usage = window_usage(q, idx, "seven_day")
    assert usage is not None
    assert usage.requests == 2
    assert usage.total_tokens == 2000


def test_tokens_are_broken_down_by_model(tmp_path: Path) -> None:
    _sample(tmp_path / "q.db", 50.0)
    with closing(index_connect(tmp_path / "i.db")) as idx:
        _request(idx, "2026-09-15T00:00:00.000Z", model="claude-opus-5")
        _request(idx, "2026-09-15T00:00:01.000Z", model="claude-sonnet-5")
        _request(idx, "2026-09-15T00:00:02.000Z", model="claude-sonnet-5")
        with closing(sqlite3.connect(tmp_path / "q.db")) as q:
            usage = window_usage(q, idx, "seven_day")
    assert usage is not None
    assert [(m.model, m.requests) for m in usage.by_model] == [
        ("claude-sonnet-5", 2),
        ("claude-opus-5", 1),
    ]


def test_the_full_window_projection_divides_by_the_observed_percentage(tmp_path: Path) -> None:
    """한도의 절반을 쓴 시점에 20억 토큰이면 한도 전체는 40억 토큰어치다."""
    _sample(tmp_path / "q.db", 50.0)
    with closing(index_connect(tmp_path / "i.db")) as idx:
        _request(idx, "2026-09-15T00:00:00.000Z", read=1_999_999_000, output=1000)
        with closing(sqlite3.connect(tmp_path / "q.db")) as q:
            usage = window_usage(q, idx, "seven_day")
    assert usage is not None
    assert usage.projected_full == 4_000_000_000


def test_a_zero_percentage_yields_no_projection(tmp_path: Path) -> None:
    """창이 막 열려 0%면 나눌 수 없다 — 0 대신 값을 내지 않는다."""
    _sample(tmp_path / "q.db", 0.0)
    with closing(index_connect(tmp_path / "i.db")) as idx:
        _request(idx, "2026-09-15T00:00:00.000Z")
        with closing(sqlite3.connect(tmp_path / "q.db")) as q:
            usage = window_usage(q, idx, "seven_day")
    assert usage is not None
    assert usage.projected_full is None
    assert usage.unmeasurable == ["소진율이 0이라 한도 전체를 환산할 수 없다"]


def test_a_monthly_plan_price_yields_an_effective_unit_price(tmp_path: Path) -> None:
    """월 $200은 주 $46.15다(12개월 / 52주). 한도를 다 쓴 시점에 100M 토큰이면 1M당 $0.4615다."""
    _sample(tmp_path / "q.db", 100.0)
    with closing(index_connect(tmp_path / "i.db")) as idx:
        _request(idx, "2026-09-15T00:00:00.000Z", read=99_900_000, output=100_000)
        with closing(sqlite3.connect(tmp_path / "q.db")) as q:
            usage = window_usage(q, idx, "seven_day", plan_monthly=200.0)
    assert usage is not None
    assert usage.effective_usd_per_mtok is not None
    assert round(usage.effective_usd_per_mtok, 4) == 0.4615


def test_a_window_with_no_sample_yields_nothing(tmp_path: Path) -> None:
    """그 창의 표본이 한 번도 안 왔으면 창 경계를 모른다 — 추측해서 내지 않는다."""
    _sample(tmp_path / "q.db", 50.0, kind="five_hour")
    with (
        closing(index_connect(tmp_path / "i.db")) as idx,
        closing(sqlite3.connect(tmp_path / "q.db")) as q,
    ):
        assert window_usage(q, idx, "seven_day") is None


def test_a_monthly_plan_price_is_not_applied_to_the_five_hour_window(tmp_path: Path) -> None:
    """5시간 창은 하루에 여러 번 열려 월 요금을 배분할 근거가 없다."""
    _sample(tmp_path / "q.db", 50.0, kind="five_hour")
    with closing(index_connect(tmp_path / "i.db")) as idx:
        _request(idx, "2026-09-18T12:00:00.000Z")
        with closing(sqlite3.connect(tmp_path / "q.db")) as q:
            usage = window_usage(q, idx, "five_hour", plan_monthly=200.0)
    assert usage is not None
    assert usage.effective_usd_per_mtok is None
    assert usage.unmeasurable == ["월 요금은 주간 창에만 배분할 수 있다"]


# --- 창 집계를 CLI로 부르기 ---------------------------------------------------


def _window_argv(tmp_path: Path, *extra: str) -> list[str]:
    return [
        "quota",
        "--window",
        "seven_day",
        "--db",
        str(tmp_path / "q.db"),
        "--index-db",
        str(tmp_path / "i.db"),
        *extra,
    ]


def test_cli_window_reports_the_totals_with_the_measurement_boundary(
    tmp_path: Path, capsys
) -> None:
    _sample(tmp_path / "q.db", 50.0)
    with closing(index_connect(tmp_path / "i.db")) as idx:
        _request(idx, "2026-09-15T00:00:00.000Z")
    assert main(_window_argv(tmp_path)) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["measured"] == _QUOTA_MEASURED
    assert got["window_kind"] == "seven_day"
    assert got["total_tokens"] == 1000
    assert got["projected_full"] == 2000


def test_cli_window_table_lists_each_model(tmp_path: Path, capsys) -> None:
    _sample(tmp_path / "q.db", 50.0)
    with closing(index_connect(tmp_path / "i.db")) as idx:
        _request(idx, "2026-09-15T00:00:00.000Z", model="claude-opus-5")
        _request(idx, "2026-09-15T01:00:00.000Z", model="claude-sonnet-5")
    assert main(_window_argv(tmp_path, "--table")) == 0
    out = capsys.readouterr().out
    assert "claude-opus-5" in out
    assert "claude-sonnet-5" in out


def test_cli_window_with_a_plan_price_prints_the_unit_price(tmp_path: Path, capsys) -> None:
    _sample(tmp_path / "q.db", 50.0)
    with closing(index_connect(tmp_path / "i.db")) as idx:
        _request(idx, "2026-09-15T00:00:00.000Z")
    assert main(_window_argv(tmp_path, "--plan-monthly", "200")) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["plan_monthly_usd"] == 200.0
    assert got["effective_usd_per_mtok"] is not None


def test_cli_window_without_a_sample_fails_instead_of_guessing(tmp_path: Path, capsys) -> None:
    (tmp_path / "q.db").touch()
    _sample(tmp_path / "q.db", 50.0, kind="five_hour")
    with closing(index_connect(tmp_path / "i.db")):
        pass
    assert main(_window_argv(tmp_path)) == 1
    assert "표본이 없다" in capsys.readouterr().err


def test_cli_window_and_session_cannot_be_asked_for_together(tmp_path: Path, capsys) -> None:
    assert main(_window_argv(tmp_path, "--session", "s1")) == 1
    assert "같이 쓸 수 없다" in capsys.readouterr().err


def test_a_window_that_already_reset_is_marked_stale(tmp_path: Path) -> None:
    """마지막 표본이 낡아 창이 이미 초기화됐으면, 그 수치를 현재 창으로 읽으면 안 된다."""
    _sample(tmp_path / "q.db", 50.0)
    with (
        closing(index_connect(tmp_path / "i.db")) as idx,
        closing(sqlite3.connect(tmp_path / "q.db")) as q,
    ):
        _request(idx, "2026-09-15T00:00:00.000Z")
        after = window_usage(q, idx, "seven_day", now=datetime(2026, 9, 19, 1, 0, tzinfo=UTC))
        during = window_usage(q, idx, "seven_day", now=datetime(2026, 9, 18, 15, 0, tzinfo=UTC))
    assert after is not None and after.already_reset
    assert during is not None and not during.already_reset

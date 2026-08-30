"""statusLine payload에서 구독 한도 표본을 어떻게 뽑고 저장하는가 — 이 파일이 판정자다."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from usage.cli import main
from usage.quota import (
    Observation,
    Window,
    attribute_interval,
    is_same_windows,
    parse_payload,
    record,
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

"""statusLine payload에서 구독 한도 소진 표본을 뽑아 저장한다.

한도 값(5시간/7일/지출 한도 소진 비율)은 대화 세션 동안 디스크 어디에도 남지 않는다.
statusLine 훅에 오는 stdin JSON이 유일한 경로다(`code.claude.com/docs/en/statusline`).
표본을 어떻게 뽑고 언제 중복으로 보는지는 `tests/test_quota.py`가 정본이다.
"""

import json
import sqlite3
import subprocess
import sys
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

_WINDOW_KINDS = ("five_hour", "seven_day", "spend_limit")


@dataclass(frozen=True)
class Window:
    used_percentage: float
    resets_at: int


@dataclass(frozen=True)
class Observation:
    """관측 하나. `windows`에 없는 창은 그 순간 페이로드에 아예 없었다는 뜻이다 — 0%가 아니다."""

    session_id: str
    windows: dict[str, Window] = field(default_factory=dict)
    observed_at: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None


def parse_payload(data: dict, now: datetime) -> Observation | None:
    """statusLine stdin JSON 하나를 표본으로 바꾼다.

    `rate_limits`나 `session_id`가 없으면 `None`을 낸다 — Free 구독, 세션의 첫 API 응답 전에는
    정상적으로 없는 값이라 크래시하면 안 된다. 창은 페이로드에 있는 것만 담는다.
    """
    session_id = data.get("session_id")
    rate_limits = data.get("rate_limits")
    if not session_id or not isinstance(rate_limits, dict):
        return None
    windows: dict[str, Window] = {}
    for kind in _WINDOW_KINDS:
        w = rate_limits.get(kind)
        if not isinstance(w, dict):
            continue
        pct, resets = w.get("used_percentage"), w.get("resets_at")
        if pct is None or resets is None:
            continue
        windows[kind] = Window(used_percentage=float(pct), resets_at=int(resets))
    if not windows:
        return None
    usage = (data.get("context_window") or {}).get("current_usage") or {}
    return Observation(
        session_id=session_id,
        windows=windows,
        observed_at=now.astimezone(UTC).isoformat(timespec="microseconds"),
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        cache_read_tokens=usage.get("cache_read_input_tokens"),
        cache_write_tokens=usage.get("cache_creation_input_tokens"),
    )


def is_same_windows(prev: Observation | None, cur: Observation) -> bool:
    """직전 관측과 창 집합, 소진율, 초기화 시각이 전부 같은가.

    statusLine은 300ms 디바운스로 자주 다시 그려진다. 같으면 남기지 않아 파일이 무한히
    커지는 것을 막는다. 창이 하나라도 사라지거나 나타나면 다른 것으로 본다 — 그것이 창
    초기화다.
    """
    return prev is not None and prev.windows == cur.windows


_SCHEMA = """
CREATE TABLE IF NOT EXISTS quota_observations (
  observed_at        TEXT NOT NULL,
  session_id         TEXT NOT NULL,
  input_tokens       INTEGER,
  output_tokens      INTEGER,
  cache_read_tokens  INTEGER,
  cache_write_tokens INTEGER,
  PRIMARY KEY (observed_at, session_id)
);

CREATE TABLE IF NOT EXISTS quota_windows (
  observed_at     TEXT NOT NULL,
  session_id      TEXT NOT NULL,
  window_kind     TEXT NOT NULL,
  used_percentage REAL NOT NULL,
  resets_at       INTEGER NOT NULL,
  PRIMARY KEY (observed_at, session_id, window_kind)
);

CREATE INDEX IF NOT EXISTS idx_quota_windows_session ON quota_windows(session_id);
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    """표본은 그 시각이 지나면 다시 만들 수 없다 — `index.py`의 `_connect()`와 달리 DROP하지
    않는다. 스키마를 바꿀 때는 여기에 `ALTER TABLE`을 추가한다."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def _last_observation(conn: sqlite3.Connection, session_id: str) -> Observation | None:
    row = conn.execute(
        "SELECT observed_at, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens"
        " FROM quota_observations WHERE session_id = ? ORDER BY observed_at DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    observed_at = row[0]
    windows = {
        kind: Window(used_percentage=pct, resets_at=resets)
        for kind, pct, resets in conn.execute(
            "SELECT window_kind, used_percentage, resets_at FROM quota_windows"
            " WHERE session_id = ? AND observed_at = ?",
            (session_id, observed_at),
        )
    }
    return Observation(
        session_id=session_id,
        windows=windows,
        observed_at=observed_at,
        input_tokens=row[1],
        output_tokens=row[2],
        cache_read_tokens=row[3],
        cache_write_tokens=row[4],
    )


def record(obs: Observation, db_path: Path) -> bool:
    """직전 관측과 창이 전부 같으면 건너뛴다. 새로 넣었으면 `True`."""
    with closing(_connect(db_path)) as conn:
        prev = _last_observation(conn, obs.session_id)
        if is_same_windows(prev, obs):
            return False
        conn.execute(
            "INSERT OR IGNORE INTO quota_observations (observed_at, session_id, input_tokens,"
            " output_tokens, cache_read_tokens, cache_write_tokens) VALUES (?, ?, ?, ?, ?, ?)",
            (
                obs.observed_at,
                obs.session_id,
                obs.input_tokens,
                obs.output_tokens,
                obs.cache_read_tokens,
                obs.cache_write_tokens,
            ),
        )
        conn.executemany(
            "INSERT OR IGNORE INTO quota_windows (observed_at, session_id, window_kind,"
            " used_percentage, resets_at) VALUES (?, ?, ?, ?, ?)",
            [
                (obs.observed_at, obs.session_id, kind, w.used_percentage, w.resets_at)
                for kind, w in obs.windows.items()
            ],
        )
        conn.commit()
    return True


def collect(payload: bytes, db_path: Path, now: datetime | None = None) -> None:
    """payload 하나를 표본으로 남긴다. 예외를 밖으로 내지 않는다.

    statusLine의 화면 출력을 이 계측이 죽이면 사용자가 이 도구를 떼어내고, 그러면 표본이
    아예 안 쌓인다 — 화면이 살아 있는 것이 표본 하나보다 중요하다.
    """
    try:
        data = json.loads(payload)
        obs = parse_payload(data, now or datetime.now(UTC))
        if obs is not None:
            record(obs, db_path)
    except Exception:
        pass


@dataclass(frozen=True)
class WindowDelta:
    window_kind: str
    start_pct: float
    end_pct: float
    delta: float
    resets_at: int


@dataclass(frozen=True)
class Attribution:
    """세션 구간 하나의 소진량 판정. `unmeasurable`이 비어 있지 않으면 그만큼 값을 못 낸 것이다."""

    session_id: str
    from_ts: str
    until_ts: str
    deltas: list[WindowDelta]
    unmeasurable: list[str]
    parallel_sessions: list[str]


def _windows_at(conn: sqlite3.Connection, session_id: str, observed_at: str) -> dict[str, Window]:
    return {
        kind: Window(used_percentage=pct, resets_at=resets)
        for kind, pct, resets in conn.execute(
            "SELECT window_kind, used_percentage, resets_at FROM quota_windows"
            " WHERE session_id = ? AND observed_at = ?",
            (session_id, observed_at),
        )
    }


def attribute_interval(
    conn: sqlite3.Connection, session_id: str, from_ts: str, until_ts: str
) -> Attribution:
    """`from_ts`와 `until_ts`(요청 타임스탬프, ISO8601) 사이에 든 표본으로 소진량을 낸다.

    문자열 그대로 SQL에서 비교하지 않는다 — 요청 타임스탬프는 밀리초와 `Z`를 쓰고 표본의
    `observed_at`은 그렇지 않아, 초가 같아도 문자열 정렬이 어긋난다. `datetime`으로 파싱해
    비교한다.
    """
    lo, hi = datetime.fromisoformat(from_ts), datetime.fromisoformat(until_ts)
    rows = conn.execute(
        "SELECT observed_at FROM quota_observations WHERE session_id = ? ORDER BY observed_at",
        (session_id,),
    ).fetchall()
    in_range = [r[0] for r in rows if lo <= datetime.fromisoformat(r[0]) <= hi]
    if len(in_range) < 2:
        return Attribution(
            session_id, from_ts, until_ts, [], ["그 구간에 표본이 두 개 미만이다"], []
        )
    first_at, last_at = in_range[0], in_range[-1]
    first_windows = _windows_at(conn, session_id, first_at)
    last_windows = _windows_at(conn, session_id, last_at)
    deltas: list[WindowDelta] = []
    unmeasurable: list[str] = []
    for kind in _WINDOW_KINDS:
        a, b = first_windows.get(kind), last_windows.get(kind)
        if a is None and b is None:
            continue  # 그 구간에 이 창이 한 번도 오지 않았다 — 측정 대상이 아니다
        if a is None or b is None:
            unmeasurable.append(f"{kind}: 구간 시작 또는 끝에 표본이 없다")
            continue
        if a.resets_at != b.resets_at:
            unmeasurable.append(f"{kind}: 구간 중 초기화됐다(resets_at 변화)")
            continue
        delta = b.used_percentage - a.used_percentage
        if delta < 0:
            unmeasurable.append(f"{kind}: 소진율이 줄었다(값이 비정상이다)")
            continue
        deltas.append(WindowDelta(kind, a.used_percentage, b.used_percentage, delta, b.resets_at))
    parallel = sorted(
        {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT session_id FROM quota_observations"
                " WHERE session_id != ? AND observed_at BETWEEN ? AND ?",
                (session_id, first_at, last_at),
            )
        }
    )
    return Attribution(session_id, from_ts, until_ts, deltas, unmeasurable, parallel)


def run_collect(db_path: Path, child_cmd: Sequence[str] | None) -> int:
    """stdin의 statusLine payload를 표본으로 남긴 뒤 그대로 자식에게 넘긴다.

    `child_cmd`가 없으면 표본만 남기고 끝난다(tee 없이 계측만 쓰는 경우).
    """
    payload = sys.stdin.buffer.read()
    collect(payload, db_path)
    if not child_cmd:
        return 0
    try:
        proc = subprocess.run(list(child_cmd), input=payload, capture_output=True)
    except OSError as e:
        # 표본은 이미 남았다 — 여기서 죽으면 statusLine 화면이 사라져 표본 하나보다 비싸다
        print(f"자식 커맨드를 실행하지 못했다: {e}", file=sys.stderr)
        return 1
    sys.stdout.buffer.write(proc.stdout)
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(proc.stderr)
    sys.stderr.buffer.flush()
    return int(proc.returncode)

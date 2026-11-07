"""Small SQLite-backed state store (cue posteriors, perf events, online-model blobs).

Holds only pseudonymous patient_id (UUID) plus aggregates. No names, no media.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .clock import ensure_utc, iso, parse_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS cue_state (
  patient_id TEXT NOT NULL, cue_id TEXT NOT NULL, cue_type TEXT NOT NULL,
  aw REAL NOT NULL, bw REAL NOT NULL, ao REAL NOT NULL, bo REAL NOT NULL,
  half_life_days REAL NOT NULL, last_ts TEXT NOT NULL, n_obs INTEGER NOT NULL,
  valence_counts TEXT NOT NULL, last_label TEXT NOT NULL,
  PRIMARY KEY (patient_id, cue_id));
CREATE TABLE IF NOT EXISTS obs_seen (key TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS perf_event (
  id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT NOT NULL, ts TEXT NOT NULL,
  source TEXT NOT NULL, game_id TEXT, correct INTEGER NOT NULL, response_ms INTEGER,
  hints INTEGER NOT NULL DEFAULT 0, difficulty INTEGER, with_cue INTEGER);
CREATE INDEX IF NOT EXISTS ix_perf_patient_ts ON perf_event(patient_id, ts);
CREATE TABLE IF NOT EXISTS model_blob (key TEXT PRIMARY KEY, blob BLOB NOT NULL);
"""


@dataclass
class CueState:
    cue_id: str
    cue_type: str
    last_ts: datetime
    last_label: str
    aw: float = 1.0  # Beta prior (1,1): recall WITH cue
    bw: float = 1.0
    ao: float = 1.0  # Beta prior (1,1): recall WITHOUT cue
    bo: float = 1.0
    half_life_days: float = 30.0
    n_obs: int = 0
    valence_counts: dict[str, float] = field(default_factory=dict)


@dataclass
class PerfEvent:
    ts: datetime
    source: str  # 'game' | 'cue'
    correct: bool
    response_ms: int | None = None
    hints: int = 0
    difficulty: int | None = None
    with_cue: bool | None = None
    game_id: str | None = None


class Store:
    def __init__(self, path: str = ":memory:") -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        if path != ":memory:":
            self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)
        self._db.commit()

    def close(self) -> None:
        with self.lock:
            self._db.close()

    def commit(self) -> None:
        self._db.commit()

    # ------------------------------------------------------------- cues
    @staticmethod
    def _cue_from_row(r: sqlite3.Row) -> CueState:
        return CueState(
            cue_id=r["cue_id"], cue_type=r["cue_type"], last_ts=parse_iso(r["last_ts"]),
            last_label=r["last_label"], aw=r["aw"], bw=r["bw"], ao=r["ao"], bo=r["bo"],
            half_life_days=r["half_life_days"], n_obs=r["n_obs"],
            valence_counts=json.loads(r["valence_counts"]),
        )

    def get_cues(self, patient_id: str) -> list[CueState]:
        with self.lock:
            rows = self._db.execute("SELECT * FROM cue_state WHERE patient_id=?", (patient_id,)).fetchall()
        return [self._cue_from_row(r) for r in rows]

    def save_cue(self, patient_id: str, c: CueState) -> None:
        with self.lock:
            self._db.execute(
                "INSERT OR REPLACE INTO cue_state VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (patient_id, c.cue_id, c.cue_type, c.aw, c.bw, c.ao, c.bo, c.half_life_days,
                 iso(c.last_ts), c.n_obs, json.dumps(c.valence_counts), c.last_label),
            )

    # ----------------------------------------------------- idempotency
    def seen(self, key: str) -> bool:
        with self.lock:
            return self._db.execute("SELECT 1 FROM obs_seen WHERE key=?", (key,)).fetchone() is not None

    def mark_seen(self, key: str) -> None:
        with self.lock:
            self._db.execute("INSERT OR IGNORE INTO obs_seen VALUES (?)", (key,))

    # ------------------------------------------------------------- perf
    def add_perf(self, patient_id: str, events: list[PerfEvent]) -> None:
        with self.lock:
            self._db.executemany(
                "INSERT INTO perf_event (patient_id, ts, source, game_id, correct, response_ms, hints, difficulty, with_cue)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                [(patient_id, iso(e.ts), e.source, e.game_id, int(e.correct), e.response_ms, e.hints,
                  e.difficulty, None if e.with_cue is None else int(e.with_cue)) for e in events],
            )

    @staticmethod
    def _perf_from_row(r: sqlite3.Row) -> PerfEvent:
        return PerfEvent(
            ts=parse_iso(r["ts"]), source=r["source"], correct=bool(r["correct"]),
            response_ms=r["response_ms"], hints=r["hints"], difficulty=r["difficulty"],
            with_cue=None if r["with_cue"] is None else bool(r["with_cue"]), game_id=r["game_id"],
        )

    def perf_between(self, patient_id: str, start: datetime, end: datetime) -> list[PerfEvent]:
        with self.lock:
            rows = self._db.execute(
                "SELECT * FROM perf_event WHERE patient_id=? AND ts>=? AND ts<=? ORDER BY ts, id",
                (patient_id, iso(ensure_utc(start)), iso(ensure_utc(end))),
            ).fetchall()
        return [self._perf_from_row(r) for r in rows]

    def perf_earliest(self, patient_id: str, n: int) -> list[PerfEvent]:
        with self.lock:
            rows = self._db.execute(
                "SELECT * FROM perf_event WHERE patient_id=? ORDER BY ts, id LIMIT ?", (patient_id, n)
            ).fetchall()
        return [self._perf_from_row(r) for r in rows]

    # ------------------------------------------------------ model blobs
    def load_blob(self, key: str) -> bytes | None:
        with self.lock:
            r = self._db.execute("SELECT blob FROM model_blob WHERE key=?", (key,)).fetchone()
        return None if r is None else bytes(r["blob"])

    def save_blob(self, key: str, blob: bytes) -> None:
        with self.lock:
            self._db.execute("INSERT OR REPLACE INTO model_blob VALUES (?,?)", (key, blob))

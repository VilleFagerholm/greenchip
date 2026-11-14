"""Heat-loss event records, the bounded event file, and the daily summary (constitution V)."""

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from sentinel import config

END_REASONS = ("closed", "snoozed", "timed_out", "occupied")


@dataclass
class HeatLossEvent:
    start: str
    start_uptime_s: int
    sensitivity_c: float
    signals: list = field(default_factory=lambda: ["cold", "window"])
    duration_s: int = 0
    max_drop_c: float = 0.0
    degree_minutes: float = 0.0
    beeps: int = 0
    end_reason: str | None = None

    def record(self) -> dict:
        d = asdict(self)
        d["max_drop_c"] = round(self.max_drop_c, 1)
        d["degree_minutes"] = round(self.degree_minutes, 1)
        return d


def event_line(e: HeatLossEvent) -> str:
    return (f"EVENT end={e.end_reason} start={e.start} dur={e.duration_s}s max_drop={e.max_drop_c:.1f} "
            f"dm={e.degree_minutes:.1f} beeps={e.beeps} signals={','.join(e.signals)}")


@dataclass
class DailySummary:
    date: str
    events: int = 0
    total_minutes: float = 0.0
    degree_minutes: float = 0.0
    by_end_reason: dict = field(default_factory=lambda: {r: 0 for r in END_REASONS})
    clock_unsynced: bool = False

    def line(self) -> str:
        reasons = " ".join(f"{r}={self.by_end_reason.get(r, 0)}" for r in END_REASONS)
        return (f"SUMMARY date={self.date} events={self.events} minutes={self.total_minutes:.1f} "
                f"dm={self.degree_minutes:.1f} {reasons} clock_unsynced={int(self.clock_unsynced)}")


class EventLog:
    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "events.jsonl"
        self.old_path = Path(data_dir) / "events.1.jsonl"
        self._lines = self._count(self.path)

    @staticmethod
    def _count(path: Path) -> int:
        try:
            with path.open() as f:
                return sum(1 for _ in f)
        except OSError:
            return 0

    def append(self, event: HeatLossEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self._lines >= config.EVENTS_MAX_LINES:
            os.replace(self.path, self.old_path)
            self._lines = 0
        with self.path.open("a") as f:
            f.write(json.dumps(event.record()) + "\n")
        self._lines += 1

    def _records(self):
        for path in (self.old_path, self.path):
            try:
                with path.open() as f:
                    for line in f:
                        try:
                            yield json.loads(line)
                        except ValueError:
                            continue
            except OSError:
                continue

    def summary_today(self, now: datetime) -> DailySummary:
        today = now.date().isoformat()
        s = DailySummary(date=today, clock_unsynced=now.year < config.CLOCK_VALID_YEAR)
        for r in self._records():
            if not isinstance(r, dict) or not str(r.get("start", "")).startswith(today):
                continue
            s.events += 1
            s.total_minutes += float(r.get("duration_s", 0)) / 60
            s.degree_minutes += float(r.get("degree_minutes", 0))
            reason = r.get("end_reason")
            if reason in s.by_end_reason:
                s.by_end_reason[reason] += 1
        return s

    def recent_today(self, now: datetime, limit: int | None = None) -> list[dict]:
        """Newest-first short list of today's events for the dashboard (derived fields only)."""
        limit = config.UI_RECENT_EVENTS if limit is None else limit
        today = now.date().isoformat()
        rows = []
        for r in self._records():
            if not isinstance(r, dict) or not str(r.get("start", "")).startswith(today):
                continue
            rows.append({
                "start": r.get("start"),
                "duration_s": int(r.get("duration_s", 0) or 0),
                "max_drop_c": float(r.get("max_drop_c", 0) or 0),
                "degree_minutes": float(r.get("degree_minutes", 0) or 0),
                "end_reason": r.get("end_reason"),
            })
        rows.reverse()
        return rows[:limit]

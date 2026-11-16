"""Training-load maths and the plain records the coach reasons over. Pure: no session, no I/O.

Load uses a TSS-like scale (1 hour at threshold is about 100):
  1. heart rate with known max and resting HR  -> TRIMP normalised to threshold heart rate
  2. a run with pace and a known threshold pace -> rTSS (hours x intensity^2 x 100)
  3. otherwise                                   -> a duration-based estimate
Fitness (CTL) is the 42-day exponentially weighted average of daily load, fatigue (ATL) the
7-day one, and form (TSB) yesterday's fitness minus yesterday's fatigue.
"""

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta


@dataclass(frozen=True)
class LapSummary:
    """One lap of a session."""

    distance_m: float | None
    seconds: float | None
    avg_hr: int | None
    intensity: str | None


@dataclass
class TrainingSession:
    """One activity in the athlete's local time, with its computed load."""

    activity_id: int
    local_start: datetime
    type_name: str
    is_run: bool
    name: str
    distance_m: float
    moving_s: float
    elevation_m: int | None
    avg_hr: int | None
    max_hr: int | None
    avg_speed: float | None
    rpe: int | None
    description: str | None
    private_notes: str | None
    laps: list[LapSummary] = field(default_factory=list)
    load: float = 0.0

    @property
    def local_date(self) -> date:
        """The calendar day the session started on, in the athlete's time zone."""
        return self.local_start.date()


@dataclass(frozen=True)
class SleepNight:
    """One night of sleep and recovery data."""

    night: date
    total_sleep_s: int | None
    sleep_score: int | None
    resting_hr: int | None
    hrv_status: str | None
    avg_stress: int | None
    skin_temp_deviation: float | None


@dataclass(frozen=True)
class AthleteBasics:
    """Physiology needed for load: from the coach profile, falling back to synced data."""

    max_hr: int | None
    rest_hr: int | None
    female: bool
    threshold_pace_s_per_km: int | None


def _trimp(minutes: float, hrr: float, female: bool) -> float:
    a, b = (0.86, 1.67) if female else (0.64, 1.92)
    return minutes * hrr * a * math.exp(b * hrr)


def session_load(session: TrainingSession, basics: AthleteBasics) -> float:
    """Return the session's load on the TSS-like scale.

    Args:
        session: The session.
        basics: The athlete's heart-rate and pace anchors.

    Returns:
        The load, rounded to one decimal.
    """
    minutes = session.moving_s / 60
    if minutes <= 0:
        return 0.0
    if session.avg_hr and basics.max_hr and basics.rest_hr and basics.max_hr > basics.rest_hr:
        hrr = max(0.0, min(1.0, (session.avg_hr - basics.rest_hr) / (basics.max_hr - basics.rest_hr)))
        return round(_trimp(minutes, hrr, basics.female) / _trimp(60, 0.86, basics.female) * 100, 1)
    if session.is_run and basics.threshold_pace_s_per_km and session.avg_speed:
        intensity = basics.threshold_pace_s_per_km / (1000 / session.avg_speed)
        return round(minutes / 60 * intensity**2 * 100, 1)
    return round(minutes * (0.75 if session.is_run else 0.5), 1)


def load_series(sessions: list[TrainingSession], today: date, days: int) -> list[dict]:
    """Return fitness, fatigue and form per day for the last ``days`` days.

    Args:
        sessions: Sessions with their load set; older history makes the values realistic.
        today: Last day of the series.
        days: Number of days returned.

    Returns:
        Dicts with ``date``, ``load``, ``ctl``, ``atl`` and ``tsb``, oldest first.
    """
    per_day: dict[date, float] = defaultdict(float)
    for s in sessions:
        per_day[s.local_date] += s.load
    if not per_day:
        return []
    k_ctl, k_atl = 1 - math.exp(-1 / 42), 1 - math.exp(-1 / 7)
    ctl = atl = 0.0
    out = []
    d = min(per_day)
    while d <= today:
        tsb = ctl - atl
        load = per_day.get(d, 0.0)
        ctl += (load - ctl) * k_ctl
        atl += (load - atl) * k_atl
        out.append(
            {"date": d, "load": round(load, 1), "ctl": round(ctl, 1), "atl": round(atl, 1), "tsb": round(tsb, 1)}
        )
        d += timedelta(days=1)
    return out[-days:]


def week_start(d: date) -> date:
    """Return the Monday of the week containing ``d``."""
    return d - timedelta(days=d.weekday())


def weekly_summary(sessions: list[TrainingSession], today: date, weeks: int) -> list[dict]:
    """Return per-week running totals for the last ``weeks`` weeks, current week last.

    Args:
        sessions: Sessions to total.
        today: A day in the last week.
        weeks: Number of weeks.

    Returns:
        Dicts with week start, run km, run count, run hours, longest run, elevation,
        other-sport hours, load and time-weighted average run heart rate.
    """
    first = week_start(today) - timedelta(weeks=weeks - 1)
    buckets = {
        first + timedelta(weeks=i): {
            "week": first + timedelta(weeks=i),
            "run_km": 0.0,
            "runs": 0,
            "run_hours": 0.0,
            "long_km": 0.0,
            "elev_m": 0.0,
            "other_hours": 0.0,
            "load": 0.0,
            "_hr": 0.0,
            "_hr_h": 0.0,
        }
        for i in range(weeks)
    }
    for s in sessions:
        b = buckets.get(week_start(s.local_date))
        if b is None:
            continue
        hours = s.moving_s / 3600
        b["load"] += s.load
        if s.is_run:
            km = s.distance_m / 1000
            b["run_km"] += km
            b["runs"] += 1
            b["run_hours"] += hours
            b["long_km"] = max(b["long_km"], km)
            b["elev_m"] += s.elevation_m or 0
            if s.avg_hr:
                b["_hr"] += s.avg_hr * hours
                b["_hr_h"] += hours
        else:
            b["other_hours"] += hours
    out = []
    for b in buckets.values():
        b["avg_run_hr"] = round(b["_hr"] / b["_hr_h"]) if b["_hr_h"] else None
        del b["_hr"], b["_hr_h"]
        for k in ("run_km", "run_hours", "long_km", "elev_m", "other_hours", "load"):
            b[k] = round(b[k], 1)
        out.append(b)
    return out


def fmt_pace(seconds_per_km: float | None) -> str:
    """Format seconds per km as ``m:ss/km``."""
    if not seconds_per_km:
        return "-"
    total = round(seconds_per_km)
    return f"{total // 60}:{total % 60:02d}/km"


def pace_from_speed(speed_m_s: float | None) -> float | None:
    """Convert m/s to seconds per km."""
    return 1000 / speed_m_s if speed_m_s else None


def fmt_duration(seconds: float | None) -> str:
    """Format seconds as ``h:mm:ss`` or ``m:ss``."""
    if not seconds:
        return "-"
    seconds = round(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

"""Builds the context pack: everything the coach knows, as Markdown. Pure: inputs in, text out.

Sections: athlete, goals and races, today, recovery, training load, 16-week history, previous plan
versus what happened, the plan on the calendar, recent sessions in detail, check-ins and the
coach's own long-term notes.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import modules.coach.constants as coach_constants
import modules.coach.metrics as coach_metrics
import modules.coach.schema as coach_schema

#: Below this average weekly load (28 days) the acute:chronic ratio is noise.
MIN_WEEKLY_LOAD_FOR_ACWR = 100


@dataclass(frozen=True)
class ContextInputs:
    """Everything the pack is built from."""

    now_local: datetime
    timezone: str
    athlete_name: str
    birthdate: date | None
    gender: str | None
    profile: coach_schema.CoachProfileRead
    resolved_rest_hr: int | None
    races: list[coach_schema.CoachRaceRead]
    sessions: list[coach_metrics.TrainingSession]
    sleep: list[coach_metrics.SleepNight]
    checkins: list[coach_schema.CoachCheckinRead]
    plan_by_date: dict[date, coach_schema.CoachWorkout]


def day_status(
    workout: coach_schema.CoachWorkout | None, done: list[coach_metrics.TrainingSession], *, past: bool
) -> str | None:
    """Compare one planned day with what was recorded.

    Args:
        workout: The planned workout, if any.
        done: Sessions recorded that day.
        past: Whether the day is over.

    Returns:
        done, partial, over, missed, rest, extra or pending; ``None`` when nothing was planned.
    """
    if workout is None:
        return None
    if workout.sport == "rest":
        return "extra" if done else "rest"
    if not done:
        return "missed" if past else "pending"
    km = sum(s.distance_m for s in done if s.is_run) / 1000
    minutes = sum(s.moving_s for s in done) / 60
    if workout.distance_km:
        ratio = km / workout.distance_km
    elif workout.duration_min:
        ratio = minutes / workout.duration_min
    else:
        ratio = 1.0
    if ratio > 1.3:
        return "over"
    return "done" if ratio >= 0.8 else "partial"


def _session_line(s: coach_metrics.TrainingSession) -> str:
    parts = [
        f'**{s.local_start:%a %Y-%m-%d %H:%M}** {s.type_name} - "{s.name}"',
        f"{s.distance_m / 1000:.1f} km" if s.distance_m else None,
        coach_metrics.fmt_duration(s.moving_s),
        coach_metrics.fmt_pace(coach_metrics.pace_from_speed(s.avg_speed)) if s.is_run else None,
        f"HR {s.avg_hr}/{s.max_hr}" if s.avg_hr and s.max_hr else None,
        f"+{s.elevation_m} m" if s.elevation_m else None,
        f"RPE {s.rpe}/10" if s.rpe else None,
        f"load {s.load:.0f}" if s.load else None,
    ]
    return " | ".join(p for p in parts if p)


def _session_details(s: coach_metrics.TrainingSession) -> list[str]:
    lines = []
    for label, text in (("Athlete's description", s.description), ("Private note", s.private_notes)):
        if text and text.strip():
            lines.append(f"  - {label}: {text.strip()[:600]}")
    if 1 < len(s.laps) <= 40:
        laps = []
        for lap in s.laps:
            pace = lap.seconds / (lap.distance_m / 1000) if lap.seconds and lap.distance_m else None
            bits = f"{(lap.distance_m or 0) / 1000:.2f}km@{coach_metrics.fmt_pace(pace).removesuffix('/km')}"
            if lap.avg_hr:
                bits += f" HR{lap.avg_hr}"
            if lap.intensity and lap.intensity != "active":
                bits += f" ({lap.intensity})"
            laps.append(bits)
        lines.append("  - Laps: " + "; ".join(laps))
    return lines


def _workout_line(d: date, w: coach_schema.CoachWorkout) -> str:
    bits = [f"{w.type}: {w.title}"]
    if w.distance_km:
        bits.append(f"{w.distance_km} km")
    if w.duration_min:
        bits.append(f"{w.duration_min} min")
    if w.target:
        bits.append(f"target {w.target}")
    return f"- {d:%a %Y-%m-%d}: " + ", ".join(bits) + (" [KEY]" if w.key else "")


def build(inputs: ContextInputs) -> str:
    """Return the context pack.

    Args:
        inputs: The athlete's data.

    Returns:
        The context pack as Markdown.
    """
    today = inputs.now_local.date()
    p = inputs.profile
    out: list[str] = [f"# Context pack - {inputs.now_local:%A %Y-%m-%d %H:%M} ({inputs.timezone})", ""]
    add = out.append

    # Athlete
    add("## Athlete")
    age = None
    if inputs.birthdate:
        age = (
            today.year
            - inputs.birthdate.year
            - ((today.month, today.day) < (inputs.birthdate.month, inputs.birthdate.day))
        )
    facts = {
        "Name": inputs.athlete_name,
        "Age": age,
        "Gender": inputs.gender,
        "Max HR": p.max_hr,
        "Resting HR": inputs.resolved_rest_hr,
        "Threshold pace": coach_metrics.fmt_pace(p.threshold_pace_s_per_km) if p.threshold_pace_s_per_km else None,
        "Running background": p.experience,
        "Available training days": ", ".join(p.available_days) if p.available_days else None,
        "Preferred long-run day": p.long_run_day,
        "Max training hours per week": p.max_weekly_hours,
        "Injuries / health": p.health,
        "Preferences": p.preferences,
        "Life schedule / constraints": p.constraints,
    }
    for key, value in facts.items():
        if value not in (None, ""):
            add(f"- {key}: {value}")
    add("")

    # Goals
    add("## Goals and race calendar")
    if p.primary_goal:
        add(f"Main goal (athlete's words): {p.primary_goal}")
    races = sorted(inputs.races, key=lambda r: r.race_date)
    for r in races:
        days = (r.race_date - today).days
        when = f"in {days} days ({days / 7:.1f} weeks)" if days >= 0 else f"{-days} days ago"
        line = f"- [{r.priority}] {r.name} - {r.race_date} ({when}), {r.distance_km or '?'} km, target {r.target_time or 'none set'}"
        add(line + (f". Notes: {r.notes}" if r.notes else ""))
    if not races and not p.primary_goal:
        add("- No goals set. Build durable aerobic fitness and suggest the athlete sets a goal.")
    add("")

    # Today
    add("## Today")
    add(f"Today is {today:%A %Y-%m-%d}. Weeks start on Monday.")
    upcoming = [r for r in races if r.race_date >= today]
    a_races = [r for r in upcoming if r.priority == "A"] or upcoming
    if a_races:
        add(f"Next A-race: {a_races[0].name} in {(a_races[0].race_date - today).days} days.")
    todays = [s for s in inputs.sessions if s.local_date == today]
    if todays:
        add("Already done today: " + "; ".join(f"{s.name} ({s.distance_m / 1000:.1f} km)" for s in todays))
    else:
        add("Nothing recorded yet today.")
    add("")

    # Recovery
    add(f"## Sleep and recovery (last {coach_constants.RECOVERY_NIGHTS} nights, from the watch)")
    if inputs.sleep:
        add("| Night | Sleep | Score | Resting HR | HRV status | Stress | Skin temp dev |")
        add("|---|---|---|---|---|---|---|")
        for n in sorted(inputs.sleep, key=lambda n: n.night):
            sleep = coach_metrics.fmt_duration(n.total_sleep_s)[:-3] if n.total_sleep_s else "-"
            add(
                f"| {n.night:%a %m-%d} | {sleep} | {n.sleep_score or '-'} | {n.resting_hr or '-'} | "
                f"{n.hrv_status or '-'} | {n.avg_stress or '-'} | "
                f"{'-' if n.skin_temp_deviation is None else f'{n.skin_temp_deviation:+.1f}'} |"
            )
    else:
        add("- No sleep data synced.")
    add("")

    # Load
    series = coach_metrics.load_series(inputs.sessions, today, days=56)
    if series:
        cur = series[-1]
        week_ago = series[-8] if len(series) >= 8 else series[0]
        month_ago = series[-29] if len(series) >= 29 else series[0]
        add("## Training load (TSS-like units; CTL = fitness 42 d, ATL = fatigue 7 d, TSB = form)")
        add(f"- Now: CTL {cur['ctl']}, ATL {cur['atl']}, TSB {cur['tsb']}")
        add(f"- 7 days ago CTL {week_ago['ctl']}; 28 days ago CTL {month_ago['ctl']}")
        add(f"- CTL change over 7 days: {cur['ctl'] - week_ago['ctl']:+.1f} (sustained > +5/week raises injury risk)")
        acute = sum(x["load"] for x in series[-7:])
        chronic = sum(x["load"] for x in series[-28:]) / 4
        if chronic >= MIN_WEEKLY_LOAD_FOR_ACWR:
            add(f"- Acute:chronic workload ratio {acute / chronic:.2f} (0.8-1.3 is the sweet spot, > 1.5 a red flag)")
        else:
            add("- Acute:chronic ratio not shown: too little recent training for it to mean anything")
        add("- Daily load, last 14 days: " + ", ".join(f"{x['date']:%m-%d}:{x['load']:.0f}" for x in series[-14:]))
        add("")

    # History
    add("## Weekly history (16 weeks, current week last and partial)")
    add("| Week of | Run km | Runs | Run h | Longest km | Elev m | Other h | Load | Avg run HR |")
    add("|---|---|---|---|---|---|---|---|---|")
    for w in coach_metrics.weekly_summary(inputs.sessions, today, weeks=16):
        add(
            f"| {w['week']} | {w['run_km']} | {w['runs']} | {w['run_hours']} | {w['long_km']} | "
            f"{w['elev_m']:.0f} | {w['other_hours']} | {w['load']:.0f} | {w['avg_run_hr'] or '-'} |"
        )
    add("")

    # Plan versus reality
    by_day: dict[date, list[coach_metrics.TrainingSession]] = {}
    for s in inputs.sessions:
        by_day.setdefault(s.local_date, []).append(s)
    past = sorted(d for d in inputs.plan_by_date if today - timedelta(days=14) <= d < today)
    if past:
        add("## Your previous plan vs what happened (last 14 days)")
        for d in past:
            w = inputs.plan_by_date[d]
            done = by_day.get(d, [])
            status = day_status(w, done, past=True)
            km = sum(s.distance_m for s in done if s.is_run) / 1000
            mins = sum(s.moving_s for s in done) / 60
            names = "; ".join(s.name for s in done)
            add(
                f'- {d} planned {w.type} "{w.title}" ({w.distance_km or "-"} km / {w.duration_min or "-"} min)'
                f" -> {str(status).upper()}: {km:.1f} km, {mins:.0f} min" + (f" ({names})" if names else "")
            )
        add("")
    future = sorted(d for d in inputs.plan_by_date if d >= today)
    if future:
        add("## Plan currently on the athlete's calendar (from your last update)")
        out.extend(_workout_line(d, inputs.plan_by_date[d]) for d in future)
        add("Keep continuity: change sessions only when the data or check-ins give a reason, and say why.")
        add("")

    # Recent sessions
    add(f"## All sessions in the last {coach_constants.RECENT_DETAIL_DAYS} days (newest last)")
    cutoff = today - timedelta(days=coach_constants.RECENT_DETAIL_DAYS)
    recent = [s for s in inputs.sessions if s.local_date >= cutoff]
    if not recent:
        add("- None recorded.")
    for s in recent:
        add("- " + _session_line(s))
        out.extend(_session_details(s))
    add("")

    # Check-ins
    add("## Athlete check-ins (free-text notes from the athlete, last 21 days)")
    if inputs.checkins:
        out.extend(f"- {c.created_at:%Y-%m-%d %H:%M}: {c.text}" for c in inputs.checkins)
    else:
        add("- None.")
    add("")

    add("## Your own long-term notes about this athlete (written by you on earlier updates)")
    add(p.coach_notes or "(empty: this is the first update, start your notes)")
    return "\n".join(out)

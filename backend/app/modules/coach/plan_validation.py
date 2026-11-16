"""Checks that a plan is complete and that every workout's steps can drive a device. Pure."""

from collections.abc import Iterator
from datetime import date, timedelta

import modules.coach.constants as coach_constants
import modules.coach.schema as coach_schema

_OPEN_ALLOWED = {"warmup", "recovery", "cooldown", "rest"}
_PACE_RANGE = (150, 900)
_HR_RANGE = (60, 230)


def _flatten(
    steps: list[coach_schema.CoachWorkoutStep | coach_schema.CoachRepeat | coach_schema.CoachInnerRepeat],
    times: int = 1,
) -> Iterator[tuple[coach_schema.CoachWorkoutStep, int]]:
    """Yield each step with how many times it runs."""
    for item in steps:
        if isinstance(item, coach_schema.CoachWorkoutStep):
            yield item, times
        else:
            yield from _flatten(list(item.steps), times * max(item.count, 0))


def _step_issues(step: coach_schema.CoachWorkoutStep) -> list[str]:
    issues = []
    if step.duration_type == "open":
        if step.kind not in _OPEN_ALLOWED:
            issues.append(f"'{step.kind}' step cannot have an open duration")
    elif not step.duration_value or step.duration_value <= 0:
        issues.append(f"{step.duration_type} step needs a positive duration_value")

    lo, hi = step.target_low, step.target_high
    if step.target_type == "none":
        return issues
    if lo is None or hi is None or lo > hi:
        issues.append(f"{step.target_type} target needs target_low <= target_high")
        return issues
    if step.target_type == "pace" and not (_PACE_RANGE[0] <= lo and hi <= _PACE_RANGE[1]):
        issues.append(f"pace target {lo:.0f}-{hi:.0f} s/km is outside {_PACE_RANGE[0]}-{_PACE_RANGE[1]}")
    if step.target_type in ("hr", "hr_zone") and not (_HR_RANGE[0] <= lo and hi <= _HR_RANGE[1]):
        issues.append(f"heart-rate target {lo:.0f}-{hi:.0f} bpm is outside {_HR_RANGE[0]}-{_HR_RANGE[1]}")
    if step.target_type == "hr_zone" and step.zone is None:
        issues.append("hr_zone target needs a zone number")
    if step.target_type == "rpe" and not (lo >= 1 and hi <= 10):
        issues.append("rpe target must be within 1-10")
    return issues


def _totals(workout: coach_schema.CoachWorkout) -> tuple[float | None, float | None]:
    """Estimated total meters and seconds from the steps, or None where a step cannot tell."""
    meters: float | None = 0.0
    seconds: float | None = 0.0
    for step, times in _flatten(list(workout.steps)):
        mid_pace = (
            (step.target_low + step.target_high) / 2
            if step.target_type == "pace" and step.target_low and step.target_high
            else None
        )
        if step.duration_type == "distance" and step.duration_value:
            m, s = step.duration_value, (step.duration_value / 1000 * mid_pace if mid_pace else None)
        elif step.duration_type == "time" and step.duration_value:
            s, m = step.duration_value, (step.duration_value / mid_pace * 1000 if mid_pace else None)
        else:
            m = s = None
        meters = None if meters is None or m is None else meters + m * times
        seconds = None if seconds is None or s is None else seconds + s * times
    return meters, seconds


def workout_issues(workout: coach_schema.CoachWorkout) -> list[str]:
    """Return problems with one workout's device-neutral steps.

    Args:
        workout: The planned workout.

    Returns:
        Human-readable issues, empty when the workout is usable.
    """
    if workout.sport == "rest":
        return ["rest day must not have steps"] if workout.steps else []
    if not workout.steps:
        return ["non-rest workout needs steps"]
    issues: list[str] = []
    for step, _ in _flatten(list(workout.steps)):
        issues.extend(_step_issues(step))
        if workout.sport == "run" and step.kind == "active" and step.target_type == "none":
            issues.append(
                "active running steps need a pace, hr, hr_zone or rpe target (use a repeat block for intervals)"
            )
    for item in workout.steps:
        if not isinstance(item, coach_schema.CoachWorkoutStep) and item.count < 1:
            issues.append("repeat count must be at least 1")
    meters, seconds = _totals(workout)
    tol = coach_constants.STEP_TOTAL_TOLERANCE
    if (
        workout.distance_km
        and meters is not None
        and abs(meters / 1000 - workout.distance_km) > tol * workout.distance_km
    ):
        issues.append(f"steps add up to {meters / 1000:.1f} km but distance_km is {workout.distance_km}")
    if (
        workout.duration_min
        and seconds is not None
        and abs(seconds / 60 - workout.duration_min) > tol * workout.duration_min
    ):
        issues.append(f"steps add up to {seconds / 60:.0f} min but duration_min is {workout.duration_min}")
    return issues


def plan_issues(report: coach_schema.CoachReportOutput, today: date) -> list[str]:
    """Return problems with the whole plan: coverage of the 14 days and each workout.

    Args:
        report: The model's report.
        today: The athlete's local today.

    Returns:
        Issues prefixed with the date they concern; empty when the plan is usable.
    """
    expected = [(today + timedelta(days=i)).isoformat() for i in range(coach_constants.PLAN_DAYS)]
    dates = [w.date for w in report.plan]
    issues = []
    missing = [d for d in expected if d not in dates]
    if missing:
        issues.append(f"plan is missing days: {', '.join(missing)}")
    duplicates = sorted({d for d in dates if dates.count(d) > 1})
    if duplicates:
        issues.append(f"plan has more than one entry for: {', '.join(duplicates)}")
    for w in report.plan:
        if w.date in expected:
            issues.extend(f"{w.date}: {i}" for i in workout_issues(w))
    return issues

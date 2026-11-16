"""Builders for coach test data."""

from datetime import UTC, date, datetime, timedelta

import modules.coach.metrics as coach_metrics
import modules.coach.schema as coach_schema


def step(**overrides) -> coach_schema.CoachWorkoutStep:
    values = {
        "kind": "active",
        "duration_type": "distance",
        "duration_value": 1000.0,
        "target_type": "pace",
        "target_low": 300.0,
        "target_high": 320.0,
        "zone": None,
        "note": "",
    }
    values.update(overrides)
    return coach_schema.CoachWorkoutStep(**values)


def easy_run(day: date, km: float = 10, pace: tuple[float, float] = (330, 350)) -> coach_schema.CoachWorkout:
    minutes = round(km * sum(pace) / 2 / 60)
    return coach_schema.CoachWorkout(
        date=day.isoformat(),
        type="easy",
        sport="run",
        title=f"Easy {km} km",
        distance_km=km,
        duration_min=minutes,
        target="easy",
        structure="steady",
        purpose="aerobic base",
        key=False,
        steps=[step(duration_value=km * 1000, target_low=pace[0], target_high=pace[1])],
    )


def intervals(day: date) -> coach_schema.CoachWorkout:
    return coach_schema.CoachWorkout(
        date=day.isoformat(),
        type="intervals",
        sport="run",
        title="6 x 1 km",
        distance_km=10,
        duration_min=55,
        target="4:10-4:15/km",
        structure="wu, 6 x 1 km, cd",
        purpose="threshold",
        key=True,
        steps=[
            step(
                kind="warmup",
                duration_type="time",
                duration_value=900,
                target_type="hr",
                target_low=120,
                target_high=145,
            ),
            coach_schema.CoachRepeat(
                kind="repeat",
                count=6,
                steps=[
                    step(target_low=250, target_high=255),
                    step(
                        kind="recovery",
                        duration_type="open",
                        duration_value=None,
                        target_type="none",
                        target_low=None,
                        target_high=None,
                    ),
                ],
            ),
            step(
                kind="cooldown",
                duration_type="time",
                duration_value=600,
                target_type="none",
                target_low=None,
                target_high=None,
            ),
        ],
    )


def rest_day(day: date) -> coach_schema.CoachWorkout:
    return coach_schema.CoachWorkout(
        date=day.isoformat(),
        type="rest",
        sport="rest",
        title="Rest",
        distance_km=None,
        duration_min=None,
        target="",
        structure="",
        purpose="recover",
        key=False,
        steps=[],
    )


def report_for(today: date) -> coach_schema.CoachReportOutput:
    plan = []
    for i in range(14):
        d = today + timedelta(days=i)
        plan.append(rest_day(d) if i % 3 == 2 else (intervals(d) if i % 7 == 1 else easy_run(d)))
    return coach_schema.CoachReportOutput(
        headline="Steady week",
        today_summary="Easy run today.",
        readiness=coach_schema.CoachReadiness(status="ready", note="Slept well."),
        recent_assessment="Consistent.",
        phase="Base 1 of 3",
        week_focus="Volume",
        plan=plan,
        plan_changes="",
        goal_progress=[
            coach_schema.CoachGoalProgress(race="Spring Half", on_track="on_track", predicted="1:40", summary="Fine.")
        ],
        flags=[],
        tips=["Sleep"],
        coach_notes="Responds well to volume.",
    )


def session(day: date, **overrides) -> coach_metrics.TrainingSession:
    values = {
        "activity_id": 1,
        "local_start": datetime(day.year, day.month, day.day, 7, 0, tzinfo=UTC),
        "type_name": "Run",
        "is_run": True,
        "name": "Morning run",
        "distance_m": 10000.0,
        "moving_s": 3300.0,
        "elevation_m": 50,
        "avg_hr": 145,
        "max_hr": 160,
        "avg_speed": 1000 / 330,
        "rpe": 3,
        "description": None,
        "private_notes": None,
    }
    values.update(overrides)
    return coach_metrics.TrainingSession(**values)

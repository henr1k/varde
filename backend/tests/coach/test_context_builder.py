"""Tests for the context pack and day status."""

from datetime import UTC, date, datetime, timedelta

import pytest

import modules.coach.context_builder as context_builder
import modules.coach.metrics as coach_metrics
import modules.coach.schema as coach_schema
from tests.coach.factories import easy_run, rest_day, session

TODAY = date(2026, 11, 16)


def _profile(**overrides) -> coach_schema.CoachProfileRead:
    values = {"user_id": 1, "enabled": True, "max_hr": 190, "primary_goal": "Sub-1:40 half", "coach_notes": None}
    values.update(overrides)
    return coach_schema.CoachProfileRead(**values)


def _inputs(**overrides) -> context_builder.ContextInputs:
    sessions = sorted(
        (session(TODAY - timedelta(days=i), activity_id=i + 1) for i in range(1, 60, 2)), key=lambda s: s.local_start
    )
    for s in sessions:
        s.load = 60
    sessions[-1].description = "Felt strong"
    sessions[-1].laps = [
        coach_metrics.LapSummary(1000, 250, 170, "active"),
        coach_metrics.LapSummary(400, 180, 140, "rest"),
    ]
    values = {
        "now_local": datetime(2026, 11, 16, 6, 0, tzinfo=UTC),
        "timezone": "Europe/Oslo",
        "athlete_name": "Kari",
        "birthdate": date(1990, 6, 1),
        "gender": "female",
        "profile": _profile(),
        "resolved_rest_hr": 48,
        "races": [
            coach_schema.CoachRaceRead(
                id=1, name="Spring Half", race_date=TODAY + timedelta(days=120), distance_km=21.1
            )
        ],
        "sessions": sessions,
        "sleep": [coach_metrics.SleepNight(TODAY - timedelta(days=1), 27000, 82, 47, "balanced", 20, -0.2)],
        "checkins": [
            coach_schema.CoachCheckinRead(
                id=1, text="Calf a bit tight", created_at=datetime(2026, 11, 15, 20, 0, tzinfo=UTC)
            )
        ],
        "plan_by_date": {
            TODAY - timedelta(days=1): easy_run(TODAY - timedelta(days=1), km=10),
            TODAY - timedelta(days=2): easy_run(TODAY - timedelta(days=2), km=8),
            TODAY: easy_run(TODAY, km=8),
        },
    }
    values.update(overrides)
    return context_builder.ContextInputs(**values)


class TestBuild:
    def test_includes_every_section_and_the_athletes_words(self):
        md = context_builder.build(_inputs())
        for heading in (
            "## Athlete",
            "## Goals and race calendar",
            "## Today",
            "## Sleep and recovery",
            "## Training load",
            "## Weekly history",
            "## Your previous plan vs what happened",
            "## Plan currently on the athlete's calendar",
            "## All sessions in the last 21 days",
            "## Athlete check-ins",
            "## Your own long-term notes",
        ):
            assert heading in md
        assert "Age: 36" in md
        assert "Spring Half" in md and "in 120 days" in md
        assert "Felt strong" in md
        assert "1.00km@4:10 HR170" in md and "(rest)" in md
        assert "Calf a bit tight" in md
        assert "balanced" in md
        assert "Acute:chronic workload ratio" in md

    def test_sparse_history_hides_the_workload_ratio_and_suggests_goals(self):
        md = context_builder.build(
            _inputs(sessions=[], sleep=[], checkins=[], races=[], plan_by_date={}, profile=_profile(primary_goal=None))
        )
        assert "No sleep data synced" in md
        assert "No goals set" in md
        assert "None recorded" in md
        assert "Acute:chronic workload ratio" not in md

    def test_low_volume_hides_the_workload_ratio(self):
        lone = session(TODAY - timedelta(days=3))
        lone.load = 40
        md = context_builder.build(_inputs(sessions=[lone]))
        assert "too little recent training" in md


class TestDayStatus:
    @pytest.mark.parametrize(
        ("km", "past", "expected"),
        [
            (10, True, "done"),
            (5, True, "partial"),
            (14, True, "over"),
            (None, True, "missed"),
            (None, False, "pending"),
        ],
    )
    def test_run_day(self, km, past, expected):
        done = [session(TODAY, distance_m=km * 1000)] if km else []
        assert context_builder.day_status(easy_run(TODAY, km=10), done, past=past) == expected

    def test_rest_day_and_unplanned_day(self):
        assert context_builder.day_status(rest_day(TODAY), [], past=True) == "rest"
        assert context_builder.day_status(rest_day(TODAY), [session(TODAY)], past=True) == "extra"
        assert context_builder.day_status(None, [session(TODAY)], past=True) is None

    def test_duration_only_workout_compares_minutes(self):
        w = easy_run(TODAY).model_copy(update={"distance_km": None, "duration_min": 60})
        assert context_builder.day_status(w, [session(TODAY, moving_s=3600)], past=True) == "done"

"""Tests for the device-neutral plan checks."""

from datetime import date, timedelta

import pytest

import modules.coach.plan_validation as plan_validation
import modules.coach.schema as coach_schema
from tests.coach.factories import easy_run, intervals, report_for, rest_day, step

TODAY = date(2026, 11, 16)


class TestWorkoutIssues:
    def test_easy_run_with_matching_steps_is_valid(self):
        assert plan_validation.workout_issues(easy_run(TODAY, km=10, pace=(330, 350))) == []

    def test_intervals_with_open_recoveries_skip_the_total_check(self):
        assert plan_validation.workout_issues(intervals(TODAY)) == []

    def test_rest_day_must_not_have_steps(self):
        w = rest_day(TODAY).model_copy(update={"steps": [step()]})
        assert plan_validation.workout_issues(w) == ["rest day must not have steps"]

    def test_run_without_steps_is_rejected(self):
        w = easy_run(TODAY).model_copy(update={"steps": []})
        assert plan_validation.workout_issues(w) == ["non-rest workout needs steps"]

    def test_open_active_step_is_rejected(self):
        w = easy_run(TODAY).model_copy(update={"steps": [step(duration_type="open", duration_value=None)]})
        assert "'active' step cannot have an open duration" in plan_validation.workout_issues(w)

    def test_distance_mismatch_is_reported(self):
        w = easy_run(TODAY, km=10).model_copy(update={"distance_km": 14})
        assert any("add up to 10.0 km" in i for i in plan_validation.workout_issues(w))

    def test_duration_mismatch_is_reported(self):
        w = easy_run(TODAY, km=10, pace=(300, 300)).model_copy(update={"duration_min": 80})
        assert any("add up to 50 min" in i for i in plan_validation.workout_issues(w))

    @pytest.mark.parametrize(
        ("target_type", "low", "high", "zone", "expected"),
        [
            ("pace", 100, 120, None, "outside 150-900"),
            ("hr", 40, 50, None, "outside 60-230"),
            ("hr_zone", 130, 145, None, "needs a zone number"),
            ("rpe", 0, 12, None, "within 1-10"),
            ("pace", 360, 300, None, "target_low <= target_high"),
        ],
    )
    def test_bad_targets_are_reported(self, target_type, low, high, zone, expected):
        bad = step(target_type=target_type, target_low=low, target_high=high, zone=zone)
        w = easy_run(TODAY).model_copy(update={"steps": [bad], "distance_km": None, "duration_min": None})
        assert any(expected in i for i in plan_validation.workout_issues(w))

    def test_repeat_count_must_be_positive(self):
        w = intervals(TODAY)
        broken = w.steps[1].model_copy(update={"count": 0})
        w = w.model_copy(update={"steps": [w.steps[0], broken, w.steps[2]]})
        assert "repeat count must be at least 1" in plan_validation.workout_issues(w)

    def test_nested_repeat_totals_count_every_repetition(self):
        inner = coach_schema.CoachInnerRepeat(
            kind="repeat",
            count=4,
            steps=[step(duration_type="distance", duration_value=400, target_low=240, target_high=250)],
        )
        outer = coach_schema.CoachRepeat(kind="repeat", count=3, steps=[inner])
        w = easy_run(TODAY).model_copy(update={"steps": [outer], "distance_km": 4.8, "duration_min": None})
        assert plan_validation.workout_issues(w) == []


class TestPlanIssues:
    def test_complete_plan_is_valid(self):
        assert plan_validation.plan_issues(report_for(TODAY), TODAY) == []

    def test_missing_and_duplicate_days_are_reported(self):
        report = report_for(TODAY)
        plan = [*report.plan[:-1], report.plan[0]]
        issues = plan_validation.plan_issues(report.model_copy(update={"plan": plan}), TODAY)
        assert any((TODAY + timedelta(days=13)).isoformat() in i and "missing" in i for i in issues)
        assert any("more than one entry" in i for i in issues)


class TestRunSteps:
    def test_untargeted_active_running_step_is_rejected(self):
        collapsed = step(
            duration_type="time", duration_value=1260, target_type="none", target_low=None, target_high=None
        )
        w = easy_run(TODAY).model_copy(update={"steps": [collapsed], "distance_km": None, "duration_min": 21})
        assert any("need a pace, hr, hr_zone or rpe target" in i for i in plan_validation.workout_issues(w))

    def test_untargeted_active_step_is_fine_outside_running(self):
        w = easy_run(TODAY).model_copy(
            update={
                "sport": "cross",
                "type": "cross",
                "distance_km": None,
                "duration_min": None,
                "steps": [
                    step(
                        duration_type="time", duration_value=1800, target_type="none", target_low=None, target_high=None
                    )
                ],
            }
        )
        assert plan_validation.workout_issues(w) == []

    def test_repeat_marker_is_an_enum_in_the_api_schema(self):
        import pydantic
        from anthropic.lib._parse._transform import transform_schema

        defs = transform_schema(pydantic.TypeAdapter(coach_schema.CoachReportOutput).json_schema())["$defs"]
        assert defs["CoachRepeatKind"]["enum"] == ["repeat"]

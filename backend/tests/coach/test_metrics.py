"""Tests for training-load maths."""

from datetime import date, timedelta

import modules.coach.metrics as coach_metrics
from tests.coach.factories import session

TODAY = date(2026, 11, 16)
HR = coach_metrics.AthleteBasics(max_hr=190, rest_hr=50, female=False, threshold_pace_s_per_km=270)


class TestSessionLoad:
    def test_one_hour_at_threshold_hr_is_about_100(self):
        s = session(TODAY, moving_s=3600, avg_hr=50 + round(0.86 * 140))
        assert 95 <= coach_metrics.session_load(s, HR) <= 105

    def test_pace_based_when_no_heart_rate(self):
        s = session(TODAY, moving_s=3600, avg_hr=None, avg_speed=1000 / 270)
        assert coach_metrics.session_load(s, HR) == 100.0

    def test_duration_fallback_differs_for_runs_and_other_sports(self):
        basics = coach_metrics.AthleteBasics(None, None, False, None)
        run = session(TODAY, moving_s=3600, avg_hr=None)
        ride = session(TODAY, moving_s=3600, avg_hr=None, is_run=False)
        assert coach_metrics.session_load(run, basics) == 45.0
        assert coach_metrics.session_load(ride, basics) == 30.0

    def test_zero_duration_has_no_load(self):
        assert coach_metrics.session_load(session(TODAY, moving_s=0), HR) == 0.0

    def test_female_trimp_uses_its_own_weighting(self):
        s = session(TODAY, moving_s=3600, avg_hr=150)
        female = coach_metrics.AthleteBasics(190, 50, True, None)
        assert coach_metrics.session_load(s, female) != coach_metrics.session_load(s, HR)


class TestSeries:
    def test_load_series_rises_with_training_and_form_lags(self):
        sessions = [session(TODAY - timedelta(days=i)) for i in range(20)]
        for s in sessions:
            s.load = 50
        series = coach_metrics.load_series(sessions, TODAY, days=10)
        assert len(series) == 10
        assert series[-1]["date"] == TODAY
        assert series[-1]["ctl"] > series[0]["ctl"]
        assert series[-1]["atl"] > series[-1]["ctl"]

    def test_load_series_is_empty_without_sessions(self):
        assert coach_metrics.load_series([], TODAY, days=10) == []

    def test_weekly_summary_totals_runs_and_other_sport(self):
        monday = coach_metrics.week_start(TODAY)
        run = session(monday, distance_m=12000, moving_s=3600, avg_hr=150)
        ride = session(monday, is_run=False, moving_s=7200, distance_m=40000)
        old = session(monday - timedelta(weeks=30))
        weeks = coach_metrics.weekly_summary([run, ride, old], TODAY, weeks=4)
        assert len(weeks) == 4
        current = weeks[-1]
        assert current["week"] == monday
        assert (current["run_km"], current["runs"], current["long_km"], current["other_hours"]) == (12.0, 1, 12.0, 2.0)
        assert current["avg_run_hr"] == 150
        assert weeks[0]["avg_run_hr"] is None


class TestFormatting:
    def test_pace_and_duration(self):
        assert coach_metrics.fmt_pace(255) == "4:15/km"
        assert coach_metrics.fmt_pace(None) == "-"
        assert coach_metrics.pace_from_speed(4) == 250
        assert coach_metrics.pace_from_speed(None) is None
        assert coach_metrics.fmt_duration(3725) == "1:02:05"
        assert coach_metrics.fmt_duration(65) == "1:05"
        assert coach_metrics.fmt_duration(None) == "-"

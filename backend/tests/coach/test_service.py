"""Tests for coach orchestration: due detection, claiming, the update run and the dashboard."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import anthropic
import pytest

import modules.coach.crud as coach_crud
import modules.coach.engine as coach_engine
import modules.coach.schema as coach_schema
import modules.coach.service as coach_service
from tests._helpers.db import create_sqlite_session_factory
from tests.coach.factories import report_for

NOW = datetime(2026, 11, 16, 6, 30, tzinfo=UTC)  # 07:30 in Oslo
TODAY = date(2026, 11, 16)
CONFIG = coach_service.CoachConfig(api_key="test-key", model="claude-opus-5-5", effort="high", daily_hour=5)


@pytest.fixture
def db():
    factory = create_sqlite_session_factory()
    session = factory()
    yield session
    session.close()
    factory.kw["bind"].dispose()


def _activity(days_ago: int, *, created: datetime | None = None, activity_type: int = 1, **overrides):
    start = NOW - timedelta(days=days_ago, hours=1)
    values = {
        "id": 100 + days_ago,
        "start_time": start,
        "timezone": "Europe/Oslo",
        "activity_type": activity_type,
        "name": f"Run {days_ago}",
        "distance": 10000,
        "total_timer_time": 3300.0,
        "total_elapsed_time": 3400.0,
        "elevation_gain": 40,
        "average_hr": 145,
        "max_hr": 170,
        "average_speed": 1000 / 330,
        "workout_rpe": 40,
        "description": None,
        "private_notes": None,
        "created_at": created or start + timedelta(hours=2),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def peers():
    """Patch every peer module the service reads."""
    user = SimpleNamespace(name="Kari", birthdate=date(1990, 6, 1), gender="female", timezone="Europe/Oslo")
    lap = SimpleNamespace(total_distance=1000.0, total_timer_time=250.0, avg_heart_rate=170, intensity="active")
    sleep = SimpleNamespace(
        date=TODAY,
        total_sleep_seconds=27000,
        sleep_score_overall=80,
        resting_heart_rate=47,
        hrv_status=SimpleNamespace(value="BALANCED"),
        avg_stress_level=20,
        avg_skin_temp_deviation=-0.1,
    )
    with (
        patch.object(coach_service.users_integration, "get_user", return_value=user),
        patch.object(coach_service.users_integration, "timezone_or_default", side_effect=lambda tz: tz or "UTC"),
        patch.object(
            coach_service.activity_integration,
            "list_user_activities_in_timeframe_by_types",
            return_value=[_activity(d) for d in (1, 3, 5, 40)],
        ) as activities,
        patch.object(coach_service.activity_laps_integration, "list_laps_for_requester", return_value=[lap]) as laps,
        patch.object(coach_service.health_sleep_integration, "list_recent_sleep", return_value=[sleep]),
    ):
        yield SimpleNamespace(activities=activities, laps=laps)


def _enable(db, user_id: int = 1) -> None:
    coach_crud.upsert_profile(
        user_id, coach_schema.CoachProfileUpdate(enabled=True, max_hr=190, language="Norwegian"), db
    )
    db.commit()


def _claimed_at(db):
    db.expire_all()
    return db.get(coach_service.coach_crud.coach_models.CoachProfile, 1).update_claimed_at


def _engine_result(report=None) -> coach_engine.EngineResult:
    return coach_engine.EngineResult(report=report or report_for(TODAY), usage={"input_tokens": 1})


class TestRequests:
    def test_profile_save_marks_an_update_due(self, db):
        coach_service.update_profile(1, coach_schema.CoachProfileUpdate(enabled=True), NOW, db)
        assert coach_crud.get_profile(1, db).update_trigger == "settings updated"

    def test_races_and_checkins_mark_updates_due(self, db):
        _enable(db)
        stored = coach_service.replace_races(1, [coach_schema.CoachRaceWrite(name="Half", race_date=TODAY)], NOW, db)
        assert [r.name for r in stored] == ["Half"]
        assert coach_crud.get_profile(1, db).update_trigger == "races updated"
        coach_service.add_checkin(1, "  sore calf  ", NOW, db)
        assert coach_crud.list_checkins_since(1, NOW - timedelta(days=3650), db)[0].text == "sore calf"
        assert coach_crud.get_profile(1, db).update_trigger == "athlete check-in"

    def test_refresh_requires_an_enabled_coach(self, db):
        assert coach_service.request_refresh(1, NOW, db) is False
        _enable(db)
        assert coach_service.request_refresh(1, NOW, db) is True

    def test_new_activity_is_debounced(self, db):
        _enable(db)
        coach_service.note_new_activity(1, NOW, db)
        profile = coach_crud.get_profile(1, db)
        assert profile.update_trigger == "new activity"
        assert coach_service._utc(profile.update_due_at) == NOW + timedelta(seconds=120)

    def test_new_activity_ignored_without_coach(self, db):
        coach_service.note_new_activity(1, NOW, db)
        assert coach_crud.get_profile(1, db) is None


class TestRunDueUpdates:
    def test_does_nothing_without_an_api_key(self, db):
        _enable(db)
        assert coach_service.run_due_updates(coach_service.CoachConfig(None, "m", "high", 5), NOW, db) == 0

    @patch.object(coach_engine, "generate_report")
    def test_first_plan_runs_and_stores_everything(self, generate, db, peers):
        _enable(db)
        generate.return_value = _engine_result()
        assert coach_service.run_due_updates(CONFIG, NOW, db) == 1

        args, kwargs = generate.call_args
        assert "# Context pack" in args[0] and "Kari" in args[0] and "BALANCED" in args[0]
        assert kwargs["language"] == "Norwegian" and kwargs["previous_issues"] is None
        report = coach_crud.get_latest_report(1, db, ok_only=True)
        assert report.trigger == "first plan" and report.validation_issues is None
        assert len(coach_crud.list_plan(1, TODAY, TODAY + timedelta(days=20), db)) == 14
        profile = coach_crud.get_profile(1, db)
        assert profile.coach_notes == "Responds well to volume."
        assert _claimed_at(db) is None
        # laps are read per recent run, through the access-checked surface
        assert {c.args[1] for c in peers.laps.call_args_list} == {1}

        # Nothing new: the next pass does not run again.
        assert coach_service.run_due_updates(CONFIG, NOW + timedelta(minutes=2), db) == 0

    @patch.object(coach_engine, "generate_report")
    def test_invalid_plan_is_asked_again_once(self, generate, db, peers):
        _enable(db)
        bad = report_for(TODAY)
        bad = bad.model_copy(update={"plan": bad.plan[:-1]})
        generate.side_effect = [_engine_result(bad), _engine_result(bad)]
        coach_service.run_due_updates(CONFIG, NOW, db)
        assert generate.call_count == 2
        assert generate.call_args_list[1].kwargs["previous_issues"]
        report = coach_crud.get_latest_report(1, db, ok_only=True)
        assert report.validation_issues and "missing days" in report.validation_issues[0]

    @patch.object(coach_engine, "generate_report")
    def test_api_failure_is_recorded_and_released(self, generate, db, peers):
        _enable(db)
        generate.side_effect = anthropic.APIConnectionError(request=MagicMock())
        coach_service.run_due_updates(CONFIG, NOW, db)
        attempt = coach_crud.get_latest_report(1, db, ok_only=False)
        assert attempt.status == "error" and "APIConnectionError" in attempt.error
        assert _claimed_at(db) is None
        # The failed attempt counts as today's update, so it is not retried every pass.
        assert coach_service.run_due_updates(CONFIG, NOW + timedelta(minutes=2), db) == 0

    @patch.object(coach_engine, "generate_report", side_effect=ValueError("unexpected"))
    def test_unexpected_failure_is_recorded(self, _generate, db, peers):
        _enable(db)
        coach_service.run_due_updates(CONFIG, NOW, db)
        assert coach_crud.get_latest_report(1, db, ok_only=False).error.startswith("Unexpected error")

    @patch.object(coach_engine, "generate_report")
    def test_claimed_update_is_skipped(self, generate, db, peers):
        _enable(db)
        coach_crud.claim_update(1, NOW - timedelta(minutes=1), NOW - timedelta(minutes=15), db)
        db.commit()
        assert coach_service.run_due_updates(CONFIG, NOW, db) == 0
        generate.assert_not_called()

    def _with_report(self, db, created_at: datetime) -> None:
        rid = coach_crud.create_report(1, "t", "m", "c", NOW, db)
        coach_crud.finish_report(rid, db, report=report_for(TODAY).model_dump(mode="json"))
        db.query(coach_service.coach_crud.coach_models.CoachReport).filter_by(id=rid).update({"created_at": created_at})
        db.commit()

    def test_due_triggers(self, db, peers):
        _enable(db)
        profile = lambda: coach_crud.get_profile(1, db)  # noqa: E731
        # report yesterday, after the daily hour today -> daily update
        self._with_report(db, NOW - timedelta(days=1))
        assert coach_service._due_trigger(profile(), CONFIG, NOW, db) == "daily update"
        # report today, an activity created after it -> new activity (missed event)
        self._with_report(db, NOW - timedelta(hours=1))
        peers.activities.return_value = [_activity(0, created=NOW - timedelta(minutes=10))]
        assert coach_service._due_trigger(profile(), CONFIG, NOW, db) == "new activity"
        # nothing new -> not due
        peers.activities.return_value = []
        assert coach_service._due_trigger(profile(), CONFIG, NOW, db) is None
        # before the daily hour nothing happens either
        early = coach_service.CoachConfig("k", "m", "high", daily_hour=9)
        self._with_report(db, NOW - timedelta(days=1))
        assert coach_service._due_trigger(profile(), early, NOW, db) is None
        # an explicit request always wins
        coach_crud.mark_update_due(1, NOW, "manual refresh", db)
        assert coach_service._due_trigger(profile(), early, NOW, db) == "manual refresh"

    def test_run_update_for_a_disabled_profile_only_releases(self, db, peers):
        coach_crud.upsert_profile(1, coach_schema.CoachProfileUpdate(enabled=False), db)
        db.commit()
        assert coach_service.run_update(1, "t", NOW, CONFIG, db) is None


class TestDashboard:
    def test_without_profile_is_empty(self, db):
        dash = coach_service.get_dashboard(1, CONFIG, NOW, db)
        assert dash.profile is None and dash.days == [] and dash.configured is True

    @patch.object(coach_engine, "generate_report")
    def test_with_plan_shows_two_weeks_and_charts(self, generate, db, peers):
        _enable(db)
        generate.return_value = _engine_result()
        coach_service.run_due_updates(CONFIG, NOW, db)
        dash = coach_service.get_dashboard(1, CONFIG, NOW, db)
        assert len(dash.days) == 14 and dash.days[0].date == TODAY  # TODAY is a Monday
        assert dash.days[0].workout.type == "easy" and dash.days[0].status == "pending"
        assert dash.days[2].status == "rest"
        assert dash.report.report.headline == "Steady week"
        assert dash.load and dash.load[-1].date == TODAY
        assert len(dash.weeks) == 17 and dash.weeks[-1].planned_km
        assert coach_service.get_latest_context(1, db).startswith("# Context pack")


def test_load_config_reads_the_secret(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    config = coach_service.load_config()
    assert config.api_key == "sk-test" and config.model

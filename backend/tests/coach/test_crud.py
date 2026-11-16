"""Tests for coach persistence, against an in-memory database."""

from datetime import UTC, date, datetime, timedelta

import pytest

import modules.coach.crud as coach_crud
import modules.coach.schema as coach_schema
from tests._helpers.db import create_sqlite_session_factory
from tests.coach.factories import easy_run, report_for

NOW = datetime(2026, 11, 16, 6, 0, tzinfo=UTC)


@pytest.fixture
def db():
    factory = create_sqlite_session_factory()
    session = factory()
    yield session
    session.close()
    factory.kw["bind"].dispose()


def _enable(db, user_id: int = 1) -> coach_schema.CoachProfileRead:
    profile = coach_crud.upsert_profile(user_id, coach_schema.CoachProfileUpdate(enabled=True, max_hr=190), db)
    db.commit()
    return profile


class TestProfile:
    def test_upsert_creates_then_updates(self, db):
        assert coach_crud.get_profile(1, db) is None
        _enable(db)
        updated = coach_crud.upsert_profile(1, coach_schema.CoachProfileUpdate(enabled=False, max_hr=185), db)
        assert (updated.enabled, updated.max_hr) == (False, 185)
        assert updated.available_days == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    def test_notes_are_replaced(self, db):
        _enable(db)
        coach_crud.set_coach_notes(1, "likes hills", db)
        assert coach_crud.get_profile(1, db).coach_notes == "likes hills"

    def test_mark_due_only_for_enabled_profiles(self, db):
        assert coach_crud.mark_update_due(1, NOW, "x", db) is False
        _enable(db)
        assert coach_crud.mark_update_due(1, NOW, "new activity", db) is True
        assert coach_crud.get_profile(1, db).update_trigger == "new activity"

    def test_list_enabled_profiles_pages_by_user_id(self, db):
        for uid in (1, 2, 3):
            _enable(db, uid)
        coach_crud.upsert_profile(2, coach_schema.CoachProfileUpdate(enabled=False), db)
        assert [p.user_id for p in coach_crud.list_enabled_profiles(0, 10, db)] == [1, 3]
        assert [p.user_id for p in coach_crud.list_enabled_profiles(1, 10, db)] == [3]


class TestClaim:
    def test_only_one_claim_wins_until_released(self, db):
        _enable(db)
        stale = NOW - timedelta(minutes=15)
        assert coach_crud.claim_update(1, NOW, stale, db) is True
        assert coach_crud.claim_update(1, NOW + timedelta(seconds=5), stale, db) is False
        coach_crud.release_update(1, NOW, db)
        assert coach_crud.claim_update(1, NOW + timedelta(seconds=10), stale, db) is True

    def test_abandoned_claim_can_be_taken_over(self, db):
        _enable(db)
        coach_crud.claim_update(1, NOW - timedelta(hours=1), NOW - timedelta(hours=2), db)
        assert coach_crud.claim_update(1, NOW, NOW - timedelta(minutes=15), db) is True

    def test_release_keeps_a_due_mark_set_after_the_claim(self, db):
        _enable(db)
        coach_crud.mark_update_due(1, NOW, "first", db)
        coach_crud.claim_update(1, NOW, NOW - timedelta(minutes=15), db)
        coach_crud.mark_update_due(1, NOW + timedelta(minutes=2), "new activity", db)
        coach_crud.release_update(1, NOW, db)
        assert coach_crud.get_profile(1, db).update_trigger == "new activity"

    def test_release_clears_the_handled_due_mark(self, db):
        _enable(db)
        coach_crud.mark_update_due(1, NOW, "first", db)
        coach_crud.release_update(1, NOW, db)
        profile = coach_crud.get_profile(1, db)
        assert (profile.update_due_at, profile.update_trigger) == (None, None)


class TestRacesCheckinsReportsPlan:
    def test_races_are_replaced_and_sorted(self, db):
        races = [
            coach_schema.CoachRaceWrite(name="Late", race_date=date(2027, 9, 1)),
            coach_schema.CoachRaceWrite(name="Early", race_date=date(2027, 3, 1), priority="B"),
        ]
        assert [r.name for r in coach_crud.replace_races(1, races, db)] == ["Early", "Late"]
        assert coach_crud.replace_races(1, [], db) == []

    def test_checkins_since(self, db):
        coach_crud.create_checkin(1, "sore calf", db)
        assert [c.text for c in coach_crud.list_checkins_since(1, NOW - timedelta(days=3650), db)] == ["sore calf"]

    def test_report_lifecycle(self, db):
        assert coach_crud.get_latest_report(1, db, ok_only=False) is None
        first = coach_crud.create_report(1, "daily update", "model-x", "# pack", NOW, db)
        coach_crud.finish_report(first, db, error="boom")
        second = coach_crud.create_report(1, "manual refresh", "model-x", "# pack 2", NOW, db)
        coach_crud.finish_report(second, db, report=report_for(date(2026, 11, 16)).model_dump(mode="json"), usage={})
        latest_ok = coach_crud.get_latest_report(1, db, ok_only=True)
        assert latest_ok.id == second and latest_ok.report.headline == "Steady week"
        assert coach_crud.get_latest_report(1, db, ok_only=False).id == second
        assert coach_crud.get_latest_context(1, db) == "# pack 2"

    def test_future_plan_is_replaced_and_past_days_kept(self, db):
        rid = coach_crud.create_report(1, "t", "m", "c", NOW, db)
        today = date(2026, 11, 16)
        coach_crud.replace_future_plan(
            1, today - timedelta(days=2), [easy_run(today - timedelta(days=2)), easy_run(today)], rid, db
        )
        coach_crud.replace_future_plan(1, today, [easy_run(today, km=6), easy_run(today + timedelta(days=1))], rid, db)
        plan = coach_crud.list_plan(1, today - timedelta(days=7), today + timedelta(days=7), db)
        assert sorted(plan) == [today - timedelta(days=2), today, today + timedelta(days=1)]
        assert plan[today].distance_km == 6

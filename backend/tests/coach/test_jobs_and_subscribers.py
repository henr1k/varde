"""Tests for the coach's subscriber, scheduled job and engine call."""

from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from jasil.events import Event, new_event

import modules.activities.activity.events as activity_events
import modules.coach.engine as coach_engine
import modules.coach.scheduled_jobs as coach_scheduled_jobs
import modules.coach.subscriber_registry as coach_subscriber_registry
import modules.coach.subscribers as coach_subscribers
from tests.coach.factories import report_for

ANTHROPIC = coach_engine.LlmSettings(coach_engine.coach_constants.LlmProvider.ANTHROPIC, "claude-opus-5-5", "k")


def _created_event(user_id: int = 3) -> Event:
    return new_event(
        activity_events.ACTIVITY_CREATED,
        {"activity_id": 11, "user_id": user_id, "duplicate_start_time": False},
        source="test",
    )


class TestSubscriber:
    @patch("modules.coach.subscribers.core_database.SessionLocal")
    @patch("modules.coach.subscribers.coach_service.note_new_activity")
    def test_marks_the_owner_due(self, note, session_local):
        coach_subscribers.note_activity_for_event(_created_event(3))
        assert note.call_args.args[0] == 3

    def test_registration(self):
        events = MagicMock()
        coach_subscriber_registry.register_bus_subscribers(events)
        assert events.subscribe.call_args.args[0] == activity_events.ACTIVITY_CREATED
        registry = MagicMock()
        coach_subscriber_registry.register_durable_handlers(registry)
        assert registry.register.call_args.args[1] == coach_subscribers.COACH_ACTIVITY_SUBSCRIBER_ID


class TestScheduledJob:
    def test_is_scheduled(self):
        (job,) = coach_scheduled_jobs.recurring_jobs()
        assert job.func is coach_scheduled_jobs.run_due_coach_updates

    @pytest.mark.parametrize("acquired", [True, False])
    @patch("modules.coach.scheduled_jobs.core_database.SessionLocal")
    @patch("modules.coach.scheduled_jobs.coach_service.run_due_updates", return_value=1)
    def test_runs_only_while_holding_the_lock(self, run_due, _session, monkeypatch, acquired):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

        @contextmanager
        def try_acquire(_name):
            yield acquired

        platform = SimpleNamespace(lock=SimpleNamespace(try_acquire=try_acquire))
        with patch("modules.coach.scheduled_jobs.platform_runtime.get_active_platform", return_value=platform):
            coach_scheduled_jobs.run_due_coach_updates()
        assert run_due.called is acquired

    @patch("modules.coach.scheduled_jobs.core_scheduler.run_once")
    def test_schedule_now(self, run_once):
        coach_scheduled_jobs.schedule_due_updates_now()
        assert run_once.call_args.args[0] is coach_scheduled_jobs.run_due_coach_updates


class TestEngine:
    def _client_returning(self, message):
        stream = MagicMock()
        stream.__enter__.return_value.get_final_message.return_value = message
        stream.__enter__.return_value.request_id = "req_1"
        client = MagicMock()
        client.beta.messages.stream.return_value = stream
        return client

    def _message(self, **overrides):
        values = {
            "stop_reason": "end_turn",
            "stop_details": None,
            "parsed_output": report_for(date(2026, 11, 16)),
            "model": "claude-opus-5-5",
            "usage": SimpleNamespace(input_tokens=10, output_tokens=20, cache_read_input_tokens=0),
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_returns_parsed_report_and_sends_the_right_request(self):
        client = self._client_returning(self._message())
        with patch("modules.coach.engine.anthropic.Anthropic", return_value=client):
            result = coach_engine.generate_report(
                "# pack",
                date(2026, 11, 16),
                ANTHROPIC,
                language="English",
                previous_issues=["2026-11-17: missing steps"],
            )
        assert result.report.headline == "Steady week" and result.usage["request_id"] == "req_1"
        kwargs = client.beta.messages.stream.call_args.kwargs
        assert kwargs["output_format"] is coach_engine.coach_schema.CoachReportOutput
        assert kwargs["fallbacks"] == "default" and kwargs["thinking"] == {"type": "adaptive"}
        prompt = kwargs["messages"][0]["content"]
        assert "2026-11-16 through 2026-11-29" in prompt and "missing steps" in prompt

    @pytest.mark.parametrize(
        ("overrides", "message"),
        [
            ({"stop_reason": "refusal", "stop_details": SimpleNamespace(category="bio")}, "declined"),
            ({"stop_reason": "max_tokens"}, "output limit"),
            ({"parsed_output": None}, "no structured report"),
        ],
    )
    def test_unusable_responses_raise(self, overrides, message):
        client = self._client_returning(self._message(**overrides))
        with (
            patch("modules.coach.engine.anthropic.Anthropic", return_value=client),
            pytest.raises(coach_engine.CoachEngineError, match=message),
        ):
            coach_engine.generate_report("# pack", date(2026, 11, 16), ANTHROPIC, language="English")


class TestPeerSurfaces:
    @patch("modules.activities.activity_laps.service.list_activity_laps")
    def test_laps_for_requester_uses_the_access_checked_listing(self, list_laps):
        import modules.activities.activity_laps.integration_service as laps_integration

        list_laps.return_value = SimpleNamespace(items=["lap"])
        assert laps_integration.list_laps_for_requester(5, 7, MagicMock()) == ["lap"]
        assert list_laps.call_args.args[:2] == (5, 7)

    @patch("modules.health.health_sleep.crud.get_health_sleep_by_user_id", return_value=["night"])
    def test_recent_sleep(self, get_sleep):
        import modules.health.health_sleep.integration_service as sleep_integration

        assert sleep_integration.list_recent_sleep(7, 14, MagicMock()) == ["night"]
        assert get_sleep.call_args.kwargs == {"page_number": 1, "num_records": 14}

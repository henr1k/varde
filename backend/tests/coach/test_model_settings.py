"""Tests for per-user model settings: provider choice, own API keys, and provider portability."""

import json
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import anthropic
import openai
import pytest

import core.exceptions as core_exceptions
import modules.coach.constants as coach_constants
import modules.coach.crud as coach_crud
import modules.coach.engine as coach_engine
import modules.coach.schema as coach_schema
import modules.coach.service as coach_service
from tests._helpers.db import create_sqlite_session_factory
from tests.coach.factories import report_for

NOW = datetime(2026, 11, 16, 6, 30, tzinfo=UTC)
SERVER = coach_service.CoachConfig(api_key="server-key", model="claude-opus-5-5", effort="high", daily_hour=5)
NO_SERVER_KEY = coach_service.CoachConfig(api_key=None, model="claude-opus-5-5", effort="high", daily_hour=5)
OPENAI = coach_constants.LlmProvider.OPENAI_COMPATIBLE


@pytest.fixture
def db():
    factory = create_sqlite_session_factory()
    session = factory()
    yield session
    session.close()
    factory.kw["bind"].dispose()


def _save(db, **fields) -> coach_schema.CoachProfileRead:
    coach_crud.upsert_profile(1, coach_schema.CoachProfileUpdate(enabled=True, **fields), db)
    db.commit()
    return coach_crud.get_profile(1, db)


class TestResolveModel:
    def test_server_key_and_default_model(self, db):
        settings, status = coach_service.resolve_model(_save(db), SERVER, db)
        assert (settings.api_key, settings.model, settings.effort) == ("server-key", "claude-opus-5-5", "high")
        assert (status.usable, status.key_source) == (True, "server")

    def test_own_key_and_model_win(self, db):
        _save(db, llm_model="claude-sonnet-5-5", llm_effort="medium")
        coach_service.save_api_key(1, "  sk-ant-own-1234  ", db)
        settings, status = coach_service.resolve_model(coach_crud.get_profile(1, db), SERVER, db)
        assert (settings.api_key, settings.model, settings.effort) == ("sk-ant-own-1234", "claude-sonnet-5-5", "medium")
        assert status.key_source == "own"

    def test_no_key_anywhere_is_not_usable(self, db):
        settings, status = coach_service.resolve_model(_save(db), NO_SERVER_KEY, db)
        assert settings is None and not status.usable and "API key" in status.detail

    def test_openai_compatible_never_uses_the_server_key(self, db):
        with patch.object(coach_service.core_network, "url_rejection_reason", return_value=None):
            coach_service.update_profile(
                1,
                coach_schema.CoachProfileUpdate(
                    enabled=True, llm_provider=OPENAI, llm_model="llama3.1", llm_base_url="http://ollama:11434/v1"
                ),
                NOW,
                db,
            )
        settings, status = coach_service.resolve_model(coach_crud.get_profile(1, db), SERVER, db)
        assert settings.provider == OPENAI and settings.api_key is None and settings.base_url.endswith("/v1")
        assert status.key_source == "none" and status.detail == "openai_compatible/llama3.1"

    def test_openai_compatible_without_url_is_not_usable(self, db):
        profile = _save(db).model_copy(update={"llm_provider": OPENAI})
        settings, status = coach_service.resolve_model(profile, SERVER, db)
        assert settings is None and "server URL" in status.detail


class TestProfileValidation:
    def test_openai_compatible_needs_url_and_model(self, db):
        with pytest.raises(core_exceptions.InvalidInputError):
            coach_service.update_profile(
                1, coach_schema.CoachProfileUpdate(enabled=True, llm_provider=OPENAI, llm_model="gpt-x"), NOW, db
            )

    def test_internal_url_is_rejected_unless_allow_listed(self, db):
        data = coach_schema.CoachProfileUpdate(
            enabled=True, llm_provider=OPENAI, llm_model="m", llm_base_url="http://127.0.0.1:11434/v1"
        )
        with pytest.raises(core_exceptions.InvalidInputError, match="cannot be used"):
            coach_service.update_profile(1, data, NOW, db)


class TestApiKey:
    def test_key_is_encrypted_at_rest_and_only_a_hint_is_returned(self, db):
        profile = coach_service.save_api_key(1, "sk-ant-secret-9876", db)
        assert profile.llm_api_key_hint == "9876" and profile.enabled is False
        stored = coach_crud.get_encrypted_api_key(1, db)
        assert stored and "sk-ant-secret" not in stored
        assert "llm_api_key" not in coach_schema.CoachProfileRead.model_fields

    def test_delete_removes_the_key(self, db):
        coach_service.save_api_key(1, "sk-ant-secret-9876", db)
        coach_service.delete_api_key(1, db)
        assert coach_crud.get_encrypted_api_key(1, db) is None
        assert coach_crud.get_profile(1, db).llm_api_key_hint is None

    def test_delete_without_profile_is_a_no_op(self, db):
        coach_service.delete_api_key(1, db)
        assert coach_crud.get_profile(1, db) is None


class TestConnectionCheck:
    def test_without_profile(self, db):
        assert coach_service.check_model_connection(1, SERVER, db).ok is False

    def test_unusable_settings_explain_why(self, db):
        _save(db)
        result = coach_service.check_model_connection(1, NO_SERVER_KEY, db)
        assert result.ok is False and "API key" in result.detail

    @patch.object(coach_engine, "check_connection", return_value="Connected")
    def test_success(self, check, db):
        _save(db)
        assert coach_service.check_model_connection(1, SERVER, db).ok is True
        assert check.call_args.args[0].api_key == "server-key"

    def test_rejected_key_is_reported_without_details(self, db):
        _save(db)
        error = anthropic.AuthenticationError("bad key sk-ant-xyz", response=MagicMock(status_code=401), body=None)
        with patch.object(coach_engine, "check_connection", side_effect=error):
            result = coach_service.check_model_connection(1, SERVER, db)
        assert (
            result.ok is False
            and result.detail == "The provider rejected the API key."
            and "sk-ant" not in result.detail
        )


class TestUpdatesUseEachUsersModel:
    @patch.object(coach_engine, "generate_report")
    def test_own_key_works_without_a_server_key(self, generate, db):
        _save(db, llm_model="claude-sonnet-5-5")
        coach_service.save_api_key(1, "sk-ant-own-1234", db)
        generate.return_value = coach_engine.EngineResult(report_for(date(2026, 11, 16)), {})
        with patch.object(coach_service, "_read_athlete") as read:
            read.return_value = SimpleNamespace(inputs=MagicMock(), today=date(2026, 11, 16), language="English")
            with patch.object(coach_service.coach_context, "build", return_value="# pack"):
                assert coach_service.run_due_updates(NO_SERVER_KEY, NOW, db) == 1
        assert generate.call_args.args[2].api_key == "sk-ant-own-1234"
        assert coach_crud.get_latest_report(1, db, ok_only=True).model == "anthropic/claude-sonnet-5-5"

    def test_users_without_a_usable_model_are_skipped(self, db):
        _save(db)
        assert coach_service.run_due_updates(NO_SERVER_KEY, NOW, db) == 0
        assert coach_crud.get_latest_report(1, db, ok_only=False) is None

    def test_dashboard_reports_the_model_status(self, db):
        _save(db)
        athlete = SimpleNamespace(inputs=SimpleNamespace(sessions=[], checkins=[]), today=date(2026, 11, 16))
        with patch.object(coach_service, "_read_athlete", return_value=athlete):
            without = coach_service.get_dashboard(1, NO_SERVER_KEY, NOW, db)
            with_server = coach_service.get_dashboard(1, SERVER, NOW, db)
        assert without.configured is False and without.model_status.key_source == "none"
        assert with_server.configured is True and with_server.model_status.detail == "anthropic/claude-opus-5-5"


class TestOpenAICompatibleEngine:
    SETTINGS = coach_engine.LlmSettings(OPENAI, "gpt-test", "sk-o", "https://example.test/v1")

    def _completion(self, content: str, finish: str = "stop"):
        message = SimpleNamespace(content=content, refusal=None)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason=finish)],
            model="gpt-test",
            id="chatcmpl-1",
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20),
        )

    def _client(self, *results):
        client = MagicMock()
        client.chat.completions.create.side_effect = list(results)
        return client

    def test_valid_json_is_parsed_and_the_schema_is_requested(self):
        body = report_for(date(2026, 11, 16)).model_dump_json()
        client = self._client(self._completion(f"```json\n{body}\n```"))
        with patch.object(coach_engine.openai, "OpenAI", return_value=client) as ctor:
            result = coach_engine.generate_report("# pack", date(2026, 11, 16), self.SETTINGS, language="English")
        assert result.report.headline == "Steady week" and result.usage["provider"] == "openai_compatible"
        assert ctor.call_args.kwargs["base_url"] == "https://example.test/v1"
        kwargs = client.chat.completions.create.call_args.kwargs
        assert kwargs["response_format"]["type"] == "json_schema"
        assert "JSON Schema" in kwargs["messages"][0]["content"]

    def test_falls_back_to_json_mode_when_schema_output_is_unsupported(self):
        body = report_for(date(2026, 11, 16)).model_dump_json()
        unsupported = openai.BadRequestError("no json_schema", response=MagicMock(status_code=400), body=None)
        client = self._client(unsupported, self._completion(body))
        with patch.object(coach_engine.openai, "OpenAI", return_value=client):
            coach_engine.generate_report("# pack", date(2026, 11, 16), self.SETTINGS, language="English")
        assert client.chat.completions.create.call_args.kwargs["response_format"] == {"type": "json_object"}

    @pytest.mark.parametrize(
        ("content", "finish", "match"),
        [
            (json.dumps({"headline": "only this"}), "stop", "did not match"),
            ("{}", "length", "output limit"),
        ],
    )
    def test_unusable_replies_raise(self, content, finish, match):
        client = self._client(self._completion(content, finish))
        with (
            patch.object(coach_engine.openai, "OpenAI", return_value=client),
            pytest.raises(coach_engine.CoachEngineError, match=match),
        ):
            coach_engine.generate_report("# pack", date(2026, 11, 16), self.SETTINGS, language="English")

    def test_local_server_gets_a_placeholder_key(self):
        with patch.object(coach_engine.openai, "OpenAI") as ctor:
            coach_engine._openai_client(coach_engine.LlmSettings(OPENAI, "m", None, "http://ollama/v1"))
        assert ctor.call_args.kwargs["api_key"] == "not-needed"


class TestCheckConnection:
    def test_anthropic_retrieves_the_model(self):
        client = MagicMock()
        client.models.retrieve.return_value = SimpleNamespace(display_name="Claude Opus 5.5")
        settings = coach_engine.LlmSettings(coach_constants.LlmProvider.ANTHROPIC, "claude-opus-5-5", "k")
        with patch.object(coach_engine.anthropic, "Anthropic", return_value=client):
            assert "Claude Opus 5.5" in coach_engine.check_connection(settings)

    def test_openai_compatible_checks_the_model_list(self):
        client = MagicMock()
        client.with_options.return_value.models.list.return_value = [SimpleNamespace(id="other")]
        settings = coach_engine.LlmSettings(OPENAI, "gpt-test", "k", "https://example.test/v1")
        with (
            patch.object(coach_engine.openai, "OpenAI", return_value=client),
            pytest.raises(coach_engine.CoachEngineError, match="does not offer"),
        ):
            coach_engine.check_connection(settings)
        client.with_options.return_value.models.list.return_value = [SimpleNamespace(id="gpt-test")]
        with patch.object(coach_engine.openai, "OpenAI", return_value=client):
            assert "available" in coach_engine.check_connection(settings)

    def test_fallbacks_only_for_models_that_support_them(self):
        stream = MagicMock()
        stream.__enter__.return_value.get_final_message.return_value = SimpleNamespace(
            stop_reason="end_turn",
            stop_details=None,
            parsed_output=report_for(date(2026, 11, 16)),
            model="claude-haiku-5-5",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1, cache_read_input_tokens=0),
        )
        client = MagicMock()
        client.beta.messages.stream.return_value = stream
        haiku = coach_engine.LlmSettings(coach_constants.LlmProvider.ANTHROPIC, "claude-haiku-5-5", "k")
        with patch.object(coach_engine.anthropic, "Anthropic", return_value=client):
            coach_engine.generate_report("# pack", date(2026, 11, 16), haiku, language="English")
        assert "fallbacks" not in client.beta.messages.stream.call_args.kwargs

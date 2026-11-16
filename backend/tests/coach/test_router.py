"""Tests for the coach API routes."""

from datetime import date
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import modules.coach.schema as coach_schema


def _client(mock_db) -> TestClient:
    import core.database as core_db
    import core.exceptions as core_exceptions
    import modules.auth.dependencies as auth_deps
    import modules.coach.router as router

    app = FastAPI()
    app.include_router(router.router, prefix="/coach")
    core_exceptions.register_exception_handlers(app)
    app.dependency_overrides[auth_deps.check_scopes] = lambda: None
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = lambda: 7
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return TestClient(app)


def _empty_dashboard() -> coach_schema.CoachDashboard:
    return coach_schema.CoachDashboard(
        configured=False,
        profile=None,
        races=[],
        report=None,
        latest_attempt=None,
        days=[],
        load=[],
        weeks=[],
        checkins=[],
    )


@patch("modules.coach.service.get_dashboard")
def test_dashboard(get_dashboard, mock_db):
    get_dashboard.return_value = _empty_dashboard()
    response = _client(mock_db).get("/coach")
    assert response.status_code == 200 and response.json()["configured"] is False
    assert get_dashboard.call_args.args[0] == 7


@patch("modules.coach.service.update_profile")
def test_update_profile_validates_input(update_profile, mock_db):
    update_profile.return_value = coach_schema.CoachProfileRead(user_id=7, enabled=True)
    client = _client(mock_db)
    assert client.put("/coach/profile", json={"enabled": True, "max_hr": 500}).status_code == 422
    assert client.put("/coach/profile", json={"enabled": True, "long_run_day": "Sun"}).status_code == 200


@patch("modules.coach.service.replace_races")
def test_replace_races(replace_races, mock_db):
    replace_races.return_value = [coach_schema.CoachRaceRead(id=1, name="Half", race_date=date(2027, 4, 1))]
    response = _client(mock_db).put("/coach/races", json=[{"name": "Half", "race_date": "2027-04-01"}])
    assert response.status_code == 200 and response.json()[0]["priority"] == "A"


@patch("modules.coach.service.add_checkin")
def test_checkin(add_checkin, mock_db):
    add_checkin.return_value = coach_schema.CoachCheckinRead(id=1, text="tired", created_at="2026-11-16T06:00:00Z")
    client = _client(mock_db)
    assert client.post("/coach/checkins", json={"text": ""}).status_code == 422
    assert client.post("/coach/checkins", json={"text": "tired"}).status_code == 201


@patch("modules.coach.service.request_refresh")
def test_refresh(request_refresh, mock_db):
    client = _client(mock_db)
    request_refresh.return_value = True
    assert client.post("/coach/refresh").status_code == 202
    request_refresh.return_value = False
    assert client.post("/coach/refresh").status_code == 409


@patch("modules.coach.service.get_latest_context")
def test_context(get_latest_context, mock_db):
    client = _client(mock_db)
    get_latest_context.return_value = None
    assert client.get("/coach/context").status_code == 404
    get_latest_context.return_value = "# Context pack"
    response = client.get("/coach/context")
    assert response.status_code == 200 and response.text == "# Context pack"


@patch("modules.coach.service.save_api_key")
def test_save_api_key_validates_and_hides_the_key(save_api_key, mock_db):
    save_api_key.return_value = coach_schema.CoachProfileRead(user_id=7, enabled=True, llm_api_key_hint="1234")
    client = _client(mock_db)
    assert client.put("/coach/api-key", json={"api_key": "short"}).status_code == 422
    response = client.put("/coach/api-key", json={"api_key": "sk-ant-abcdef-1234"})
    assert response.status_code == 200 and "sk-ant" not in response.text
    assert response.json()["llm_api_key_hint"] == "1234"


@patch("modules.coach.service.delete_api_key")
def test_delete_api_key(delete_api_key, mock_db):
    assert _client(mock_db).delete("/coach/api-key").status_code == 204
    assert delete_api_key.call_args.args[0] == 7


@patch("modules.coach.service.check_model_connection")
def test_check_model(check, mock_db):
    check.return_value = coach_schema.CoachConnectionTest(ok=True, detail="Connected")
    response = _client(mock_db).post("/coach/model/test")
    assert response.status_code == 200 and response.json()["ok"] is True

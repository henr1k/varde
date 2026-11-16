"""API routes for the AI coach. Every route acts on the authenticated user's own coach."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Security, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.coach.schema as coach_schema
import modules.coach.service as coach_service

router = APIRouter()

ReadScope = Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["coach:read"])]
WriteScope = Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["coach:write"])]
TokenUser = Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)]
Db = Annotated[Session, Depends(core_database.get_db)]


@router.get("", response_model=coach_schema.CoachDashboard)
def read_dashboard(_check_scopes: ReadScope, token_user_id: TokenUser, db: Db) -> coach_schema.CoachDashboard:
    """Return today's guidance, the two-week plan with what was done, charts data and settings."""
    return coach_service.get_dashboard(token_user_id, coach_service.load_config(), datetime.now(UTC), db)


@router.put("/profile", response_model=coach_schema.CoachProfileRead)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def update_profile(
    request: Request, data: coach_schema.CoachProfileUpdate, _check_scopes: WriteScope, token_user_id: TokenUser, db: Db
) -> coach_schema.CoachProfileRead:
    """Save coach settings; a new plan follows shortly."""
    return coach_service.update_profile(token_user_id, data, datetime.now(UTC), db)


@router.put("/races", response_model=list[coach_schema.CoachRaceRead])
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def replace_races(
    request: Request,
    races: list[coach_schema.CoachRaceWrite],
    _check_scopes: WriteScope,
    token_user_id: TokenUser,
    db: Db,
) -> list[coach_schema.CoachRaceRead]:
    """Replace the race calendar; a new plan follows shortly."""
    return coach_service.replace_races(token_user_id, races, datetime.now(UTC), db)


@router.post("/checkins", response_model=coach_schema.CoachCheckinRead, status_code=status.HTTP_201_CREATED)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def create_checkin(
    request: Request, data: coach_schema.CoachCheckinCreate, _check_scopes: WriteScope, token_user_id: TokenUser, db: Db
) -> coach_schema.CoachCheckinRead:
    """Send the coach a note; the plan is reworked shortly."""
    return coach_service.add_checkin(token_user_id, data.text, datetime.now(UTC), db)


@router.post("/refresh", response_model=coach_schema.CoachRefreshAccepted, status_code=status.HTTP_202_ACCEPTED)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def request_refresh(
    request: Request, _check_scopes: WriteScope, token_user_id: TokenUser, db: Db
) -> coach_schema.CoachRefreshAccepted:
    """Ask for a new update now; it runs on the next scheduler pass."""
    if not coach_service.request_refresh(token_user_id, datetime.now(UTC), db):
        raise core_exceptions.ConflictError("Enable the coach in its settings first")
    return coach_schema.CoachRefreshAccepted(detail="Coach update requested")


@router.get("/context", response_class=PlainTextResponse)
def read_context(_check_scopes: ReadScope, token_user_id: TokenUser, db: Db) -> str:
    """Return exactly what the coach saw on its latest update."""
    context = coach_service.get_latest_context(token_user_id, db)
    if context is None:
        raise core_exceptions.NotFoundError("The coach has not run yet")
    return context


@router.put("/api-key", response_model=coach_schema.CoachProfileRead)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def save_api_key(
    request: Request, data: coach_schema.CoachApiKeyUpdate, _check_scopes: WriteScope, token_user_id: TokenUser, db: Db
) -> coach_schema.CoachProfileRead:
    """Save your own API key for your model provider. It is stored encrypted and never returned."""
    return coach_service.save_api_key(token_user_id, data.api_key, db)


@router.delete("/api-key", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_api_key(request: Request, _check_scopes: WriteScope, token_user_id: TokenUser, db: Db) -> None:
    """Remove your own API key (the server key, if any, is used again)."""
    coach_service.delete_api_key(token_user_id, db)


@router.post("/model/test", response_model=coach_schema.CoachConnectionTest)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def check_model(
    request: Request, _check_scopes: WriteScope, token_user_id: TokenUser, db: Db
) -> coach_schema.CoachConnectionTest:
    """Check your model settings against the provider without generating a plan."""
    return coach_service.check_model_connection(token_user_id, coach_service.load_config(), db)

"""Application logic for the coach.

Updates are never run inside a request or an event subscriber. Requests and subscribers only mark
a user's update as due; the scheduled pass (``run_due_updates``) claims each due user with one
conditional ``UPDATE`` and runs the update. Reading data, calling Claude and storing the result
are separate transactions, so no database connection is held while the model works.
"""

import statistics
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

import core.config as core_config
import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.network as core_network
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity_laps.integration_service as activity_laps_integration
import modules.coach.constants as coach_constants
import modules.coach.context_builder as coach_context
import modules.coach.crud as coach_crud
import modules.coach.engine as coach_engine
import modules.coach.metrics as coach_metrics
import modules.coach.plan_validation as coach_validation
import modules.coach.schema as coach_schema
import modules.health.health_sleep.integration_service as health_sleep_integration
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)

_RUN_TYPE_IDS = frozenset(activity_constants.ACTIVITY_TYPES_BY_SPORT["run"])


@dataclass(frozen=True)
class CoachConfig:
    """Server-wide coach defaults, read from configuration at the entry point.

    Attributes:
        api_key: The server's Anthropic key. Users without their own key share it; when it is
            unset, every user must bring their own key.
        model: Default Anthropic model.
        effort: Default reasoning effort.
        daily_hour: Local hour after which the daily update runs.
    """

    api_key: str | None
    model: str
    effort: str
    daily_hour: int


# --------------------------------------------------------------------------- model resolution
def resolve_model(
    profile: coach_schema.CoachProfileRead, config: CoachConfig, db: Session
) -> tuple[coach_engine.LlmSettings | None, coach_schema.CoachModelStatus]:
    """Decide which model, provider and key this user's updates use.

    The user's own key always wins. Without one, Anthropic falls back to the server key;
    an OpenAI-compatible server needs no key only when it is a local one that ignores it.

    Args:
        profile: The user's coach profile.
        config: Server defaults.
        db: Database session.

    Returns:
        The settings to call with (``None`` when the coach cannot run) and a status for the UI.
    """
    provider = profile.llm_provider or coach_constants.LlmProvider.ANTHROPIC
    own_key = core_cryptography.decrypt_token_fernet(coach_crud.get_encrypted_api_key(profile.user_id, db))

    if provider == coach_constants.LlmProvider.ANTHROPIC:
        model = profile.llm_model or config.model
        key, source = (own_key, "own") if own_key else (config.api_key, "server" if config.api_key else "none")
        if not key:
            return None, coach_schema.CoachModelStatus(
                usable=False,
                provider=provider,
                model=model,
                key_source="none",
                detail="Add your Anthropic API key in coach settings.",
            )
        settings = coach_engine.LlmSettings(provider, model, key, None, profile.llm_effort or config.effort)
        return settings, coach_schema.CoachModelStatus(
            usable=True, provider=provider, model=model, key_source=source, detail=settings.label
        )

    if not profile.llm_base_url or not profile.llm_model:
        return None, coach_schema.CoachModelStatus(
            usable=False,
            provider=provider,
            model=profile.llm_model,
            key_source="own" if own_key else "none",
            detail="Set the server URL and model for your OpenAI-compatible provider.",
        )
    settings = coach_engine.LlmSettings(provider, profile.llm_model, own_key, profile.llm_base_url)
    return settings, coach_schema.CoachModelStatus(
        usable=True,
        provider=provider,
        model=profile.llm_model,
        key_source="own" if own_key else "none",
        detail=settings.label,
    )


def _check_base_url(url: str) -> None:
    """Reject URLs Endurain must not dial (internal hosts unless the admin allow-listed them)."""
    reason = core_network.url_rejection_reason(url, purpose="coach_llm")
    if reason:
        raise core_exceptions.InvalidInputError(f"The model server URL cannot be used: {reason}")


@dataclass(frozen=True)
class _AthleteData:
    """Everything read for one athlete, before any model call."""

    inputs: coach_context.ContextInputs
    today: date
    language: str


# --------------------------------------------------------------------------- reading
def _utc(value: datetime) -> datetime:
    """Return ``value`` as an aware UTC instant (stores without a zone return naive UTC)."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _enum_text(value: object) -> str | None:
    """Return an enum's value or a plain string as text (schemas store either)."""
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _zone(name: str | None, fallback: ZoneInfo) -> ZoneInfo:
    try:
        return ZoneInfo(name) if name else fallback
    except (KeyError, ValueError):
        return fallback


def _sessions(user_id: int, tz: ZoneInfo, now: datetime, db: Session) -> list[coach_metrics.TrainingSession]:
    activities = activity_integration.list_user_activities_in_timeframe_by_types(
        user_id,
        list(activity_constants.ACTIVITY_ID_TO_NAME),
        now - timedelta(days=coach_constants.HISTORY_DAYS),
        now,
        db,
    )
    sessions = []
    for a in activities:
        if a.start_time is None:
            continue
        start = _utc(a.start_time)
        sessions.append(
            coach_metrics.TrainingSession(
                activity_id=a.id,
                local_start=start.astimezone(_zone(a.timezone, tz)),
                type_name=activity_constants.ACTIVITY_ID_TO_NAME.get(a.activity_type, "Workout"),
                is_run=a.activity_type in _RUN_TYPE_IDS,
                name=a.name or "Untitled",
                distance_m=float(a.distance or 0),
                moving_s=float(a.total_timer_time or a.total_elapsed_time or 0),
                elevation_m=a.elevation_gain,
                avg_hr=a.average_hr,
                max_hr=a.max_hr,
                avg_speed=a.average_speed,
                rpe=round(a.workout_rpe / 10) if a.workout_rpe else None,
                description=a.description,
                private_notes=a.private_notes,
            )
        )
    sessions.sort(key=lambda s: s.local_start)
    cutoff = now.astimezone(tz).date() - timedelta(days=coach_constants.RECENT_DETAIL_DAYS)
    recent_runs = {s.activity_id: s for s in sessions if s.is_run and s.local_date >= cutoff}
    for activity_id, session in recent_runs.items():
        session.laps.extend(
            coach_metrics.LapSummary(lap.total_distance, lap.total_timer_time, lap.avg_heart_rate, lap.intensity)
            for lap in activity_laps_integration.list_laps_for_requester(activity_id, user_id, db)
        )
    return sessions


def _sleep(user_id: int, db: Session) -> list[coach_metrics.SleepNight]:
    nights = []
    for n in health_sleep_integration.list_recent_sleep(user_id, coach_constants.RECOVERY_NIGHTS, db):
        if n.date is None:
            continue
        nights.append(
            coach_metrics.SleepNight(
                night=n.date,
                total_sleep_s=n.total_sleep_seconds,
                sleep_score=n.sleep_score_overall,
                resting_hr=n.resting_heart_rate,
                hrv_status=_enum_text(n.hrv_status),
                avg_stress=n.avg_stress_level,
                skin_temp_deviation=n.avg_skin_temp_deviation,
            )
        )
    return nights


def _read_athlete(user_id: int, profile: coach_schema.CoachProfileRead, now: datetime, db: Session) -> _AthleteData:
    user = users_integration.get_user(user_id, db)
    tz = _zone(users_integration.timezone_or_default(user.timezone if user else None), ZoneInfo("UTC"))
    now_local = now.astimezone(tz)
    today = now_local.date()
    sessions = _sessions(user_id, tz, now, db)
    sleep = _sleep(user_id, db)

    sleep_rhr = [n.resting_hr for n in sleep if n.resting_hr]
    rest_hr = profile.rest_hr or (round(statistics.median(sleep_rhr)) if sleep_rhr else None)
    observed_max = max((s.max_hr for s in sessions if s.max_hr), default=None)
    gender = _enum_text(user.gender) if user else None
    basics = coach_metrics.AthleteBasics(
        max_hr=profile.max_hr or observed_max,
        rest_hr=rest_hr,
        female=str(gender).lower().startswith("f") if gender is not None else False,
        threshold_pace_s_per_km=profile.threshold_pace_s_per_km,
    )
    for s in sessions:
        s.load = coach_metrics.session_load(s, basics)

    checkins = [
        c.model_copy(update={"created_at": _utc(c.created_at).astimezone(tz)})
        for c in coach_crud.list_checkins_since(user_id, now - timedelta(days=21), db)
    ]
    inputs = coach_context.ContextInputs(
        now_local=now_local,
        timezone=str(tz),
        athlete_name=user.name if user else "Athlete",
        birthdate=user.birthdate if user else None,
        gender=str(gender) if gender is not None else None,
        profile=profile,
        resolved_rest_hr=rest_hr,
        races=coach_crud.list_races(user_id, db),
        sessions=sessions,
        sleep=sleep,
        checkins=checkins,
        plan_by_date=coach_crud.list_plan(user_id, today - timedelta(days=14), today + timedelta(days=21), db),
    )
    return _AthleteData(inputs=inputs, today=today, language=profile.language or "English")


# --------------------------------------------------------------------------- requests
def get_dashboard(user_id: int, config: CoachConfig, now: datetime, db: Session) -> coach_schema.CoachDashboard:
    """Return everything the coach page shows.

    Args:
        user_id: The authenticated user.
        config: Coach configuration.
        now: Current instant.
        db: Database session.

    Returns:
        The dashboard.
    """
    profile = coach_crud.get_profile(user_id, db)
    status = resolve_model(profile, config, db)[1] if profile else None
    empty = coach_schema.CoachDashboard(
        configured=bool(status and status.usable) if profile else bool(config.api_key),
        model_status=status,
        profile=profile,
        races=coach_crud.list_races(user_id, db),
        report=None,
        latest_attempt=None,
        days=[],
        load=[],
        weeks=[],
        checkins=[],
    )
    if profile is None:
        return empty
    data = _read_athlete(user_id, profile, now, db)
    sessions, today = data.inputs.sessions, data.today
    start = coach_metrics.week_start(today)
    plan = coach_crud.list_plan(user_id, start, start + timedelta(days=13), db)
    by_day: dict[date, list[coach_metrics.TrainingSession]] = {}
    for s in sessions:
        by_day.setdefault(s.local_date, []).append(s)

    days = []
    for i in range(14):
        d = start + timedelta(days=i)
        done = by_day.get(d, [])
        days.append(
            coach_schema.CoachPlanDayRead(
                date=d,
                workout=plan.get(d),
                done_km=round(sum(s.distance_m for s in done if s.is_run) / 1000, 1),
                done_minutes=round(sum(s.moving_s for s in done) / 60),
                done_names=[s.name for s in done],
                status=coach_context.day_status(plan.get(d), done, past=d < today),
            )
        )
    planned_by_week: dict[date, float] = {}
    for d, w in plan.items():
        planned_by_week[coach_metrics.week_start(d)] = planned_by_week.get(coach_metrics.week_start(d), 0) + (
            w.distance_km or 0
        )
    weeks = [
        coach_schema.CoachWeekSummary(
            week=w["week"],
            run_km=w["run_km"],
            runs=w["runs"],
            run_hours=w["run_hours"],
            long_km=w["long_km"],
            load=w["load"],
            planned_km=round(planned_by_week[w["week"]], 1) if w["week"] in planned_by_week else None,
        )
        for w in coach_metrics.weekly_summary(sessions, today, weeks=16)
    ]
    next_week = start + timedelta(days=7)
    if next_week in planned_by_week:
        weeks.append(
            coach_schema.CoachWeekSummary(
                week=next_week,
                run_km=0,
                runs=0,
                run_hours=0,
                long_km=0,
                load=0,
                planned_km=round(planned_by_week[next_week], 1),
            )
        )
    return empty.model_copy(
        update={
            "report": coach_crud.get_latest_report(user_id, db, ok_only=True),
            "latest_attempt": coach_crud.get_latest_report(user_id, db, ok_only=False),
            "days": days,
            "load": [coach_schema.CoachLoadPoint(**p) for p in coach_metrics.load_series(sessions, today, days=120)],
            "weeks": weeks,
            "checkins": list(reversed(data.inputs.checkins))[:5],
        }
    )


def update_profile(
    user_id: int, data: coach_schema.CoachProfileUpdate, now: datetime, db: Session
) -> coach_schema.CoachProfileRead:
    """Save coach settings and ask for a fresh plan.

    Args:
        user_id: The authenticated user.
        data: New settings.
        now: Current instant.
        db: Database session.

    Returns:
        The stored profile.

    Raises:
        InvalidInputError: An OpenAI-compatible provider without a usable URL or model.
    """
    if data.llm_provider == coach_constants.LlmProvider.OPENAI_COMPATIBLE:
        if not data.llm_base_url or not data.llm_model:
            raise core_exceptions.InvalidInputError("An OpenAI-compatible provider needs a server URL and a model")
        _check_base_url(data.llm_base_url)
    profile = coach_crud.upsert_profile(user_id, data, db)
    coach_crud.mark_update_due(user_id, now + timedelta(seconds=30), "settings updated", db)
    db.commit()
    logger.info("Coach settings saved", extra=core_logger.context(user_id=user_id, enabled=data.enabled))
    return coach_crud.get_profile(user_id, db) or profile


def save_api_key(user_id: int, api_key: str, db: Session) -> coach_schema.CoachProfileRead:
    """Store the user's own API key, encrypted. Creates a (disabled) profile if needed.

    Args:
        user_id: The authenticated user.
        api_key: The plain key.
        db: Database session.

    Returns:
        The profile, showing only the key's last characters.
    """
    if coach_crud.get_profile(user_id, db) is None:
        coach_crud.upsert_profile(user_id, coach_schema.CoachProfileUpdate(enabled=False), db)
    key = api_key.strip()
    coach_crud.set_api_key(user_id, core_cryptography.encrypt_token_fernet(key), key[-4:], db)
    db.commit()
    logger.info("Coach API key saved", extra=core_logger.context(user_id=user_id))
    return coach_crud.get_profile(user_id, db)  # type: ignore[return-value]


def delete_api_key(user_id: int, db: Session) -> None:
    """Remove the user's own API key.

    Args:
        user_id: The authenticated user.
        db: Database session.
    """
    if coach_crud.set_api_key(user_id, None, None, db):
        db.commit()
        logger.info("Coach API key removed", extra=core_logger.context(user_id=user_id))


def check_model_connection(user_id: int, config: CoachConfig, db: Session) -> coach_schema.CoachConnectionTest:
    """Check the user's model settings against the provider, without generating a plan.

    Args:
        user_id: The authenticated user.
        config: Server defaults.
        db: Database session.

    Returns:
        Whether the provider accepted the credentials and offers the model.
    """
    profile = coach_crud.get_profile(user_id, db)
    if profile is None:
        return coach_schema.CoachConnectionTest(ok=False, detail="Save your coach settings first.")
    settings, status = resolve_model(profile, config, db)
    db.commit()  # no transaction across the network call
    if settings is None:
        return coach_schema.CoachConnectionTest(ok=False, detail=status.detail)
    if settings.base_url:
        _check_base_url(settings.base_url)
    try:
        detail = coach_engine.check_connection(settings)
    except (coach_engine.CoachEngineError, *coach_engine.PROVIDER_ERRORS) as err:
        logger.warning(
            "Coach connection test failed", extra=core_logger.context(user_id=user_id, error_type=type(err).__name__)
        )
        return coach_schema.CoachConnectionTest(ok=False, detail=_error_text(err))
    logger.info("Coach connection test passed", extra=core_logger.context(user_id=user_id))
    return coach_schema.CoachConnectionTest(ok=True, detail=detail)


def _error_text(err: Exception) -> str:
    """A short, key-free description of a provider error for the user."""
    status_code = getattr(err, "status_code", None)
    if status_code in (401, 403):
        return "The provider rejected the API key."
    if status_code == 404:
        return "The provider does not offer that model."
    if isinstance(err, coach_engine.CoachEngineError):
        return str(err)
    return f"The provider could not be reached ({type(err).__name__})."


def replace_races(
    user_id: int, races: list[coach_schema.CoachRaceWrite], now: datetime, db: Session
) -> list[coach_schema.CoachRaceRead]:
    """Replace the race calendar and ask for a fresh plan.

    Args:
        user_id: The authenticated user.
        races: The new races.
        now: Current instant.
        db: Database session.

    Returns:
        The stored races.
    """
    stored = coach_crud.replace_races(user_id, races, db)
    coach_crud.mark_update_due(user_id, now + timedelta(seconds=30), "races updated", db)
    db.commit()
    logger.info("Coach races replaced", extra=core_logger.context(user_id=user_id, races=len(stored)))
    return stored


def add_checkin(user_id: int, text: str, now: datetime, db: Session) -> coach_schema.CoachCheckinRead:
    """Store a check-in and ask for a fresh plan.

    Args:
        user_id: The authenticated user.
        text: The note.
        now: Current instant.
        db: Database session.

    Returns:
        The stored check-in.
    """
    checkin = coach_crud.create_checkin(user_id, text.strip(), db)
    coach_crud.mark_update_due(user_id, now + timedelta(seconds=20), "athlete check-in", db)
    db.commit()
    logger.info("Coach check-in stored", extra=core_logger.context(user_id=user_id, checkin_id=checkin.id))
    return checkin


def request_refresh(user_id: int, now: datetime, db: Session) -> bool:
    """Ask for an update now.

    Args:
        user_id: The authenticated user.
        now: Current instant.
        db: Database session.

    Returns:
        Whether the coach is enabled for this user (otherwise nothing was requested).
    """
    marked = coach_crud.mark_update_due(user_id, now, "manual refresh", db)
    db.commit()
    if marked:
        logger.info("Coach refresh requested", extra=core_logger.context(user_id=user_id))
    else:
        logger.warning("Coach refresh refused: coach not enabled", extra=core_logger.context(user_id=user_id))
    return marked


def get_latest_context(user_id: int, db: Session) -> str | None:
    """Return the context pack the coach saw on the user's latest update.

    Args:
        user_id: The authenticated user.
        db: Database session.

    Returns:
        The Markdown pack, or ``None`` before the first update.
    """
    return coach_crud.get_latest_context(user_id, db)


# --------------------------------------------------------------------------- events
def note_new_activity(user_id: int, now: datetime, db: Session) -> None:
    """Schedule a debounced update after a new activity, for users with the coach enabled.

    Args:
        user_id: The activity owner.
        now: Current instant.
        db: Database session.
    """
    due = now + timedelta(seconds=coach_constants.ACTIVITY_DEBOUNCE_SECONDS)
    if coach_crud.mark_update_due(user_id, due, "new activity", db):
        db.commit()
        logger.info("Coach update scheduled after new activity", extra=core_logger.context(user_id=user_id))


# --------------------------------------------------------------------------- scheduled updates
def _due_trigger(profile: coach_schema.CoachProfileRead, config: CoachConfig, now: datetime, db: Session) -> str | None:
    """Return why the user's update is due now, or ``None``."""
    if profile.update_due_at is not None and _utc(profile.update_due_at) <= now:
        return profile.update_trigger or "requested"
    last = coach_crud.get_latest_report(profile.user_id, db, ok_only=False)
    user = users_integration.get_user(profile.user_id, db)
    tz = _zone(users_integration.timezone_or_default(user.timezone if user else None), ZoneInfo("UTC"))
    local_now = now.astimezone(tz)
    if last is None:
        return "first plan"
    last_at = _utc(last.created_at)
    if local_now.hour >= config.daily_hour and last_at.astimezone(tz).date() < local_now.date():
        return "daily update"
    recent = activity_integration.list_user_activities_in_timeframe_by_types(
        profile.user_id, list(activity_constants.ACTIVITY_ID_TO_NAME), now - timedelta(days=3), now, db
    )
    if any(a.created_at and _utc(a.created_at) > last_at for a in recent):
        return "new activity"
    return None


def run_update(user_id: int, trigger: str, claimed_at: datetime, config: CoachConfig, db: Session) -> int | None:
    """Run one claimed update: read, ask the model, validate, store. Always releases the claim.

    Args:
        user_id: The user whose update was claimed.
        trigger: Why it runs.
        claimed_at: When it was claimed.
        config: Server defaults.
        db: Database session.

    Returns:
        The report id, or ``None`` when the profile disappeared or has no usable model.
    """
    profile = coach_crud.get_profile(user_id, db)
    settings = resolve_model(profile, config, db)[0] if profile and profile.enabled else None
    if profile is None or settings is None:
        coach_crud.release_update(user_id, claimed_at, db)
        db.commit()
        return None
    if settings.base_url:
        _check_base_url(settings.base_url)
    data = _read_athlete(user_id, profile, claimed_at, db)
    context_md = coach_context.build(data.inputs)
    report_id = coach_crud.create_report(user_id, trigger, settings.label, context_md, claimed_at, db)
    db.commit()  # end the read transaction before the slow model call

    def ask(previous_issues: list[str] | None) -> coach_engine.EngineResult:
        return coach_engine.generate_report(
            context_md, data.today, settings, language=data.language, previous_issues=previous_issues
        )

    try:
        result = ask(None)
        issues = coach_validation.plan_issues(result.report, data.today)
        if issues:
            logger.info(
                "Coach plan had issues; asking again", extra=core_logger.context(user_id=user_id, issues=len(issues))
            )
            result = ask(issues)
            issues = coach_validation.plan_issues(result.report, data.today)
        window = {(data.today + timedelta(days=i)).isoformat() for i in range(coach_constants.PLAN_DAYS)}
        coach_crud.replace_future_plan(
            user_id, data.today, [w for w in result.report.plan if w.date in window], report_id, db
        )
        coach_crud.set_coach_notes(user_id, result.report.coach_notes, db)
        coach_crud.finish_report(
            report_id, db, report=result.report.model_dump(mode="json"), validation_issues=issues, usage=result.usage
        )
    except (coach_engine.CoachEngineError, *coach_engine.PROVIDER_ERRORS) as err:
        db.rollback()
        logger.error("Coach update failed", extra=core_logger.context(user_id=user_id, error_type=type(err).__name__))
        coach_crud.finish_report(report_id, db, error=_error_text(err))
    except Exception:
        # Anything unexpected still ends the update as failed, so it is visible and not retried every pass.
        db.rollback()
        logger.exception("Coach update failed unexpectedly", extra=core_logger.context(user_id=user_id))
        coach_crud.finish_report(report_id, db, error="Unexpected error; see the server log")
    coach_crud.release_update(user_id, claimed_at, db)
    db.commit()
    return report_id


def run_due_updates(config: CoachConfig, now: datetime, db: Session) -> int:
    """Run every due update, one user at a time. Doubles as the net for missed activity events.

    Args:
        config: Server defaults; each user's own model settings are resolved per update.
        now: Current instant.
        db: Database session.

    Returns:
        Number of updates run.
    """
    ran = 0
    after = 0
    stale_before = now - timedelta(seconds=coach_constants.CLAIM_LEASE_SECONDS)
    while True:
        page = coach_crud.list_enabled_profiles(after, coach_constants.DUE_CHECK_BATCH, db)
        db.commit()
        if not page:
            return ran
        for profile in page:
            after = profile.user_id
            usable = resolve_model(profile, config, db)[0] is not None
            trigger = _due_trigger(profile, config, now, db) if usable else None
            db.commit()
            if trigger is None:
                continue
            claimed = coach_crud.claim_update(profile.user_id, now, stale_before, db)
            db.commit()
            if not claimed:
                logger.debug("Coach update already claimed", extra=core_logger.context(user_id=profile.user_id))
                continue
            run_update(profile.user_id, trigger, now, config, db)
            ran += 1


def load_config() -> CoachConfig:
    """Return the coach configuration from application settings and the API-key secret.

    Returns:
        The configuration.
    """
    return CoachConfig(
        api_key=core_config.read_secret("ANTHROPIC_API_KEY"),
        model=core_config.settings.COACH_MODEL,
        effort=core_config.settings.COACH_EFFORT,
        daily_hour=core_config.settings.COACH_DAILY_HOUR,
    )

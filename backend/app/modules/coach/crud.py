"""Persistence for the coach module. Stages writes (``flush``); the service owns the transaction."""

from datetime import date, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, and_, delete, or_, select, update
from sqlalchemy.orm import Session

import modules.coach.constants as coach_constants
import modules.coach.models as coach_models
import modules.coach.schema as coach_schema


# --------------------------------------------------------------------------- profile
def get_profile(user_id: int, db: Session) -> coach_schema.CoachProfileRead | None:
    """Return the user's coach profile, or ``None`` when they never set one up.

    Args:
        user_id: The user.
        db: Database session.

    Returns:
        The profile or ``None``.
    """
    row = db.get(coach_models.CoachProfile, user_id)
    return coach_schema.CoachProfileRead.model_validate(row) if row else None


def upsert_profile(user_id: int, data: coach_schema.CoachProfileUpdate, db: Session) -> coach_schema.CoachProfileRead:
    """Create or replace the editable part of the user's profile.

    Args:
        user_id: The user.
        data: The new settings.
        db: Database session.

    Returns:
        The stored profile.
    """
    row = db.get(coach_models.CoachProfile, user_id)
    if row is None:
        row = coach_models.CoachProfile(user_id=user_id)
        db.add(row)
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    db.flush()
    db.refresh(row)
    return coach_schema.CoachProfileRead.model_validate(row)


def set_coach_notes(user_id: int, notes: str, db: Session) -> None:
    """Replace the coach's long-term notes.

    Args:
        user_id: The user.
        notes: The new notes.
        db: Database session.
    """
    db.execute(
        update(coach_models.CoachProfile).where(coach_models.CoachProfile.user_id == user_id).values(coach_notes=notes)
    )
    db.flush()


def mark_update_due(user_id: int, due_at: datetime, trigger: str, db: Session) -> bool:
    """Ask for an update at ``due_at``, if the user has the coach enabled.

    Args:
        user_id: The user.
        due_at: When the update should run.
        trigger: Why.
        db: Database session.

    Returns:
        Whether a profile was marked.
    """
    result = cast(
        CursorResult[Any],
        db.execute(
            update(coach_models.CoachProfile)
            .where(coach_models.CoachProfile.user_id == user_id, coach_models.CoachProfile.enabled.is_(True))
            .values(update_due_at=due_at, update_trigger=trigger)
        ),
    )
    db.flush()
    return result.rowcount == 1


def list_enabled_profiles(after_user_id: int, limit: int, db: Session) -> list[coach_schema.CoachProfileRead]:
    """Return one page of enabled profiles, ordered by user id.

    Args:
        after_user_id: Return users with a larger id than this.
        limit: Page size.
        db: Database session.

    Returns:
        The page.
    """
    rows = db.execute(
        select(coach_models.CoachProfile)
        .where(coach_models.CoachProfile.enabled.is_(True), coach_models.CoachProfile.user_id > after_user_id)
        .order_by(coach_models.CoachProfile.user_id)
        .limit(limit)
    ).scalars()
    return [coach_schema.CoachProfileRead.model_validate(r) for r in rows]


def claim_update(user_id: int, now: datetime, stale_before: datetime, db: Session) -> bool:
    """Claim the user's update for this pass with one conditional ``UPDATE``.

    Args:
        user_id: The user.
        now: Claim time.
        stale_before: An earlier claim older than this is treated as abandoned.
        db: Database session.

    Returns:
        Whether this caller won the claim.
    """
    profile = coach_models.CoachProfile
    result = cast(
        CursorResult[Any],
        db.execute(
            update(profile)
            .where(
                profile.user_id == user_id,
                profile.enabled.is_(True),
                or_(profile.update_claimed_at.is_(None), profile.update_claimed_at < stale_before),
            )
            .values(update_claimed_at=now)
        ),
    )
    db.flush()
    return result.rowcount == 1


def release_update(user_id: int, claimed_at: datetime, db: Session) -> None:
    """Release the claim and clear the due mark unless it was set again after the claim.

    Args:
        user_id: The user.
        claimed_at: When the finished update was claimed.
        db: Database session.
    """
    profile = coach_models.CoachProfile
    db.execute(
        update(profile)
        .where(
            profile.user_id == user_id, and_(profile.update_due_at.is_not(None), profile.update_due_at <= claimed_at)
        )
        .values(update_due_at=None, update_trigger=None)
    )
    db.execute(update(profile).where(profile.user_id == user_id).values(update_claimed_at=None))
    db.flush()


# --------------------------------------------------------------------------- races
def list_races(user_id: int, db: Session) -> list[coach_schema.CoachRaceRead]:
    """Return the user's races, soonest first.

    Args:
        user_id: The user.
        db: Database session.

    Returns:
        The races.
    """
    rows = db.execute(
        select(coach_models.CoachRace)
        .where(coach_models.CoachRace.user_id == user_id)
        .order_by(coach_models.CoachRace.race_date)
    ).scalars()
    return [coach_schema.CoachRaceRead.model_validate(r) for r in rows]


def replace_races(
    user_id: int, races: list[coach_schema.CoachRaceWrite], db: Session
) -> list[coach_schema.CoachRaceRead]:
    """Replace the user's race list.

    Args:
        user_id: The user.
        races: The new list.
        db: Database session.

    Returns:
        The stored races.
    """
    db.execute(delete(coach_models.CoachRace).where(coach_models.CoachRace.user_id == user_id))
    db.add_all(coach_models.CoachRace(user_id=user_id, **r.model_dump()) for r in races)
    db.flush()
    return list_races(user_id, db)


# --------------------------------------------------------------------------- check-ins
def create_checkin(user_id: int, text: str, db: Session) -> coach_schema.CoachCheckinRead:
    """Store a check-in.

    Args:
        user_id: The user.
        text: The note.
        db: Database session.

    Returns:
        The stored check-in.
    """
    row = coach_models.CoachCheckin(user_id=user_id, text=text)
    db.add(row)
    db.flush()
    db.refresh(row)
    return coach_schema.CoachCheckinRead.model_validate(row)


def list_checkins_since(user_id: int, since: datetime, db: Session) -> list[coach_schema.CoachCheckinRead]:
    """Return check-ins created at or after ``since``, oldest first.

    Args:
        user_id: The user.
        since: Lower bound.
        db: Database session.

    Returns:
        The check-ins.
    """
    rows = db.execute(
        select(coach_models.CoachCheckin)
        .where(coach_models.CoachCheckin.user_id == user_id, coach_models.CoachCheckin.created_at >= since)
        .order_by(coach_models.CoachCheckin.created_at)
    ).scalars()
    return [coach_schema.CoachCheckinRead.model_validate(r) for r in rows]


# --------------------------------------------------------------------------- reports
def create_report(user_id: int, trigger: str, model: str, context_md: str, started_at: datetime, db: Session) -> int:
    """Store a running report and return its id.

    Args:
        user_id: The user.
        trigger: Why the update runs.
        model: Model id.
        context_md: The context pack.
        started_at: When the update started (its claim time), used as the report time.
        db: Database session.

    Returns:
        The new report id.
    """
    row = coach_models.CoachReport(
        user_id=user_id,
        trigger=trigger,
        model=model,
        status=coach_constants.ReportStatus.RUNNING.value,
        context_md=context_md,
        created_at=started_at,
    )
    db.add(row)
    db.flush()
    return row.id


def finish_report(
    report_id: int,
    db: Session,
    *,
    report: dict | None = None,
    validation_issues: list[str] | None = None,
    usage: dict | None = None,
    error: str | None = None,
) -> None:
    """Mark a report ``ok`` (with its content) or ``error`` (with the reason).

    Args:
        report_id: The report.
        db: Database session.
        report: The structured report, for success.
        validation_issues: Plan issues left after the retry.
        usage: Token usage.
        error: Failure reason; when set the report is marked ``error``.
    """
    status = coach_constants.ReportStatus.ERROR if error else coach_constants.ReportStatus.OK
    db.execute(
        update(coach_models.CoachReport)
        .where(coach_models.CoachReport.id == report_id)
        .values(
            status=status.value, report=report, validation_issues=validation_issues or None, usage=usage, error=error
        )
    )
    db.flush()


def get_latest_report(user_id: int, db: Session, *, ok_only: bool) -> coach_schema.CoachReportRead | None:
    """Return the user's newest report.

    Args:
        user_id: The user.
        db: Database session.
        ok_only: Only consider successful reports.

    Returns:
        The report or ``None``.
    """
    stmt = select(coach_models.CoachReport).where(coach_models.CoachReport.user_id == user_id)
    if ok_only:
        stmt = stmt.where(coach_models.CoachReport.status == coach_constants.ReportStatus.OK.value)
    row = db.execute(stmt.order_by(coach_models.CoachReport.id.desc()).limit(1)).scalar_one_or_none()
    return coach_schema.CoachReportRead.model_validate(row) if row else None


def get_latest_context(user_id: int, db: Session) -> str | None:
    """Return the context pack of the user's newest report.

    Args:
        user_id: The user.
        db: Database session.

    Returns:
        The Markdown context, or ``None`` when there is no report.
    """
    return db.execute(
        select(coach_models.CoachReport.context_md)
        .where(coach_models.CoachReport.user_id == user_id)
        .order_by(coach_models.CoachReport.id.desc())
        .limit(1)
    ).scalar_one_or_none()


# --------------------------------------------------------------------------- plan
def list_plan(user_id: int, start: date, end: date, db: Session) -> dict[date, coach_schema.CoachWorkout]:
    """Return planned workouts between two days, inclusive.

    Args:
        user_id: The user.
        start: First day.
        end: Last day.
        db: Database session.

    Returns:
        Workouts keyed by day.
    """
    rows = db.execute(
        select(coach_models.CoachPlanDay).where(
            coach_models.CoachPlanDay.user_id == user_id,
            coach_models.CoachPlanDay.plan_date >= start,
            coach_models.CoachPlanDay.plan_date <= end,
        )
    ).scalars()
    return {r.plan_date: coach_schema.CoachWorkout.model_validate(r.workout) for r in rows}


def replace_future_plan(
    user_id: int, from_date: date, workouts: list[coach_schema.CoachWorkout], report_id: int, db: Session
) -> None:
    """Replace every planned day from ``from_date`` on; earlier days stay for adherence.

    Args:
        user_id: The user.
        from_date: First day owned by the new plan.
        workouts: The new workouts (already limited to the plan window).
        report_id: The report that planned them.
        db: Database session.
    """
    db.execute(
        delete(coach_models.CoachPlanDay).where(
            coach_models.CoachPlanDay.user_id == user_id, coach_models.CoachPlanDay.plan_date >= from_date
        )
    )
    db.add_all(
        coach_models.CoachPlanDay(
            user_id=user_id,
            plan_date=date.fromisoformat(w.date),
            workout=w.model_dump(mode="json"),
            report_id=report_id,
        )
        for w in workouts
    )
    db.flush()


# --------------------------------------------------------------------------- user API key
def set_api_key(user_id: int, encrypted_key: str | None, hint: str | None, db: Session) -> bool:
    """Store (or clear, with ``None``) the user's encrypted API key.

    Args:
        user_id: The user.
        encrypted_key: The Fernet-encrypted key, or ``None`` to remove it.
        hint: The last characters of the plain key, or ``None``.
        db: Database session.

    Returns:
        Whether a profile existed to store it on.
    """
    result = cast(
        CursorResult[Any],
        db.execute(
            update(coach_models.CoachProfile)
            .where(coach_models.CoachProfile.user_id == user_id)
            .values(llm_api_key=encrypted_key, llm_api_key_hint=hint)
        ),
    )
    db.flush()
    return result.rowcount == 1


def get_encrypted_api_key(user_id: int, db: Session) -> str | None:
    """Return the user's encrypted API key, if they saved one.

    Args:
        user_id: The user.
        db: Database session.

    Returns:
        The encrypted key or ``None``.
    """
    return db.execute(
        select(coach_models.CoachProfile.llm_api_key).where(coach_models.CoachProfile.user_id == user_id)
    ).scalar_one_or_none()

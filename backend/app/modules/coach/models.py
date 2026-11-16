"""SQLAlchemy ORM models for the coach module."""

from datetime import date as date_type
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base, TimestampMixin


class CoachProfile(Base, TimestampMixin):
    """Per-user coach settings, the coach's long-term notes and the update schedule.

    Attributes:
        user_id: Owning user; one profile per user.
        enabled: Whether the user has opted in to the coach.
        max_hr: Maximum heart rate in bpm.
        rest_hr: Resting heart rate override in bpm (otherwise taken from sleep data).
        threshold_pace_s_per_km: Pace the athlete could hold for about an hour.
        experience: Running background in the athlete's words.
        available_days: Weekdays the athlete can train (``Mon`` .. ``Sun``).
        long_run_day: Preferred long-run weekday.
        max_weekly_hours: Upper limit on weekly training time.
        health: Injuries, conditions and medication notes.
        preferences: Surfaces, strength work, session likes and dislikes.
        constraints: Life schedule and travel.
        language: Language the coach writes in.
        primary_goal: The athlete's main goal in their own words.
        coach_notes: The coach's long-term memory about the athlete, rewritten each update.
        update_due_at: When the next update should run; ``None`` when nothing is pending.
        update_trigger: Why the pending update was requested.
        update_claimed_at: When a scheduler pass claimed the pending update.
        llm_provider: The user's model provider; ``None`` uses the server default (Anthropic).
        llm_model: The user's model id; ``None`` uses the server default.
        llm_base_url: API base URL for an OpenAI-compatible provider.
        llm_effort: Reasoning effort for Anthropic models; ``None`` uses the server default.
        llm_api_key: The user's own API key, Fernet-encrypted; never returned by the API.
        llm_api_key_hint: Last characters of the key, so the UI can show which key is saved.
    """

    __tablename__ = "coach_profiles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        comment="Owning user",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false", comment="User opted in"
    )
    max_hr: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Maximum heart rate (bpm)")
    rest_hr: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Resting heart rate override (bpm)")
    threshold_pace_s_per_km: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Threshold pace in seconds per km"
    )
    experience: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Running background")
    available_days: Mapped[list | None] = mapped_column(JSON, nullable=True, comment="Weekdays available to train")
    long_run_day: Mapped[str | None] = mapped_column(String(3), nullable=True, comment="Preferred long-run weekday")
    max_weekly_hours: Mapped[float | None] = mapped_column(Float, nullable=True, comment="Weekly training time cap")
    health: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Injuries and health notes")
    preferences: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Training preferences")
    constraints: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Life schedule and constraints")
    language: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="Coach output language")
    primary_goal: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Main goal in the athlete's words")
    coach_notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Coach long-term notes")
    update_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True, comment="When the next update should run"
    )
    update_trigger: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="Why the pending update was requested"
    )
    update_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When a scheduler pass claimed the update"
    )
    llm_provider: Mapped[str | None] = mapped_column(String(30), nullable=True, comment="Model provider")
    llm_model: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="Model id")
    llm_base_url: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="OpenAI-compatible base URL")
    llm_effort: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="Reasoning effort")
    llm_api_key: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Encrypted user API key")
    llm_api_key_hint: Mapped[str | None] = mapped_column(String(8), nullable=True, comment="Last characters of the key")


class CoachRace(Base, TimestampMixin):
    """A race on the athlete's calendar.

    Attributes:
        id: Surrogate primary key.
        user_id: Owning user.
        name: Race name.
        race_date: Race day.
        distance_km: Race distance in kilometres.
        target_time: Goal finish time as written by the athlete.
        priority: A, B or C.
        notes: Course or pacing notes.
    """

    __tablename__ = "coach_races"
    __table_args__ = (CheckConstraint("priority IN ('A', 'B', 'C')", name="ck_coach_races_priority"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="Owning user"
    )
    name: Mapped[str] = mapped_column(String(250), nullable=False, comment="Race name")
    race_date: Mapped[date_type] = mapped_column(Date, nullable=False, comment="Race day")
    distance_km: Mapped[float | None] = mapped_column(Float, nullable=True, comment="Race distance (km)")
    target_time: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="Goal finish time")
    priority: Mapped[str] = mapped_column(String(1), nullable=False, default="A", comment="A, B or C")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Race notes")


class CoachReport(Base, TimestampMixin):
    """One coach update: what the coach saw and what it wrote.

    Attributes:
        id: Surrogate primary key.
        user_id: Owning user.
        trigger: Why the update ran.
        model: Model that produced the report.
        status: ``running``, ``ok`` or ``error``.
        context_md: The context pack the coach received.
        report: The structured report, when ``ok``.
        validation_issues: Plan problems that remained after the retry.
        error: Failure description, when ``error``.
        usage: Token usage and request id.
    """

    __tablename__ = "coach_reports"
    __table_args__ = (CheckConstraint("status IN ('running', 'ok', 'error')", name="ck_coach_reports_status"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="Owning user"
    )
    trigger: Mapped[str] = mapped_column(String(100), nullable=False, comment="Why the update ran")
    model: Mapped[str] = mapped_column(String(100), nullable=False, comment="Model used")
    status: Mapped[str] = mapped_column(String(10), nullable=False, comment="running, ok or error")
    context_md: Mapped[str] = mapped_column(Text, nullable=False, comment="Context pack sent to the model")
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="Structured coach report")
    validation_issues: Mapped[list | None] = mapped_column(JSON, nullable=True, comment="Unresolved plan issues")
    error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Failure description")
    usage: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="Token usage")


class CoachPlanDay(Base, TimestampMixin):
    """The planned session for one day. Future days belong to the newest plan; past days are kept.

    Attributes:
        id: Surrogate primary key.
        user_id: Owning user.
        plan_date: The day.
        workout: The planned workout (text fields and device-neutral steps).
        report_id: The report that planned it.
    """

    __tablename__ = "coach_plan_days"
    __table_args__ = (UniqueConstraint("user_id", "plan_date", name="uq_coach_plan_days_user_date"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="Owning user"
    )
    plan_date: Mapped[date_type] = mapped_column(Date, nullable=False, comment="Planned day")
    workout: Mapped[dict] = mapped_column(JSON, nullable=False, comment="Planned workout")
    report_id: Mapped[int | None] = mapped_column(
        ForeignKey("coach_reports.id", ondelete="SET NULL"), nullable=True, comment="Report that planned it"
    )


class CoachCheckin(Base, TimestampMixin):
    """A free-text note from the athlete to the coach.

    Attributes:
        id: Surrogate primary key.
        user_id: Owning user.
        text: The note.
    """

    __tablename__ = "coach_checkins"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="Owning user"
    )
    text: Mapped[str] = mapped_column(Text, nullable=False, comment="Check-in text")

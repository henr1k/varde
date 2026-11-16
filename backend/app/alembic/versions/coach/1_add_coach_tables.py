"""Add the AI coach tables

Revision ID: 3c0ac4e51a01
Revises: c91ac2dad0f0
Create Date: 2026-11-15 21:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3c0ac4e51a01"
down_revision: str | None = "c91ac2dad0f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _user_fk(nullable: bool = False) -> sa.Column:
    return sa.Column(
        "user_id",
        sa.Integer(),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=nullable,
        comment="Owning user",
    )


def upgrade() -> None:
    op.create_table(
        "coach_profiles",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
            comment="Owning user",
        ),
        sa.Column("enabled", sa.Boolean(), server_default="false", nullable=False, comment="User opted in"),
        sa.Column("max_hr", sa.Integer(), nullable=True, comment="Maximum heart rate (bpm)"),
        sa.Column("rest_hr", sa.Integer(), nullable=True, comment="Resting heart rate override (bpm)"),
        sa.Column("threshold_pace_s_per_km", sa.Integer(), nullable=True, comment="Threshold pace in seconds per km"),
        sa.Column("experience", sa.Text(), nullable=True, comment="Running background"),
        sa.Column("available_days", sa.JSON(), nullable=True, comment="Weekdays available to train"),
        sa.Column("long_run_day", sa.String(3), nullable=True, comment="Preferred long-run weekday"),
        sa.Column("max_weekly_hours", sa.Float(), nullable=True, comment="Weekly training time cap"),
        sa.Column("health", sa.Text(), nullable=True, comment="Injuries and health notes"),
        sa.Column("preferences", sa.Text(), nullable=True, comment="Training preferences"),
        sa.Column("constraints", sa.Text(), nullable=True, comment="Life schedule and constraints"),
        sa.Column("language", sa.String(50), nullable=True, comment="Coach output language"),
        sa.Column("primary_goal", sa.Text(), nullable=True, comment="Main goal in the athlete's words"),
        sa.Column("coach_notes", sa.Text(), nullable=True, comment="Coach long-term notes"),
        sa.Column(
            "update_due_at", sa.DateTime(timezone=True), nullable=True, comment="When the next update should run"
        ),
        sa.Column("update_trigger", sa.String(100), nullable=True, comment="Why the pending update was requested"),
        sa.Column(
            "update_claimed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When a scheduler pass claimed the update",
        ),
        *_timestamps(),
    )
    op.create_index("ix_coach_profiles_update_due_at", "coach_profiles", ["update_due_at"])

    op.create_table(
        "coach_races",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        _user_fk(),
        sa.Column("name", sa.String(250), nullable=False, comment="Race name"),
        sa.Column("race_date", sa.Date(), nullable=False, comment="Race day"),
        sa.Column("distance_km", sa.Float(), nullable=True, comment="Race distance (km)"),
        sa.Column("target_time", sa.String(20), nullable=True, comment="Goal finish time"),
        sa.Column("priority", sa.String(1), nullable=False, comment="A, B or C"),
        sa.Column("notes", sa.Text(), nullable=True, comment="Race notes"),
        *_timestamps(),
        sa.CheckConstraint("priority IN ('A', 'B', 'C')", name="ck_coach_races_priority"),
    )
    op.create_index("ix_coach_races_user_id", "coach_races", ["user_id"])

    op.create_table(
        "coach_reports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        _user_fk(),
        sa.Column("trigger", sa.String(100), nullable=False, comment="Why the update ran"),
        sa.Column("model", sa.String(100), nullable=False, comment="Model used"),
        sa.Column("status", sa.String(10), nullable=False, comment="running, ok or error"),
        sa.Column("context_md", sa.Text(), nullable=False, comment="Context pack sent to the model"),
        sa.Column("report", sa.JSON(), nullable=True, comment="Structured coach report"),
        sa.Column("validation_issues", sa.JSON(), nullable=True, comment="Unresolved plan issues"),
        sa.Column("error", sa.Text(), nullable=True, comment="Failure description"),
        sa.Column("usage", sa.JSON(), nullable=True, comment="Token usage"),
        *_timestamps(),
        sa.CheckConstraint("status IN ('running', 'ok', 'error')", name="ck_coach_reports_status"),
    )
    op.create_index("ix_coach_reports_user_id", "coach_reports", ["user_id"])

    op.create_table(
        "coach_plan_days",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        _user_fk(),
        sa.Column("plan_date", sa.Date(), nullable=False, comment="Planned day"),
        sa.Column("workout", sa.JSON(), nullable=False, comment="Planned workout"),
        sa.Column(
            "report_id",
            sa.Integer(),
            sa.ForeignKey("coach_reports.id", ondelete="SET NULL"),
            nullable=True,
            comment="Report that planned it",
        ),
        *_timestamps(),
        sa.UniqueConstraint("user_id", "plan_date", name="uq_coach_plan_days_user_date"),
    )
    op.create_index("ix_coach_plan_days_user_id", "coach_plan_days", ["user_id"])

    op.create_table(
        "coach_checkins",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        _user_fk(),
        sa.Column("text", sa.Text(), nullable=False, comment="Check-in text"),
        *_timestamps(),
    )
    op.create_index("ix_coach_checkins_user_id", "coach_checkins", ["user_id"])


def downgrade() -> None:
    op.drop_table("coach_checkins")
    op.drop_table("coach_plan_days")
    op.drop_table("coach_reports")
    op.drop_table("coach_races")
    op.drop_table("coach_profiles")

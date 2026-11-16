"""Pydantic schemas for the coach: API shapes and the structured report the model returns.

The workout format is device-neutral. Every session, however loosely described for the athlete,
also carries ``steps`` with absolute targets, so an adapter can build a device workout from it
without asking the model again or knowing the athlete's zones.
"""

from datetime import date as date_type
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

import modules.coach.constants as coach_constants

StepKind = Literal["warmup", "active", "recovery", "rest", "cooldown"]
DurationType = Literal["time", "distance", "open"]
TargetType = Literal["pace", "hr", "hr_zone", "rpe", "none"]
WorkoutSport = Literal["run", "strength", "cross", "rest"]
WorkoutType = Literal[
    "easy",
    "recovery",
    "long",
    "tempo",
    "threshold",
    "intervals",
    "hills",
    "progression",
    "fartlek",
    "strides",
    "race",
    "rest",
    "cross",
    "strength",
]
Weekday = Literal["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]


# --------------------------------------------------------------------------- report the model returns
class CoachWorkoutStep(BaseModel):
    """One step of a workout.

    Attributes:
        kind: warmup, active, recovery, rest or cooldown.
        duration_type: ``time`` (seconds), ``distance`` (meters) or ``open`` (until lap press).
        duration_value: Seconds or meters; null only when ``duration_type`` is ``open``.
        target_type: pace, hr, hr_zone, rpe or none.
        target_low: Lower bound: pace in s/km (faster end), bpm, or RPE 1-10. Null for none.
        target_high: Upper bound: pace in s/km (slower end), bpm, or RPE 1-10. Null for none.
        zone: Heart-rate zone number for ``hr_zone`` (bounds still given in bpm).
        note: Short cue shown on the device.
    """

    kind: StepKind
    duration_type: DurationType
    duration_value: float | None = Field(description="Seconds for time, meters for distance, null for open")
    target_type: TargetType
    target_low: float | None = Field(description="pace: fastest s/km; hr/hr_zone: min bpm; rpe: min. null for none")
    target_high: float | None = Field(description="pace: slowest s/km; hr/hr_zone: max bpm; rpe: max. null for none")
    zone: int | None = Field(description="HR zone number when target_type is hr_zone, else null")
    note: str = Field(description="Short cue for the watch, '' if none")


class CoachRepeatKind(StrEnum):
    """Marks a repeat block. An enum (not a Literal) so the marker survives the API schema conversion."""

    REPEAT = "repeat"


class CoachInnerRepeat(BaseModel):
    """A repeat nested inside another repeat, e.g. the 4 x 400 m in 3 x (4 x 400 m)."""

    kind: CoachRepeatKind
    count: int
    steps: list[CoachWorkoutStep]


class CoachRepeat(BaseModel):
    """A block of steps repeated ``count`` times."""

    kind: CoachRepeatKind
    count: int
    steps: list[CoachWorkoutStep | CoachInnerRepeat]


class CoachWorkout(BaseModel):
    """One planned day."""

    date: str = Field(description="YYYY-MM-DD")
    type: WorkoutType
    sport: WorkoutSport
    title: str = Field(description="Short name, e.g. '6 x 1 km @ threshold'")
    distance_km: float | None = Field(description="Planned running distance, null for rest/strength/cross")
    duration_min: int | None = Field(description="Planned total duration in minutes, null for rest")
    target: str = Field(description="Pace/HR targets in words, e.g. '5:20-5:40/km, HR < 150'. '' for rest")
    structure: str = Field(description="Warm-up, main set, cool-down in words. '' for rest")
    purpose: str = Field(description="One sentence: why this session, here in the week")
    key: bool = Field(description="True for the 1-3 sessions per week that matter most")
    steps: list[CoachWorkoutStep | CoachRepeat] = Field(description="Device-neutral steps; empty only for rest days")


class CoachReadiness(BaseModel):
    """How the athlete is likely doing today."""

    status: Literal["fresh", "ready", "tired", "overreached", "returning"]
    note: str = Field(description="One or two sentences on why")


class CoachGoalProgress(BaseModel):
    """Progress toward one goal or race."""

    race: str = Field(description="The race name exactly as in the context, or 'general fitness'")
    on_track: Literal["ahead", "on_track", "at_risk", "off_track", "unknown"]
    predicted: str = Field(description="Realistic finish-time estimate with range, or ''")
    summary: str = Field(description="2-4 sentences on progress and what decides it from here")


class CoachReportOutput(BaseModel):
    """The structured report the model returns on every update."""

    headline: str = Field(description="One line to the athlete for today, max ~15 words")
    today_summary: str = Field(description="2-4 sentences: what to do today and how it should feel")
    readiness: CoachReadiness
    recent_assessment: str = Field(description="Read of the last 1-3 weeks; 1-3 short paragraphs, plain text")
    phase: str = Field(description="Current training phase, max ~12 words")
    week_focus: str = Field(description="Focus of this week in one or two sentences")
    plan: list[CoachWorkout] = Field(description="Exactly one entry per day from today through today+13")
    plan_changes: str = Field(description="What changed versus the previous plan and why; '' if first plan")
    goal_progress: list[CoachGoalProgress]
    flags: list[str] = Field(description="Warnings worth attention; empty if none")
    tips: list[str] = Field(description="0-3 short practical tips")
    coach_notes: str = Field(description="Updated long-term notes about the athlete, rewritten in full, max ~250 words")


# --------------------------------------------------------------------------- API shapes
class CoachProfileUpdate(BaseModel):
    """Editable coach settings."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool
    max_hr: StrictInt | None = Field(default=None, ge=100, le=230)
    rest_hr: StrictInt | None = Field(default=None, ge=25, le=110)
    threshold_pace_s_per_km: StrictInt | None = Field(default=None, ge=150, le=900)
    experience: StrictStr | None = Field(default=None, max_length=2000)
    available_days: list[Weekday] = Field(default_factory=lambda: list(coach_constants.WEEKDAYS))
    long_run_day: Weekday | None = None
    max_weekly_hours: float | None = Field(default=None, gt=0, le=40)
    health: StrictStr | None = Field(default=None, max_length=2000)
    preferences: StrictStr | None = Field(default=None, max_length=2000)
    constraints: StrictStr | None = Field(default=None, max_length=2000)
    language: StrictStr | None = Field(default=None, max_length=50)
    primary_goal: StrictStr | None = Field(default=None, max_length=2000)
    llm_provider: coach_constants.LlmProvider | None = None
    llm_model: StrictStr | None = Field(default=None, max_length=200)
    llm_base_url: StrictStr | None = Field(default=None, max_length=500)
    llm_effort: Effort | None = None


class CoachProfileRead(CoachProfileUpdate):
    """Coach settings as stored. The API key itself is never returned, only whether one is saved."""

    model_config = ConfigDict(from_attributes=True, extra="ignore")

    user_id: StrictInt
    update_due_at: datetime | None = None
    update_trigger: StrictStr | None = None
    coach_notes: StrictStr | None = None
    llm_api_key_hint: StrictStr | None = None


class CoachApiKeyUpdate(BaseModel):
    """A user's own API key for their model provider."""

    model_config = ConfigDict(extra="forbid")

    api_key: StrictStr = Field(min_length=8, max_length=500)


class CoachModelStatus(BaseModel):
    """Which model the coach will use for this user, and whether it can run."""

    usable: StrictBool
    provider: coach_constants.LlmProvider
    model: StrictStr | None
    key_source: Literal["own", "server", "none"]
    detail: StrictStr


class CoachConnectionTest(BaseModel):
    """Result of a connection test against the user's model provider."""

    ok: StrictBool
    detail: StrictStr


class CoachRaceWrite(BaseModel):
    """One race as submitted."""

    model_config = ConfigDict(extra="forbid")

    name: StrictStr = Field(min_length=1, max_length=250)
    race_date: date_type
    distance_km: float | None = Field(default=None, gt=0, le=500)
    target_time: StrictStr | None = Field(default=None, max_length=20)
    priority: coach_constants.RacePriority = coach_constants.RacePriority.A
    notes: StrictStr | None = Field(default=None, max_length=1000)


class CoachRaceRead(CoachRaceWrite):
    """A stored race."""

    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: StrictInt


class CoachCheckinCreate(BaseModel):
    """A new check-in."""

    model_config = ConfigDict(extra="forbid")

    text: StrictStr = Field(min_length=1, max_length=2000)


class CoachCheckinRead(CoachCheckinCreate):
    """A stored check-in."""

    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: StrictInt
    created_at: datetime


class CoachRefreshAccepted(BaseModel):
    """Acknowledgement that an update was requested."""

    detail: StrictStr


class CoachReportRead(BaseModel):
    """A coach update as shown to the athlete (without the full context pack)."""

    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: StrictInt
    created_at: datetime
    trigger: StrictStr
    model: StrictStr
    status: coach_constants.ReportStatus
    report: CoachReportOutput | None = None
    validation_issues: list[str] | None = None
    error: StrictStr | None = None


class CoachPlanDayRead(BaseModel):
    """One calendar day: what was planned and what was done."""

    date: date_type
    workout: CoachWorkout | None
    done_km: float
    done_minutes: int
    done_names: list[str]
    status: Literal["done", "partial", "over", "missed", "rest", "extra", "pending"] | None


class CoachLoadPoint(BaseModel):
    """Fitness, fatigue and form for one day."""

    date: date_type
    load: float
    ctl: float
    atl: float
    tsb: float


class CoachWeekSummary(BaseModel):
    """Running totals for one week."""

    week: date_type
    run_km: float
    runs: StrictInt
    run_hours: float
    long_km: float
    load: float
    planned_km: float | None = None


class CoachDashboard(BaseModel):
    """Everything the coach page shows."""

    configured: StrictBool
    model_status: CoachModelStatus | None = None
    profile: CoachProfileRead | None
    races: list[CoachRaceRead]
    report: CoachReportRead | None
    latest_attempt: CoachReportRead | None
    days: list[CoachPlanDayRead]
    load: list[CoachLoadPoint]
    weeks: list[CoachWeekSummary]
    checkins: list[CoachCheckinRead]

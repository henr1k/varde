"""Domain constants for the coach module."""

from enum import StrEnum
from typing import Final

#: Days covered by every plan the coach writes, starting today.
PLAN_DAYS: Final[int] = 14

#: How far back the context reads activities (enough for a realistic 42-day fitness value).
HISTORY_DAYS: Final[int] = 180

#: Window of sessions described in full detail (laps, notes) in the context.
RECENT_DETAIL_DAYS: Final[int] = 21

#: Nights of sleep and recovery data in the context.
RECOVERY_NIGHTS: Final[int] = 14

#: Delay after a new activity before the update runs, so several uploads become one update.
ACTIVITY_DEBOUNCE_SECONDS: Final[int] = 120

#: A claimed update older than this is considered abandoned and may be claimed again.
CLAIM_LEASE_SECONDS: Final[int] = 900

#: How often the scheduler looks for due updates, in minutes.
DUE_CHECK_INTERVAL_MINUTES: Final[int] = 2

#: Users examined per scheduler pass.
DUE_CHECK_BATCH: Final[int] = 50

#: Allowed mismatch between a workout's steps and its stated distance or duration.
STEP_TOTAL_TOLERANCE: Final[float] = 0.15

WEEKDAYS: Final[tuple[str, ...]] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


class ReportStatus(StrEnum):
    """Lifecycle of one coach update."""

    RUNNING = "running"
    OK = "ok"
    ERROR = "error"


class LlmProvider(StrEnum):
    """Where the coach's model runs.

    ``anthropic`` uses the official Anthropic SDK. ``openai_compatible`` covers any server that
    speaks the OpenAI chat-completions protocol: OpenAI, OpenRouter, Mistral, Groq, Gemini's
    compatibility endpoint, and local servers such as Ollama or LM Studio.
    """

    ANTHROPIC = "anthropic"
    OPENAI_COMPATIBLE = "openai_compatible"


class RacePriority(StrEnum):
    """A = the race the season is built around, B = important, C = training race."""

    A = "A"
    B = "B"
    C = "C"

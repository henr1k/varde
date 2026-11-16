"""Asks a language model for the structured coach report.

Two providers: Anthropic through its official SDK (structured outputs, prompt caching, refusal
fallback), and any OpenAI-compatible chat-completions server (OpenAI, OpenRouter, Mistral, Groq,
Gemini's compatibility endpoint, Ollama, LM Studio) through the ``openai`` SDK. Either way the
reply is validated against the same ``CoachReportOutput`` schema.

No session and no configuration reads: the caller passes ``LlmSettings`` and must not hold a
database transaction open while this runs (a call can take a few minutes).
"""

import json
from dataclasses import dataclass
from datetime import date, timedelta

import anthropic
import openai
import pydantic

import modules.coach.constants as coach_constants
import modules.coach.schema as coach_schema

#: Per-request timeout. Long because the model may think for a while on a full plan.
REQUEST_TIMEOUT_SECONDS = 600

SYSTEM_PROMPT = """You are an experienced, evidence-based running coach for one athlete, working inside a \
self-hosted training app. You are not in a chat: the athlete opens the app and reads what you produce, \
so your output must stand alone and be directly actionable.

Each update you get a context pack: the athlete's profile, goals and races, sleep and recovery data from \
their watch, training load, 16 weeks of history, every session from the last three weeks (laps, heart \
rate, the athlete's own notes), the plan you set before and how it went, check-ins, and your own \
long-term notes.

How you coach:
- Periodise backwards from the A-race (base, build, peak, taper; about 2-3 weeks of taper for a \
marathon, 10-14 days for a half, 7-10 days for 10K and shorter). Without a race, build durable aerobic \
fitness.
- Keep most running easy (roughly 80/20 by time): usually 1-2 quality sessions and one long run a week, \
never two hard days in a row.
- Progress volume gradually (about 5-10% a week, with a lighter week every 3-4 weeks); keep the CTL ramp \
and acute:chronic ratio sensible. The long run is rarely above 30-35% of weekly volume.
- Use recovery data: poor sleep, a resting HR well above the athlete's norm, low HRV status or high \
stress for several nights mean less intensity, not more.
- Set paces and heart rates from the athlete's actual recent data (laps, easy-run HR, races), not from \
the goal alone. If a goal looks unrealistic, say so kindly and propose a realistic one.
- Respect available days, the preferred long-run day, the weekly time cap and constraints. Plan rest days.
- Adapt to reality: a missed session is not made up by cramming. If pain or injury is mentioned, be \
conservative and recommend seeing a professional when it persists; you are not a medical provider.
- Keep continuity with the plan already on the calendar; change it when there is a reason and say why.
- Be specific (reps, recoveries, paces, durations), warm and direct. No filler.
- The plan has exactly one entry for each of the 14 days starting today, rest days included. If today's \
session is already done, today's entry describes what was done.

Every workout also needs device-neutral `steps` that a watch could execute without further input:
- Rest days: sport "rest" and an empty steps list. Every other day has steps.
- A step has a kind (warmup, active, recovery, rest, cooldown), a duration (time in seconds, distance in \
meters, or open = until the athlete presses lap; open only for warmup, recovery, rest and cooldown) and a \
target.
- Targets are absolute numbers: pace as seconds per km (target_low = fastest, target_high = slowest), \
heart rate in bpm, or RPE 1-10 when pace and HR make no sense (hills, strides, strength). hr_zone also \
gives the zone number plus its bpm bounds. Use target_type none only for genuinely unguided steps.
- Use repeat blocks (kind "repeat" with a count and its own steps) for anything that repeats: intervals \
(repeat 6 x [active 1000 m, recovery 90 s]), run/walk (repeat 6 x [active 2 min run, recovery 90 s walk]), \
strides. Never describe a repeat in a note instead of writing it out. One level of nesting is allowed.
- Loose sessions still get steps: an easy run is one active step with an easy pace or HR range; a \
progression run is several active steps; strides are a repeat of short RPE steps.
- The steps must add up to the stated distance_km and duration_min (within about 10%).
"""


@dataclass(frozen=True)
class LlmSettings:
    """Which model to call and how.

    Attributes:
        provider: ``anthropic`` or ``openai_compatible``.
        model: Model id as the provider names it.
        api_key: Secret for the provider; may be empty for a local OpenAI-compatible server.
        base_url: API base URL (OpenAI-compatible only; e.g. ``https://api.openai.com/v1``).
        effort: Reasoning effort (Anthropic only).
    """

    provider: coach_constants.LlmProvider
    model: str
    api_key: str | None
    base_url: str | None = None
    effort: str = "high"

    @property
    def label(self) -> str:
        """``provider/model`` for reports and logs."""
        return f"{self.provider.value}/{self.model}"


@dataclass(frozen=True)
class EngineResult:
    """The model's report and what the call cost."""

    report: coach_schema.CoachReportOutput
    usage: dict


class CoachEngineError(Exception):
    """The model returned no usable report."""


#: Errors from either provider SDK that mean the call itself failed.
PROVIDER_ERRORS: tuple[type[Exception], ...] = (anthropic.APIError, openai.APIError)

#: Anthropic models that accept the server-side refusal fallback.
_FALLBACK_MODEL_PREFIXES = ("claude-opus-5", "claude-sonnet-5-5", "claude-fable-5")


def _user_prompt(context_md: str, today: date, language: str, previous_issues: list[str] | None) -> str:
    last = today + timedelta(days=coach_constants.PLAN_DAYS - 1)
    prompt = (
        f"{context_md}\n\n---\nWrite today's coaching update for this athlete as the structured report. "
        f"The plan must cover {today.isoformat()} through {last.isoformat()}. "
        f"Write all athlete-facing text in {language}."
    )
    if previous_issues:
        prompt += "\n\nYour previous attempt had these problems with the plan; fix all of them:\n" + "\n".join(
            f"- {issue}" for issue in previous_issues
        )
    return prompt


def _anthropic_report(prompt: str, settings: LlmSettings) -> EngineResult:
    client = anthropic.Anthropic(api_key=settings.api_key, timeout=REQUEST_TIMEOUT_SECONDS)
    extra: dict = {}
    if settings.model.startswith(_FALLBACK_MODEL_PREFIXES):
        extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    with client.beta.messages.stream(
        model=settings.model,
        max_tokens=32000,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": prompt}],
        thinking={"type": "adaptive"},
        output_config={"effort": settings.effort},
        output_format=coach_schema.CoachReportOutput,
        **extra,
    ) as stream:
        message = stream.get_final_message()
        request_id = stream.request_id
    if message.stop_reason == "refusal":
        raise CoachEngineError(f"The model declined the request ({getattr(message.stop_details, 'category', None)})")
    if message.stop_reason == "max_tokens":
        raise CoachEngineError("The report hit the output limit before it was complete")
    if message.parsed_output is None:
        raise CoachEngineError("The model returned no structured report")
    usage = {
        "provider": settings.provider.value,
        "model": message.model,
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
        "cache_read_input_tokens": message.usage.cache_read_input_tokens,
        "request_id": request_id,
    }
    return EngineResult(report=message.parsed_output, usage=usage)


def _openai_client(settings: LlmSettings) -> openai.OpenAI:
    # Local servers (Ollama, LM Studio) ignore the key but the SDK requires a non-empty one.
    return openai.OpenAI(
        api_key=settings.api_key or "not-needed", base_url=settings.base_url, timeout=REQUEST_TIMEOUT_SECONDS
    )


def _openai_compatible_report(prompt: str, settings: LlmSettings) -> EngineResult:
    schema = coach_schema.CoachReportOutput.model_json_schema()
    system = (
        SYSTEM_PROMPT
        + "\nReply with a single JSON object that matches this JSON Schema, and nothing else:\n"
        + json.dumps(schema)
    )
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    client = _openai_client(settings)
    json_schema_format = {"type": "json_schema", "json_schema": {"name": "coach_report", "schema": schema}}
    try:
        completion = client.chat.completions.create(
            model=settings.model, messages=messages, response_format=json_schema_format
        )
    except openai.BadRequestError:
        # Some servers do not support JSON-schema output; plain JSON mode plus the schema in the prompt works.
        completion = client.chat.completions.create(
            model=settings.model, messages=messages, response_format={"type": "json_object"}
        )
    if not completion.choices:
        raise CoachEngineError("The model returned no answer")
    choice = completion.choices[0]
    if getattr(choice.message, "refusal", None):
        raise CoachEngineError("The model declined the request")
    if choice.finish_reason == "length":
        raise CoachEngineError("The report hit the output limit before it was complete")
    text = (choice.message.content or "").strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        report = coach_schema.CoachReportOutput.model_validate_json(text)
    except pydantic.ValidationError as err:
        raise CoachEngineError(
            f"The model's reply did not match the report format ({err.error_count()} errors)"
        ) from err
    usage = {
        "provider": settings.provider.value,
        "model": completion.model or settings.model,
        "input_tokens": completion.usage.prompt_tokens if completion.usage else None,
        "output_tokens": completion.usage.completion_tokens if completion.usage else None,
        "request_id": completion.id,
    }
    return EngineResult(report=report, usage=usage)


def generate_report(
    context_md: str,
    today: date,
    settings: LlmSettings,
    *,
    language: str,
    previous_issues: list[str] | None = None,
) -> EngineResult:
    """Ask the configured model for a coach report.

    Args:
        context_md: The context pack.
        today: The athlete's local today.
        settings: Provider, model and credentials.
        language: Language for athlete-facing text.
        previous_issues: Problems found in a previous attempt, to be fixed this time.

    Returns:
        The parsed report and usage.

    Raises:
        CoachEngineError: The model refused, ran out of tokens or returned no valid report.
        anthropic.APIError | openai.APIError: The API call failed.
    """
    prompt = _user_prompt(context_md, today, language, previous_issues)
    if settings.provider == coach_constants.LlmProvider.ANTHROPIC:
        return _anthropic_report(prompt, settings)
    return _openai_compatible_report(prompt, settings)


def check_connection(settings: LlmSettings) -> str:
    """Check that the credentials work and the model exists, without generating anything.

    Args:
        settings: Provider, model and credentials.

    Returns:
        A short confirmation.

    Raises:
        CoachEngineError: The model is not offered by the provider.
        anthropic.APIError | openai.APIError: The provider rejected the request.
    """
    if settings.provider == coach_constants.LlmProvider.ANTHROPIC:
        info = anthropic.Anthropic(api_key=settings.api_key, timeout=30).models.retrieve(settings.model)
        return f"Connected to Anthropic; {info.display_name} is available."
    models = [m.id for m in _openai_client(settings).with_options(timeout=30).models.list()]
    if models and settings.model not in models:
        raise CoachEngineError(f"Connected, but the server does not offer {settings.model}")
    return f"Connected; {settings.model} is available."

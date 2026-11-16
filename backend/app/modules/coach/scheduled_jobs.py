"""Scheduled work owned by the coach module."""

from datetime import UTC, datetime

import jasil.runtime as platform_runtime

import core.database as core_database
import core.logger as core_logger
import core.scheduler as core_scheduler
import modules.coach.constants as coach_constants
import modules.coach.service as coach_service

logger = core_logger.get_logger(__name__)

#: Coordination lock so only one replica runs a pass.
COACH_UPDATES_LOCK = "coach_updates"


def run_due_coach_updates() -> None:
    """Run every due coach update (daily updates, requested ones and missed activity events).

    Scheduler-invoked: opens its own session, reads the configuration here, and holds the
    coordination lock so only one replica runs a pass.
    """
    config = coach_service.load_config()
    with platform_runtime.get_active_platform().lock.try_acquire(COACH_UPDATES_LOCK) as acquired:
        if not acquired:
            logger.debug("Coach: another replica is running updates; skipping")
            return
        with core_database.SessionLocal() as db:
            ran = coach_service.run_due_updates(config, datetime.now(UTC), db)
    if ran:
        logger.info("Coach updates finished", extra=core_logger.context(count=ran))


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return the coach's recurring jobs.

    Returns:
        The jobs to schedule.
    """
    return (
        core_scheduler.ScheduledJob(
            run_due_coach_updates,
            coach_constants.DUE_CHECK_INTERVAL_MINUTES,
            "run due AI coach updates",
        ),
    )


def schedule_due_updates_now() -> None:
    """Queue one pass right away, e.g. after the athlete asks for a refresh."""
    core_scheduler.run_once(
        run_due_coach_updates, job_id="endurain_coach_due_updates_oneshot", description="AI coach update"
    )

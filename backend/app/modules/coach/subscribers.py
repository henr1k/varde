"""Event subscribers for the coach.

A new activity only marks the owner's update as due (cheap and idempotent); the scheduled pass in
``scheduled_jobs`` runs it. That pass also finds activities whose event was missed, so it is this
subscriber's reconciliation net.
"""

from datetime import UTC, datetime

import jasil.event_versioning as platform_event_versioning
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider
from jasil.subscribers import best_effort

import core.database as core_database
import core.logger as core_logger
import modules.activities.activity.events as activity_events
import modules.coach.service as coach_service

logger = core_logger.get_logger(__name__)

#: Stable durable-subscriber id, independent of module path.
COACH_ACTIVITY_SUBSCRIBER_ID = "coach.activity_created"


def note_activity_for_event(event: Event) -> None:
    """Mark the owner's coach update as due after a new activity; raises on failure.

    Args:
        event: The ``activity.created`` event.
    """
    payload = platform_event_versioning.parse_payload(activity_events.ActivityCreatedPayload, event)
    with core_database.SessionLocal() as db:
        coach_service.note_new_activity(payload.user_id, datetime.now(UTC), db)
    logger.debug("Coach noted new activity", extra=core_logger.context(user_id=payload.user_id))


on_activity_created_note_coach = best_effort(note_activity_for_event)


def register_coach_subscribers(events: EventBusProvider) -> None:
    """Register the coach's bus subscribers.

    Args:
        events: The event-bus provider to subscribe on.
    """
    events.subscribe(activity_events.ACTIVITY_CREATED, on_activity_created_note_coach)


def register_coach_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the coach's durable handlers.

    Args:
        registry: The durable-subscriber registry to register on.
    """
    registry.register(activity_events.ACTIVITY_CREATED, COACH_ACTIVITY_SUBSCRIBER_ID, note_activity_for_event)

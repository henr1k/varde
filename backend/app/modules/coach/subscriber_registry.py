"""Subscriber registration and reconciliation for the coach."""

from jasil.jobs.reconciliation import DurableSubscriberNet
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider

import modules.coach.scheduled_jobs as coach_scheduled_jobs
import modules.coach.subscribers as coach_subscribers


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register coach bus subscribers.

    Args:
        events: The event bus to subscribe on.
    """
    coach_subscribers.register_coach_subscribers(events)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register coach durable handlers.

    Args:
        registry: The durable-handler registry to register on.
    """
    coach_subscribers.register_coach_durable_handlers(registry)


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(coach_subscribers.COACH_ACTIVITY_SUBSCRIBER_ID, coach_scheduled_jobs.run_due_coach_updates),
)

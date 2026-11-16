"""Public read surface of health sleep for other modules."""

from sqlalchemy.orm import Session

import modules.health.health_sleep.crud as health_sleep_crud
import modules.health.health_sleep.schema as health_sleep_schema


def list_recent_sleep(user_id: int, nights: int, db: Session) -> list[health_sleep_schema.HealthSleepRead]:
    """Return the user's most recent sleep records, newest first.

    Args:
        user_id: The user.
        nights: Maximum number of records.
        db: Database session.

    Returns:
        Up to ``nights`` sleep records.
    """
    return health_sleep_crud.get_health_sleep_by_user_id(user_id, db, page_number=1, num_records=nights)

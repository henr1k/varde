"""Guards the migration history after merging upstream Endurain.

The coach migrations hang off an upstream revision. When upstream adds its own migration after it,
Alembic ends up with two heads and the app cannot start; this fails the build instead.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

_APP = Path(__file__).resolve().parents[2] / "app"


def test_migration_history_has_a_single_head():
    config = Config(str(_APP / "alembic.ini"))
    config.set_main_option("script_location", str(_APP / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1, f"Alembic has several heads {heads}; re-point the newest coach migration's down_revision"

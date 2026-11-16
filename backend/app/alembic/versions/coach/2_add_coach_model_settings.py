"""Add per-user model settings and API key to the coach profile

Revision ID: 3c0ac4e51a02
Revises: 3c0ac4e51a01
Create Date: 2026-11-16 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3c0ac4e51a02"
down_revision: str | None = "3c0ac4e51a01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    ("llm_provider", sa.String(30), "Model provider"),
    ("llm_model", sa.String(200), "Model id"),
    ("llm_base_url", sa.String(500), "OpenAI-compatible base URL"),
    ("llm_effort", sa.String(10), "Reasoning effort"),
    ("llm_api_key", sa.Text(), "Encrypted user API key"),
    ("llm_api_key_hint", sa.String(8), "Last characters of the key"),
)


def upgrade() -> None:
    for name, type_, comment in _COLUMNS:
        op.add_column("coach_profiles", sa.Column(name, type_, nullable=True, comment=comment))


def downgrade() -> None:
    for name, _type, _comment in reversed(_COLUMNS):
        op.drop_column("coach_profiles", name)

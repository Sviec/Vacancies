"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
## Схема сервиса построена на JSONB, TEXT[] и TSVECTOR, поэтому диалектный
## импорт нужен почти каждой ревизии. Условие обязательно: autogenerate сам
## кладёт эту же строку в ${imports}, когда встречает диалектный тип, и
## безусловная строка в шапке давала бы дубль импорта (F811). Ветка шаблона
## срабатывает только для ревизий без диалектных типов — там импорт не
## используется, отсюда noqa: F401.
<%
    dialect_import = "from sqlalchemy.dialects import postgresql"
    extra_imports = imports or ""
%>\
% if dialect_import not in extra_imports:
${dialect_import}  # noqa: F401
% endif
${extra_imports}
# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: str | Sequence[str] | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    """Upgrade schema."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Downgrade schema."""
    ${downgrades if downgrades else "pass"}

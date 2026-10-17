"""Учётные записи и сессии входа.

Revision ID: 7c1e0a4b9d22
Revises: ba833660ecb2
Create Date: 2026-10-17 21:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c1e0a4b9d22"
down_revision: str | None = "ba833660ecb2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_auth_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_auth_sessions_token_hash")),
    )
    op.create_index(op.f("ix_auth_sessions_user_id"), "auth_sessions", ["user_id"], unique=False)
    # Уже записанные резюме и действия ссылаются на user_id без строки users.
    # Эти учётки нельзя открыть: хеш пароля не формата scrypt.
    op.execute(
        """
        INSERT INTO users (id, email, password_hash)
        SELECT user_id,
               'legacy+' || user_id::text || '@invalid.local',
               '!'
        FROM (
            SELECT user_id FROM resumes
            UNION
            SELECT user_id FROM user_vacancy_actions
        ) AS existing
        """
    )
    op.create_foreign_key(
        op.f("fk_resumes_user_id_users"),
        "resumes",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        op.f("fk_user_vacancy_actions_user_id_users"),
        "user_vacancy_actions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_user_vacancy_actions_user_id_users"), "user_vacancy_actions", type_="foreignkey"
    )
    op.drop_constraint(op.f("fk_resumes_user_id_users"), "resumes", type_="foreignkey")
    op.drop_index(op.f("ix_auth_sessions_user_id"), table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("users")

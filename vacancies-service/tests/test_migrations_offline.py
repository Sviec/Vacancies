"""Офлайн-инварианты цепочки Alembic: без подключения к БД.

Проверяется, что ревизии не ветвятся, первая ревизия — корень, и `downgrade`
реально удаляет таблицы, а не заглушка `pass`.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

SERVICE_ROOT = Path(__file__).resolve().parents[1]


def _script_directory() -> ScriptDirectory:
    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_ROOT / "migrations"))
    return ScriptDirectory.from_config(config)


def test_single_head() -> None:
    heads = _script_directory().get_heads()
    assert len(heads) == 1, f"Цепочка ревизий ветвится: {heads}"


def test_initial_revision_is_root() -> None:
    script = _script_directory()
    heads = script.get_heads()
    revision = script.get_revision(heads[0])
    assert revision.down_revision is None


def test_initial_downgrade_drops_tables() -> None:
    script = _script_directory()
    revision = script.get_revision(script.get_heads()[0])
    source = Path(revision.path).read_text(encoding="utf-8")
    assert "op.drop_table" in source
    assert "pass" not in source.split("def downgrade")[-1]

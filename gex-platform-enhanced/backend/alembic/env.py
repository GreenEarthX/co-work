"""
Alembic environment — reads DATABASE_URL from app config.
Supports both online (live DB) and offline (generate SQL) migration modes.
"""
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Add backend root to path so app imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Credential selection — ALEMBIC_DATABASE_URL wins over DATABASE_URL.
#
# Migrations need DDL; the runtime must not have it. From migration 045 the two
# are different roles:
#
#     ALEMBIC_DATABASE_URL -> gex_owner / gex_user   (DDL, migrations only)
#     DATABASE_URL         -> gex_app                (runtime, RLS applies)
#
# The precedence matters in both directions. Pointing DATABASE_URL at the
# unprivileged runtime role must not break migrations; and a migration must
# never quietly run with the runtime credential, because DDL is not subject to
# RLS and would become an exfiltration path.
#
# NOTE: pydantic's `env_file` populates `settings`, NOT os.environ. Alembic
# reads os.getenv, so backend/.env does NOT reach this file — the variable has
# to be exported into the process environment.
database_url = os.getenv("ALEMBIC_DATABASE_URL") or os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

# Import target_metadata from models for autogenerate support
try:
    from app.db.models import Base
    target_metadata = Base.metadata
except ImportError:
    target_metadata = None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

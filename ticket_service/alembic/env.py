# ticket_service/alembic/env.py
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool, text
import sqlalchemy as sa # Bu importu ekliyoruz

from alembic import context

# Proje ana dizinini Python path'ine ekliyoruz
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Kendi servisimizin modellerini ve Base'ini import ediyoruz
from ticket_service.database import Base
from ticket_service import db_models

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()

# --- YENİ EKLENEN FONKSİYON ---
def process_revision_directives(context, revision, directives):
    """
    Modellerde tanımlı şemaların veritabanında otomatik oluşturulmasını sağlar.
    """
    connection = context.connection
    schemas_in_models = set()
    for table in target_metadata.tables.values():
        if table.schema:
            schemas_in_models.add(table.schema)
    
    if schemas_in_models:
        inspector = sa.inspect(connection)
        existing_schemas = set(inspector.get_schema_names())
        for schema in schemas_in_models - existing_schemas:
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            # YENİ EKLENDİ: Helper fonksiyonumuzu Alembic'e tanıtıyoruz
            process_revision_directives=process_revision_directives,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
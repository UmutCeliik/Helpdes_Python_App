import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool, text
import sqlalchemy as sa

from alembic import context

# --- 1. SİSTEM YOLU AYARI ---
# Alembic'in servis modüllerini (user_service, ticket_service) bulabilmesi için
# projenin ana dizinini Python'un arama yoluna ekliyoruz.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


# --- 2. MODEL IMPORT AYARI ---
# DİKKAT: Bu bölümü, bu dosyayı kopyaladığınız servise göre düzenleyin.
#
# user_service için bu satırları kullanın:
from user_service.database import Base
from user_service import db_models # Bu satır, Alembic'in modelleri tanıması için gereklidir

# ticket_service için bu satırları kullanın:
# from ticket_service.database import Base
# from ticket_service import db_models # Bu satır, Alembic'in modelleri tanıması için gereklidir


# --- 3. ALEMBIC YAPILANDIRMASI (DEĞİŞTİRMEYİN) ---
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


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        
        # --- SAĞLAM ŞEMA OLUŞTURMA YÖNTEMİ ---
        # Transaction başlamadan önce şemaları kontrol et ve oluştur.
        schemas_in_models = set()
        for table in target_metadata.tables.values():
            if table.schema:
                schemas_in_models.add(table.schema)
        
        if schemas_in_models:
            print(f"Veritabanı şemaları kontrol ediliyor: {schemas_in_models}")
            inspector = sa.inspect(connection)
            existing_schemas = set(inspector.get_schema_names())
            for schema in schemas_in_models - existing_schemas:
                print(f"Şema '{schema}' bulunamadı, oluşturuluyor...")
                connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
        
        # Şema oluşturma DDL komutunu hemen commit ediyoruz.
        connection.commit()
        # --- YÖNTEM SONU ---

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
        )

        with context.begin_transaction():
            print("Migrasyonlar çalıştırılıyor...")
            context.run_migrations()
            print("Migrasyonlar tamamlandı.")

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
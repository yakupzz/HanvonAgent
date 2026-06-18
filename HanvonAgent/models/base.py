"""
SQLAlchemy setup ve base model.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from core import app_paths

# Database — resolved via app_paths so GUI and Windows service share the same
# absolute file under %PROGRAMDATA%\HanvonAgent. HANVON_DB_PATH env var still
# overrides (used by tests / custom deployments).
DATABASE_PATH = str(app_paths.db_path())
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,  # Set to True for SQL debug
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base model
Base = declarative_base()


def init_db():
    """Create all tables (keep existing data).

    On first run at the new data_dir() location, migrate any legacy database
    (from %PROGRAMDATA%\\HanvonAgent or the project root) before the engine
    creates an empty file. This must happen before create_all so the copied
    data is preserved instead of being shadowed by a freshly created DB.
    """
    from sqlalchemy import inspect, text

    # Data migration: copy legacy DB into the new location if needed.
    # Idempotent — no-op when the new DB already exists.
    app_paths.migrate_legacy_db()

    Base.metadata.create_all(bind=engine)

    # Schema migration: employee_device_id sütunu ekle (varsa geç)
    inspector = inspect(engine)
    records_columns = [col['name'] for col in inspector.get_columns('records')]

    if 'pull_date' not in records_columns:
        with engine.connect() as conn:
            conn.execute(text('ALTER TABLE records ADD COLUMN pull_date VARCHAR(10)'))
            conn.commit()
        # Mevcut kayıtları file_path'ten backfill et
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT id, file_path, created_at FROM records WHERE pull_date IS NULL"
            )).fetchall()
            for row in rows:
                file_path = row[1]
                pull_date = None
                if file_path:
                    import re
                    m = re.search(r'(\d{4})[/\\](\d{2})[/\\](\d{2})\.json', file_path)
                    if m:
                        pull_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                if not pull_date and row[2]:
                    pull_date = str(row[2])[:10]
                if pull_date:
                    conn.execute(
                        text("UPDATE records SET pull_date = :pd WHERE id = :id"),
                        {"pd": pull_date, "id": row[0]}
                    )
            conn.commit()

    if 'employee_device_id' not in records_columns:
        with engine.connect() as conn:
            conn.execute(text('ALTER TABLE records ADD COLUMN employee_device_id VARCHAR(20)'))
            conn.commit()

    # Schema migration: employees tablosuna sync sütunları ekle (varsa geç)
    employees_columns = [col['name'] for col in inspector.get_columns('employees')]

    if 'sync_status' not in employees_columns:
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE employees ADD COLUMN sync_status VARCHAR(20) DEFAULT 'ok'"
            ))
            conn.commit()

    if 'pending_name' not in employees_columns:
        with engine.connect() as conn:
            conn.execute(text('ALTER TABLE employees ADD COLUMN pending_name VARCHAR(255)'))
            conn.commit()

    # Schema migration: biometrik yedek sütunları ekle (varsa geç)
    biometric_cols = {
        'face_data_json': 'TEXT',
        'calid':          'VARCHAR(50)',
        'opendoor_type':  'VARCHAR(50)',
        'biometric_synced_at': 'DATETIME',
    }
    for col_name, col_type in biometric_cols.items():
        if col_name not in employees_columns:
            with engine.connect() as conn:
                conn.execute(text(f'ALTER TABLE employees ADD COLUMN {col_name} {col_type}'))
                conn.commit()

    # Secret migration: düz metin CommKey'leri DPAPI ile şifrele (idempotent —
    # "dpapi:" prefix'li değerler atlanır). Hata olursa açılışı engelleme.
    try:
        from core.secret_store import encrypt_secret, is_encrypted
        from models.device import Device

        session = SessionLocal()
        try:
            migrated = 0
            for device in session.query(Device).all():
                if device.comm_key_encrypted and not is_encrypted(device.comm_key_encrypted):
                    device.comm_key_encrypted = encrypt_secret(device.comm_key_encrypted)
                    migrated += 1
            if migrated:
                session.commit()
        finally:
            session.close()
    except Exception:
        import logging
        logging.getLogger("HanvonAgent.DB").warning(
            "CommKey şifreleme migration'ı atlandı", exc_info=True
        )


def get_session():
    """Get database session."""
    return SessionLocal()

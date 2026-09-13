from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = BASE_DIR / "handyman.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


def ensure_schema():
    with engine.begin() as connection:
        inspector = inspect(connection)
        existing = set(inspector.get_table_names())
        for table_name in Base.metadata.tables:
            if table_name not in existing:
                Base.metadata.tables[table_name].create(bind=connection)
        for table_name, columns in {
            "users": [
                ("is_active", "BOOLEAN DEFAULT 1"),
                ("updated_at", "DATETIME"),
            ],
            "workers": [
                ("user_id", "INTEGER"),
                ("is_demo", "BOOLEAN DEFAULT 1"),
                ("service_areas", "VARCHAR(200) DEFAULT ''"),
                ("hourly_rate", "FLOAT DEFAULT 0"),
                ("availability_status", "VARCHAR(20) DEFAULT 'Available'"),
                ("max_concurrent_jobs", "INTEGER DEFAULT 3"),
                ("available_from", "DATETIME"),
                ("last_status_update", "DATETIME"),
            ],
            "customers": [
                ("user_id", "INTEGER"),
                ("is_demo", "BOOLEAN DEFAULT 1"),
                ("email", "VARCHAR(120)"),
                ("created_at", "DATETIME"),
            ],
            "jobs": [
                ("assigned_at", "DATETIME"),
                ("accepted_at", "DATETIME"),
                ("rejected_at", "DATETIME"),
            ],
            "payments": [
                ("job_id", "INTEGER"),
                ("customer_id", "INTEGER"),
                ("worker_id", "INTEGER"),
                ("amount", "FLOAT"),
                ("currency", "VARCHAR(3) DEFAULT 'INR'"),
                ("status", "VARCHAR(20) DEFAULT 'pending'"),
                ("payment_method", "VARCHAR(30) DEFAULT 'UPI_QR'"),
                ("upi_id", "VARCHAR(100)"),
                ("transaction_reference", "VARCHAR(100)"),
                ("qr_payload", "TEXT"),
                ("created_at", "DATETIME"),
                ("paid_at", "DATETIME"),
            ],
            "matching_evaluations": [
                ("source", "VARCHAR(20) DEFAULT 'live'"),
                ("benchmark_run_id", "VARCHAR(50)"),
                ("ground_truth_worker_id", "INTEGER"),
            ],
        }.items():
            if table_name not in existing:
                continue
            present = {column_info["name"] for column_info in inspector.get_columns(table_name)}
            for column_name, column_type in columns:
                if column_name in present:
                    continue
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

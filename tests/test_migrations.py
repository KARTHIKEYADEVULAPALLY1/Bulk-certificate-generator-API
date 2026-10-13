import tempfile
from pathlib import Path
from alembic import command
from alembic.config import Config
import sqlalchemy as sa

def test_alembic_upgrade_and_downgrade():
    """Verify that Alembic migrations run cleanly up to head and down to base on a fresh database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_migration.sqlite"
        db_url = f"sqlite:///{db_path}"

        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)

        # 1. Upgrade to head
        command.upgrade(alembic_cfg, "head")

        # 2. Inspect created schema
        engine = sa.create_engine(db_url)
        inspector = sa.inspect(engine)
        table_names = inspector.get_table_names()

        assert "jobs" in table_names
        assert "certificates" in table_names
        assert "alembic_version" in table_names

        # Verify columns on jobs table
        job_cols = {c["name"] for c in inspector.get_columns("jobs")}
        assert {"id", "status", "total", "succeeded", "failed", "created_at", "updated_at"}.issubset(job_cols)

        # Verify columns on certificates table
        cert_cols = {c["name"] for c in inspector.get_columns("certificates")}
        assert {
            "id", "job_id", "recipient_name", "recipient_email",
            "course_name", "issue_date", "status", "file_path", "error_message", "created_at"
        }.issubset(cert_cols)

        # 3. Downgrade to base
        command.downgrade(alembic_cfg, "base")
        inspector_after = sa.inspect(engine)
        tables_after = inspector_after.get_table_names()

        assert "jobs" not in tables_after
        assert "certificates" not in tables_after
        engine.dispose()

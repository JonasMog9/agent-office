import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def run_alembic(*args: str, db: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}"}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_migrations_upgrade_and_downgrade_cleanly(tmp_path: Path) -> None:
    db = tmp_path / "migrate.db"
    for args in (("upgrade", "head"), ("downgrade", "base"), ("upgrade", "head")):
        result = run_alembic(*args, db=db)
        assert result.returncode == 0, result.stderr


def test_migrations_have_a_single_head(tmp_path: Path) -> None:
    result = run_alembic("heads", db=tmp_path / "heads.db")
    assert result.returncode == 0, result.stderr
    assert len(result.stdout.strip().splitlines()) == 1

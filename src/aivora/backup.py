"""Online SQLite backup for the local pilot. Backups contain private workspace data."""

import argparse
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from .config import Settings


def backup(source, destination):
    source, destination = Path(source), Path(destination)
    if not source.is_file():
        raise ValueError("Source database does not exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Reserve a new path; never overwrite another backup or the live database.
    with destination.open("xb"):
        pass
    try:
        with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(destination)) as dst:
                src.backup(dst)
                if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Backup integrity verification failed")
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def main():
    parser = argparse.ArgumentParser(
        description="Create and integrity-check a private local SQLite backup"
    )
    parser.add_argument(
        "--output",
        default="data/backups/aivora-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S") + ".db",
    )
    args = parser.parse_args()
    url = make_url(Settings.from_env().database_url)
    if url.get_backend_name() != "sqlite" or not url.database:
        raise SystemExit("This command supports file-based SQLite only; use pg_dump for PostgreSQL")
    result = backup(url.database, args.output)
    print(
        f"Backup verified: {result}. Store securely; it contains private data and credential hashes."
    )


if __name__ == "__main__":
    main()

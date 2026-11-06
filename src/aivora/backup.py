"""Online SQLite backup for the local pilot. Backups contain private workspace data."""

import argparse
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from .config import Settings


def backup(source, destination, include_local_key=True):
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
    if include_local_key:
        key=source.resolve().parent/".aivora-secrets.key"
        if key.is_file():
            target=destination.resolve().parent/key.name
            if target.exists():
                if target.read_bytes()!=key.read_bytes():
                    raise ValueError("Backup key conflicts with an existing key; use a dedicated backup directory")
            else:
                import os
                with os.fdopen(os.open(str(target),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),"wb") as output:
                    output.write(key.read_bytes())
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
    settings=Settings.from_env()
    url = make_url(settings.database_url)
    if url.get_backend_name() != "sqlite" or not url.database:
        raise SystemExit("This command supports file-based SQLite only; use pg_dump for PostgreSQL")
    result = backup(url.database, args.output,include_local_key=not bool(settings.credential_key))
    print(
        f"Backup verified: {result}. Store securely; it contains private data and credential hashes."
    )


if __name__ == "__main__":
    main()

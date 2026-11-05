"""Persistent automation scheduler. Run separately from the web process."""

import argparse
import signal
import threading

from .automation import run_due
from .config import Settings
from .db import database


def main():
    parser = argparse.ArgumentParser(description="Run AIVORA's internal automation schedules")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    engine, factory = database(Settings.from_env().database_url)
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        while not stop.is_set():
            try:
                results = run_due(factory)
                if results:
                    print(f"Completed {len(results)} automation schedule(s)", flush=True)
            except Exception as error:
                # Do not log raw exception payloads, which can include SQL parameters.
                print(
                    f"Scheduler iteration failed ({type(error).__name__}); will retry",
                    flush=True,
                )
                if args.once:
                    raise SystemExit(1) from None
            if args.once:
                break
            stop.wait(30)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

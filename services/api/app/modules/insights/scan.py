"""Periodic scan CLI: `python -m app.modules.insights.scan [--loop --interval-minutes 360]`.

Runs the alert rules (and, if reachable, the AI severity estimate) for every patient so that
activity_drop / missed_reminders / score_drop fire even when a patient stops syncing.
Used by the optional `insights-scan` service in infra/docker-compose.yml.
"""
from __future__ import annotations

import argparse
import logging
import time
from contextlib import contextmanager

from app.core.db import get_session

from .pipeline import scan_all_patients

log = logging.getLogger("insights.scan")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loop", action="store_true", help="keep running instead of a single pass")
    parser.add_argument("--interval-minutes", type=int, default=360)
    parser.add_argument("--no-ai", action="store_true", help="skip AI calls (rules only)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    while True:
        with contextmanager(get_session)() as session:
            summary = scan_all_patients(session, use_ai=not args.no_ai)
        log.info("scan finished: %s", summary)
        if not args.loop:
            return 0
        time.sleep(max(1, args.interval_minutes) * 60)


if __name__ == "__main__":
    raise SystemExit(main())

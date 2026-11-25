"""Record an operator review from a local interactive terminal with the broker stopped."""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3
import sys

from local_bridge import SCOPE, StateBusy, StateLock
from relay.service import NativeTools
from relay.store import Ledger


def record_review(folder, job_id):
    NativeTools._job_id(job_id)
    folder = folder.resolve()
    journal = folder / "jobs.sqlite3"
    if not journal.is_file():
        raise ValueError("No existing journal in the supplied state folder")
    lock = StateLock(folder)
    try:
        with closing(Ledger(sqlite3.connect(journal.as_uri() + "?mode=rw", uri=True))) as ledger:
            ledger.record_operator_review(SCOPE, job_id)
    finally:
        lock.close()


def main():
    parser = argparse.ArgumentParser(description="Record a Capella operator's review of one uncertain edit")
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    try:
        NativeTools._job_id(args.job_id)
        if not sys.stdin.isatty():
            raise ValueError("Run this command yourself in an interactive terminal")
        print("Review the original batch in Capella and settle its effects before continuing.")
        print("Stop the Capella connector and quit Claude Desktop before recording the review.")
        confirmation = "REVIEWED " + args.job_id
        if input(f"Type {confirmation} to record your review: ") != confirmation:
            raise ValueError("Review was not recorded")
        record_review(args.state_dir, args.job_id)
        print("Review recorded. The original outcome and receipt are preserved. No edit was submitted.")
        return 0
    except StateBusy:
        print("The broker still owns the journal. Fully quit Claude Desktop and try again.", file=sys.stderr)
    except (EOFError, OSError, sqlite3.Error, ValueError) as failure:
        print(str(failure), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Explicit local Claude Desktop entry point; importing this file starts nothing."""
import argparse
import os
from pathlib import Path
import sys

from local_bridge import SharedBridge
from capella_groundwork.protocol import serve


def main():
    parser = argparse.ArgumentParser(description="Independent Capella MCP for Claude Desktop")
    parser.add_argument("--state-dir", type=Path)
    arguments = parser.parse_args()
    state = arguments.state_dir
    if state is None:
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            parser.error("LOCALAPPDATA unavailable; supply --state-dir explicitly")
        state = Path(base) / "IndependentCapellaMCP"
    try:
        with SharedBridge(state) as bridge:
            print("Capella local bridge ready. Enable the connector for a selected model in Capella.", file=sys.stderr)
            serve(sys.stdin.buffer, sys.stdout.buffer, bridge.protocol())
    except (OSError, ValueError, RuntimeError):
        print("Capella local bridge could not start. Check the state folder and that another copy is not running.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

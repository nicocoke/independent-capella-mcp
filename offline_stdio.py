"""Optional manual mock-only launcher. Never invoked during development tests."""
if __name__ == "__main__":
    import sys
    from capella_groundwork.protocol import serve
    if sys.argv[1:] != ["--mock-only"]:
        raise SystemExit("Requires --mock-only; no live mode is provided")
    serve(sys.stdin.buffer, sys.stdout.buffer)

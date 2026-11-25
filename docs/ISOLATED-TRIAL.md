# Disposable native regression

With Windows, Python 3.11 or later and JDK 17, run the native suite from a fresh checkout with the matching release update-site ZIP and the official Windows Capella 7.1.0 product archive.

```powershell
python -B native-runtime-tests/run_71.py --product-zip C:/downloads/capella-7.1.0.202606231255-win32-win32-x86_64.zip --update-site C:/downloads/capella-mcp-update-site-0.7.2-capella-7.1.0.zip --jdk C:/sdk/jdk-17 --work-dir work
```

The runner verifies the Capella archive's SHA-512, then extracts a fresh disposable product and creates private settings and a new workspace. It registers the shipping bundle and a test-only harness in that copy. The harness requires a marker and an exact workspace match before it creates its synthetic project. Results appear in `native-result.json` in the printed trial directory. The test registers bundles directly and measures native behavior. Eclipse p2 wizard installation, Claude Desktop, and broker forwarding require separate checks.

For the extracted Windows MCPB, run `tools/verify_stdio_handover.py` with `--extension EXTRACTED_FOLDER --work-dir PRIVATE_SCRATCH_PARENT`. The separate `tools/verify_local_multiprocess.py` uses the same argument names and requires permitted loopback communication. Both use their own job journal and synthetic inputs.

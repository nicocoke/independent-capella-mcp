"""Build a self-contained Windows x64 MCPB; never install it or launch Capella."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

PYTHON_SHA256 = "90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159"
PYTHON_URL = "https://www.python.org/ftp/python/3.14.10/python-3.14.10-embed-amd64.zip"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-zip", type=Path, required=True)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    package = Path(__file__).resolve().parents[1]
    if hashlib.sha256(args.python_zip.read_bytes()).hexdigest() != PYTHON_SHA256:
        raise ValueError("Portable Python does not match the official release SHA-256")
    args.stage.mkdir(parents=True, exist_ok=False)
    runtime = args.stage / "runtime"
    runtime.mkdir()
    with zipfile.ZipFile(args.python_zip) as archive:
        for member in archive.infolist():
            if Path(member.filename).name != member.filename:
                raise ValueError("Unexpected nested runtime archive entry")
        archive.extractall(runtime)
    (runtime / "python314._pth").write_text("python314.zip\n.\n../server\n", encoding="ascii")
    server = args.stage / "server"
    server.mkdir()
    for folder in ("capella_groundwork", "relay"):
        shutil.copytree(package / folder, server / folder, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for filename in ("local_stdio.py", "local_bridge.py", "local_reconcile.py", "development_http.py"):
        shutil.copyfile(package / filename, server / filename)
    manifest = {
        "manifest_version": "0.3", "name": "independent-capella-local",
        "display_name": "Independent Capella - Local", "version": "0.9.2",
        "description": "Inspect paired architectures and incrementally edit supported elements and diagram views in an explicitly paired Capella 7.1.0 model.",
        "long_description": "Development build for Windows x64. Requires the matching Capella plugin and manual pairing of a selected model. Changes remain unsaved. No public server, OAuth, separate Python installation or automatic Capella launch. Model summaries and requested results enter the Claude conversation when tools are used. Multiple Claude Chat, Cowork and Code processes share one local broker and one paired Capella session.",
        "author": {"name": "Independent Capella MCP project"},
        "server": {"type": "binary", "entry_point": "runtime/python.exe", "mcp_config": {
            "command": "${__dirname}/runtime/python.exe",
            "args": ["-I", "-B", "${__dirname}/server/local_stdio.py"]}},
        "compatibility": {"platforms": ["win32"]},
        "tools_generated": True,
        "keywords": ["capella", "mbse", "local", "diagrams"]}
    (args.stage / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (args.stage / "RUNTIME-PROVENANCE.json").write_text(json.dumps({
        "python_version": "3.14.10", "url": PYTHON_URL, "sha256": PYTHON_SHA256,
        "checksum_source": "https://www.python.org/downloads/release/python-31410/",
        "modification": "python314._pth restricts imports to bundled runtime and server; site disabled",
        "license": "runtime/LICENSE.txt"}, indent=2), encoding="utf-8")
    shutil.copyfile(package / "docs/CLAUDE-DESKTOP.md", args.stage / "README.md")
    for filename in ("CAPABILITIES.md", "NATIVE-0.7.2.md", "RECOVER-EDIT.md"):
        shutil.copyfile(package / "docs" / filename, args.stage / filename)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(args.stage.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(args.stage).as_posix())
    with zipfile.ZipFile(args.output) as archive:
        if archive.testzip() is not None:
            raise ValueError("MCPB archive integrity failed")
    print("Prepared", args.output.name, args.output.stat().st_size, "bytes")
    print("SHA256", hashlib.sha256(args.output.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()

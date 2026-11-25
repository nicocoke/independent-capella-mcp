"""Packaged stdio lifecycle without a connector; all processes and state belong to this test."""
import argparse
import json
from pathlib import Path
import uuid
from verify_local_multiprocess import Client


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--extension", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    trial = args.work_dir.resolve() / ("handover-" + uuid.uuid4().hex[:10])
    trial.mkdir(parents=True, exist_ok=False)
    profile = trial / "state/connection.json"
    clients, checks = [], []

    def check(label, condition):
        if not condition:
            raise AssertionError(label)
        checks.append(label)

    try:
        for role in ("Chat", "Cowork", "Code"):
            client = Client(args.extension.resolve(), trial, role)
            clients.append(client)
            check(role + " initialized", client.initialize()["serverInfo"]["version"] == "0.9.2")
            tools = {t["name"]: t for t in client.request("tools/list")["tools"]}
            check(role + " has six tools and inspection filters",
                  len(tools) == 6 and "links_to" in tools["capella_snapshot"]["inputSchema"]["properties"])
        check("Owner exposes private connection path",clients[0].tool("capella_connection")["connection_file"] == str(profile))
        clients[0].close(abrupt=True)
        check("First survivor acquires broker after abrupt exit",
              clients[1].tool("capella_connection")["connection_file"] == str(profile))
        clients[1].close()
        check("Last survivor acquires broker after clean exit",
              clients[2].tool("capella_connection")["connection_file"] == str(profile))
        result = clients[2].request("tools/call", {"name":"capella_snapshot","arguments":{"diagrams":True}})
        check("Unpaired final client has no model inventory", result["isError"])
    finally:
        for client in reversed(clients):
            if client.process.poll() is None:
                client.close()
    check("Final EOF removes private connection profile", not profile.exists())
    print(json.dumps({"fixture":"three packaged stdio clients, no connector","checks":checks},indent=2))


if __name__ == "__main__":
    main()


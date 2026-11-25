"""Exercise real packaged stdio processes with a synthetic HTTP connector only.

Never launches Capella or reads real projects/settings. All state is under a new
child of the explicitly supplied --work-dir. Every child process is owned here.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid


class Client:
    def __init__(self, extension, trial, name):
        self.sequence = 0
        self.responses = queue.Queue()
        self.log = (trial / (name + ".stderr.log")).open("wb")
        self.process = subprocess.Popen([str(extension / "runtime/python.exe"), "-I", "-B",
            str(extension / "server/local_stdio.py"), "--state-dir", str(trial / "state")],
            cwd=trial, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()

    def read(self):
        try:
            for line in self.process.stdout:
                self.responses.put(json.loads(line))
        except Exception as failure:
            self.responses.put(failure)
        finally:
            self.responses.put(RuntimeError("Stdio process closed"))

    def initialize(self):
        result = self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "Synthetic Claude multi-process regression", "version": "1"}})
        self.process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        self.process.stdin.flush()
        return result

    def request(self, method, parameters=None):
        self.sequence += 1
        message = {"jsonrpc": "2.0", "id": self.sequence, "method": method, "params": parameters or {}}
        self.process.stdin.write((json.dumps(message) + "\n").encode())
        self.process.stdin.flush()
        response = self.responses.get(timeout=20)
        if isinstance(response, Exception):
            raise response
        if response.get("id") != self.sequence or "error" in response:
            raise RuntimeError("MCP response rejected")
        return response["result"]

    def tool(self, name, arguments=None):
        result = self.request("tools/call", {"name": name, "arguments": arguments or {}})
        if result["isError"]:
            raise RuntimeError(result["content"][0]["text"])
        return result["structuredContent"]

    def close(self, abrupt=False):
        if self.process.poll() is None:
            if abrupt:
                self.process.terminate()
            else:
                self.process.stdin.close()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=10)
        if not self.process.stdin.closed:
            self.process.stdin.close()
        self.reader.join(timeout=5)
        self.process.stdout.close()
        self.log.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--extension", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--expect-legacy-failure", action="store_true")
    arguments = parser.parse_args()
    extension = arguments.extension.resolve()
    trial = arguments.work_dir.resolve() / ("multiprocess-" + uuid.uuid4().hex[:10])
    trial.mkdir(parents=True, exist_ok=False)
    profile = trial / "state/connection.json"
    clients = []
    report = {"status": "failed", "fixture": "synthetic connector, no Capella", "checks": []}

    def check(label, passed):
        report["checks"].append({"check": label, "passed": bool(passed)})
        if not passed:
            raise AssertionError(label)

    def client(name):
        instance = Client(extension, trial, name)
        clients.append(instance)
        instance.initialize()
        return instance

    def connector(route, body):
        configuration = json.loads(profile.read_text())
        port = int(configuration["origin"].rsplit(":", 1)[1])
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            connection.request("POST", route, json.dumps(body).encode(), {
                "Authorization": "Bearer " + configuration["token"], "Content-Type": "application/json"})
            response = connection.getresponse()
            result = json.loads(response.read())
            if response.status != 200:
                raise RuntimeError("Synthetic connector failed: " + repr(result))
            return result
        finally:
            connection.close()

    try:
        owner = client("chat")
        if arguments.expect_legacy_failure:
            try:
                client("cowork")
            except RuntimeError:
                check("0.4.0 reproduces second-process startup failure", True)
            else:
                check("0.4.0 reproduces second-process startup failure", False)
        else:
            follower = client("cowork")
            transient = client("code-probe")
            for instance in (owner, follower, transient):
                check("simultaneous MCP process discovers six tools", len(instance.request("tools/list")["tools"]) == 6)
                check("simultaneous MCP process reports same pairing path", instance.tool("capella_connection")["connection_file"] == str(profile))
            before = profile.read_bytes()
            transient.close()
            check("closing a secondary process keeps broker and profile", profile.read_bytes() == before)
            snapshot = {"model_id": "native-model", "revision": 0, "session_epoch": "synthetic-shared-epoch",
                "elements": [{"alias": "logical-system", "type": "LogicalComponent"},
                             {"alias": "root-function", "type": "LogicalFunction"}]}
            connector("/connector/snapshot", snapshot)
            check("follower reads owner's native inventory", follower.tool("capella_snapshot") == snapshot)
            package = Path(__file__).resolve().parents[1]
            plan = json.loads((package / "examples/native-monitoring.json").read_text())
            plan["base_revision"] = 0
            preview = follower.tool("capella_prepare", {"plan": plan})
            submission = {"plan": plan, "preview_digest": preview["preview_digest"], "request_id": "shared-synthetic-request"}
            with ThreadPoolExecutor(max_workers=2) as pool:
                jobs = list(pool.map(lambda instance: instance.tool("capella_submit", submission), (owner, follower)))
            check("concurrent client retries share exactly one job", jobs[0] == jobs[1] and jobs[0]["status"] == "queued")
            claimed = connector("/connector/claim", {})["job"]
            check("queued edit is claimed only once", claimed["job_id"] == jobs[0]["job_id"] and connector("/connector/claim", {})["job"] is None)
            owner.close(abrupt=True)
            persisted = follower.tool("capella_job", {"job_id": jobs[0]["job_id"]})
            check("surviving process takes ownership and preserves executing job", persisted["status"] == "executing")
            check("takeover expires stale snapshot", follower.request("tools/call", {"name": "capella_snapshot", "arguments": {}})["isError"])
            connector("/connector/snapshot", snapshot)
            check("takeover never reclaims executing edit", connector("/connector/claim", {})["job"] is None)
            receipt = {"job_id": claimed["job_id"], "lease": claimed["lease"],
                       "status": "succeeded_unsaved", "result": {"saved": False, "synthetic_receipt": True}}
            finished = connector("/connector/result", receipt)
            check("original lease receipt reconciles after owner crash", finished["status"] == "succeeded_unsaved")
            replacement = client("replacement-chat")
            check("replacement client sees same persisted receipt", replacement.tool("capella_job", {"job_id": jobs[0]["job_id"]}) == finished)
            check("cross-process duplicate submit does not queue another edit", replacement.tool("capella_submit", submission) == finished and connector("/connector/claim", {})["job"] is None)
            follower.close()
            check("follower promotes after clean owner EOF", replacement.tool("capella_job", {"job_id": jobs[0]["job_id"]}) == finished)
            connector("/connector/snapshot", snapshot)
            failed_job = replacement.tool("capella_submit", submission | {"request_id": "synthetic-uncertain"})
            claim = connector("/connector/claim", {})["job"]
            uncertain = connector("/connector/result", {"job_id": failed_job["job_id"], "lease": claim["lease"],
                  "status": "unknown_outcome", "result": {"error": "BasicIndexOutOfBoundsException"}})
            observer = client("observer")
            check("follower can read despite uncertain edit", observer.tool("capella_snapshot") == snapshot)
            check("follower identifies the blocking job", observer.tool("capella_connection")["edit_blocker"] ==
                  {"job_id": failed_job["job_id"], "status": "unknown_outcome"})
            denied = observer.request("tools/call", {"name": "capella_submit", "arguments":
                  submission | {"request_id": "new-while-blocked"}})
            check("new submission refused instead of sitting queued", denied["isError"] and
                  failed_job["job_id"] in denied["content"][0]["text"])
            observer.close()
            replacement.close()
            check("last owner EOF removes profile", not profile.exists())
            # Exercise the packaged review function against only this synthetic journal.
            subprocess.run([str(extension / "runtime/python.exe"), "-I", "-B", "-c",
                            "from pathlib import Path; import sys; from local_reconcile import record_review; "
                            "record_review(Path(sys.argv[1]), sys.argv[2])",
                            str(trial / "state"), failed_job["job_id"]], cwd=trial, check=True, timeout=15)
            recovered = client("recovery")
            connector("/connector/snapshot", snapshot)
            check("review persists across broker shutdown", recovered.tool("capella_connection")["edit_blocker"] is None)
            history = recovered.tool("capella_job", {"job_id": failed_job["job_id"]})
            check("review preserves the original outcome", history["status"] == uncertain["status"] and
                  history["result"] == uncertain["result"] and "operator_reviewed_at" in history)
            check("review does not replay earlier or denied edits", connector("/connector/claim", {})["job"] is None)
            new_job = recovered.tool("capella_submit", submission | {"request_id": "fresh-after-review"})
            check("fresh edit is claimable after review", connector("/connector/claim", {})["job"]["job_id"] == new_job["job_id"])
            recovered.close()
        report["status"] = "passed"
    except Exception as failure:
        report["error"] = repr(failure)
    finally:
        for instance in reversed(clients):
            instance.close()
    (trial / "result.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print("Evidence:", trial / "result.json")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

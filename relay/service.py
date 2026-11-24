"""Native job tools, explicitly injected into the MCP protocol by the relay."""
import hashlib
import json
from capella_groundwork.compiler import compile_plan
from capella_groundwork.core import validate_plan, PlanError, _identifier, _digest
from capella_groundwork.tools import plan_schema, _object
from .store import Conflict
from .preflight import check_references
from .inspection import QUERY, page


def native_catalogue():
    return [
        {"name": "capella_snapshot", "description": "Read the paired session's last published summary.",
         "inputSchema": _object(QUERY, [])},
        {"name": "capella_prepare", "description": "Compile a proposal against the last native revision; does not edit.",
         "inputSchema": _object({"plan": plan_schema(native=True)}, ["plan"])},
        {"name": "capella_submit", "description": "Queue an explicitly requested native edit. Result is a job, not edit completion.",
         "inputSchema": _object({"plan": plan_schema(native=True), "preview_digest": {"type": "string"},
                                 "request_id": {"type": "string"}}, ["plan", "preview_digest", "request_id"])},
        {"name": "capella_job", "description": "Read execution outcome; success may be unsaved.",
         "inputSchema": _object({"job_id": {"type": "string"}}, ["job_id"])},
        {"name": "capella_cancel", "description": "Cancel a queued job; cannot undo executing edits.",
         "inputSchema": _object({"job_id": {"type": "string"}}, ["job_id"])}]


class NativeTools:
    def __init__(self, ledger, scope):
        self.ledger, self.scope = ledger, scope

    def prepare(self, plan):
        validate_plan(plan, native=True)
        snapshot = self.ledger.snapshot(self.scope)
        if plan["model_id"] != snapshot["model_id"] or plan["base_revision"] != snapshot["revision"]:
            raise Conflict("Stale or wrong model")
        check_references(plan, snapshot)
        compiled = compile_plan(plan)
        compiled["session_epoch"] = snapshot["session_epoch"]
        # Bind the complete payload, including the native session incarnation.
        digest = hashlib.sha256(json.dumps(compiled, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return compiled, digest

    def call(self, name, arguments):
        try:
            definitions = {item["name"]: item for item in native_catalogue()}
            if name not in definitions or not isinstance(arguments, dict) or not set(definitions[name]["inputSchema"]["required"]) <= set(arguments) <= set(definitions[name]["inputSchema"]["properties"]):
                raise PlanError("Invalid tool or arguments")
            if name == "capella_snapshot":
                result = page(self.ledger.snapshot(self.scope), arguments)
            elif name == "capella_job":
                self._job_id(arguments["job_id"])
                result = self.ledger.get(self.scope, arguments["job_id"])
            elif name == "capella_cancel":
                self._job_id(arguments["job_id"])
                result = self.ledger.cancel(self.scope, arguments["job_id"])
            else:
                if name == "capella_submit":
                    validate_plan(arguments["plan"], native=True)
                    _identifier(arguments["request_id"])
                    retry = self.ledger.retry(self.scope, arguments["request_id"], _digest(arguments["plan"]), arguments["preview_digest"])
                    if retry is not None:
                        return {"content": [{"type": "text", "text": json.dumps(retry)}], "structuredContent": retry, "isError": False}
                compiled, digest = self.prepare(arguments["plan"])
                if name == "capella_prepare":
                    result = {"payload": compiled, "preview_digest": digest,
                              "validation": "Structure and published references checked; native validation occurs in the transaction"}
                else:
                    _identifier(arguments["request_id"])
                    if arguments["preview_digest"] != digest:
                        raise Conflict("Preview no longer matches")
                    result = self.ledger.submit(self.scope, arguments["request_id"], compiled)
            return {"content": [{"type": "text", "text": json.dumps(result)}],
                    "structuredContent": result, "isError": False}
        except (ValueError, TypeError, KeyError) as exc:
            return {"content": [{"type": "text", "text": str(exc)}], "isError": True}

    @staticmethod
    def _job_id(value):
        if not isinstance(value, str) or len(value) != 32 or any(c not in "0123456789abcdef" for c in value):
            raise PlanError("Invalid job identifier")

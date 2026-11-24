"""MCP-shaped catalogue and call results, without transport or installed SDK.

A future SDK adapter can expose these functions. This module never starts a server.
Tool annotations describe the mock service, not any future live adapter.
"""
from copy import deepcopy
from .core import FIELDS, NATIVE_FIELDS, MockEngine, PlanError


def _object(properties, required):
    return {"type": "object", "properties": properties, "required": required,
            "additionalProperties": False}


from .architecture import DIAGRAMS, CI_KINDS


def plan_schema(*, native=False):
    variants = []
    for kind, fields in sorted((NATIVE_FIELDS if native else FIELDS).items()):
        props = {field: {"type": "string", "minLength": 1, "maxLength": 160}
                 if field == "name" else
                 {"type": "string", "pattern": "^[a-zA-Z][a-zA-Z0-9_-]{0,63}$"}
                 for field in fields}
        props["op"] = {"const": kind}
        if kind == "create_diagram":
            props["kind"] = {"enum": list(DIAGRAMS)} if native else {"const": "LAB"}
        if kind == "create_configuration_item":
            props["kind"] = {"enum": list(CI_KINDS)}
        variants.append(_object(props, sorted(fields)))
    return _object({"version": {"type": "integer", "const": 1},
                    "model_id": {"type": "string", "pattern": "^[a-zA-Z][a-zA-Z0-9_-]{0,63}$"},
                    "base_revision": {"type": "integer", "minimum": 0},
                    "operations": {"type": "array", "minItems": 1, "maxItems": 200,
                                   "items": {"oneOf": variants}}},
                   ["version", "model_id", "base_revision", "operations"])


def catalogue():
    definitions = [
        ("capella_mock_snapshot", "Read only the synthetic in-memory model.", _object({}, []), True),
        ("capella_preview_plan", "Validate a plan against synthetic data; no Capella access.",
         _object({"plan": plan_schema()}, ["plan"]), True),
        ("capella_commit_mock", "Apply to synthetic memory only. Never edits Capella.",
         _object({"plan": plan_schema(), "preview_digest": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                  "request_id": {"type": "string", "pattern": "^[a-zA-Z][a-zA-Z0-9_-]{0,63}$"}},
                 ["plan", "preview_digest", "request_id"]), False),
    ]
    return [{"name": name, "description": description, "inputSchema": schema,
             "annotations": {"readOnlyHint": read_only, "destructiveHint": False,
                             "idempotentHint": True, "openWorldHint": False}}
            for name, description, schema, read_only in definitions]


class OfflineTools:
    def __init__(self):
        self.engine = MockEngine()

    def call(self, name, arguments):
        import json
        try:
            definitions = {tool["name"]: tool for tool in catalogue()}
            if not isinstance(name, str) or name not in definitions:
                raise PlanError("Unknown tool")
            expected = definitions[name]["inputSchema"]["required"]
            if not isinstance(arguments, dict) or set(arguments) != set(expected):
                raise PlanError("Unexpected or missing tool arguments")
            if name == "capella_mock_snapshot":
                result = self.engine.snapshot()
            elif name == "capella_preview_plan":
                result = self.engine.preview(arguments["plan"])
            else:
                result = self.engine.commit_mock(**arguments)
            return {"content": [{"type": "text", "text": json.dumps(result, sort_keys=True)}],
                    "structuredContent": deepcopy(result), "isError": False}
        except PlanError as exc:
            return {"content": [{"type": "text", "text": str(exc)}], "isError": True}

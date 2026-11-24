"""Synthetic model engine, deliberately independent of Capella and the filesystem.

The vocabulary is an intent contract, not Capella's metamodel serialization.
Only MockEngine can apply plans; no backend selection or dynamic code execution.
"""
from .architecture import OPERATIONS, DIAGRAMS, CI_KINDS
from copy import deepcopy
from hashlib import sha256
import json
import re
from threading import RLock


class PlanError(ValueError):
    pass


def _exact(value, required):
    if not isinstance(value, dict) or set(value) != set(required):
        raise PlanError("Object fields must be exactly: " + ", ".join(sorted(required)))


def _text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 160:
        raise PlanError("Expected nonempty text of at most 160 characters")


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]{0,63}", value):
        raise PlanError("Invalid identifier")


def _digest(plan):
    return sha256(json.dumps(plan, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True).encode()).hexdigest()


FIELDS = {
    "create_component": {"op", "id", "name", "parent"},
    "create_function": {"op", "id", "name", "parent"},
    "allocate_function": {"op", "id", "function", "component"},
    "connect_functions": {"op", "id", "name", "source", "target"},
    "create_diagram": {"op", "id", "name", "kind", "target"},
    "show_element": {"op", "id", "diagram", "element"},
}


NATIVE_FIELDS = dict(FIELDS)
for operation, (references, _) in OPERATIONS.items():
    fields = {"op","id",*references}
    if operation not in {"deploy_behavior","reassign_allocation","add_chain_function","add_chain_exchange",
                          "realize_capability","realize_function","realize_system_component",
                          "involve_operational_entity","involve_capability_path"}:
        fields.add("name")
    if operation == "create_configuration_item":
        fields.add("kind")
    NATIVE_FIELDS[operation] = fields


def validate_plan(plan, *, native=False):
    vocabulary = NATIVE_FIELDS if native else FIELDS
    _exact(plan, {"version", "model_id", "base_revision", "operations"})
    if type(plan["version"]) is not int or plan["version"] != 1:
        raise PlanError("Unsupported plan version")
    _identifier(plan["model_id"])
    if type(plan["base_revision"]) is not int or plan["base_revision"] < 0:
        raise PlanError("Invalid revision")
    operations = plan["operations"]
    if not isinstance(operations, list) or not 1 <= len(operations) <= 200:
        raise PlanError("Expected 1 to 200 operations")
    ids = set()
    for operation in operations:
        if not isinstance(operation, dict) or not isinstance(operation.get("op"), str):
            raise PlanError("Invalid operation")
        kind = operation["op"]
        if kind not in vocabulary:
            raise PlanError("Unsupported operation")
        _exact(operation, vocabulary[kind])
        for field, value in operation.items():
            if field in {"op", "kind"}:
                continue
            if field == "name":
                _text(value)
            else:
                _identifier(value)
        if operation["id"] in ids:
            raise PlanError("Duplicate operation identifier")
        ids.add(operation["id"])
        if "kind" in operation and not isinstance(operation["kind"], str):
            raise PlanError("Expected a named kind")
        if kind == "create_configuration_item" and operation["kind"] not in CI_KINDS:
            raise PlanError("Unsupported configuration item kind")
        if kind == "create_diagram" and operation["kind"] not in (DIAGRAMS if native else ("LAB",)):
            raise PlanError("Unsupported diagram kind" if native else "Only mock LAB diagrams are supported")


class MockEngine:
    """One synthetic model. Revision/receipt checks are serialized in this process."""

    def __init__(self):
        self._lock = RLock()
        self._state = {
            "model_id": "synthetic-monitoring", "revision": 0,
            "elements": {"logical-system": {"kind": "component", "name": "Synthetic System",
                                             "parent": None},
                         "root-function": {"kind": "function", "name": "Synthetic Root Function",
                                           "parent": None}},
            "allocations": {}, "diagrams": {}, "views": {},
        }
        self._receipts = {}

    def snapshot(self):
        with self._lock:
            return deepcopy(self._state)

    def _simulate(self, plan):
        validate_plan(plan)
        if plan["model_id"] != self._state["model_id"]:
            raise PlanError("Wrong model")
        if plan["base_revision"] != self._state["revision"]:
            raise PlanError("Stale revision; obtain a new preview")
        candidate = deepcopy(self._state)
        elements = candidate["elements"]

        def require(identifier, kind=None):
            element = elements.get(identifier)
            if element is None or (kind is not None and element["kind"] != kind):
                raise PlanError("Missing or wrong-kind reference: " + identifier)
            return element

        for operation in plan["operations"]:
            kind, identifier = operation["op"], operation["id"]
            if any(identifier in candidate[bucket]
                   for bucket in ("elements", "allocations", "diagrams", "views")):
                raise PlanError("Identifier already exists: " + identifier)
            if kind in {"create_component", "create_function"}:
                element_kind = kind.removeprefix("create_")
                require(operation["parent"], element_kind)
                elements[identifier] = {"kind": element_kind, "name": operation["name"],
                                        "parent": operation["parent"]}
            elif kind == "allocate_function":
                require(operation["function"], "function")
                require(operation["component"], "component")
                if any(a["function"] == operation["function"]
                       for a in candidate["allocations"].values()):
                    raise PlanError("Function already allocated in mock model")
                candidate["allocations"][identifier] = {
                    "function": operation["function"], "component": operation["component"]}
            elif kind == "connect_functions":
                require(operation["source"], "function")
                require(operation["target"], "function")
                if operation["source"] == operation["target"]:
                    raise PlanError("Self connections are outside this mock subset")
                elements[identifier] = {"kind": "functional_exchange", "name": operation["name"],
                                        "source": operation["source"], "target": operation["target"]}
            elif kind == "create_diagram":
                require(operation["target"], "component")
                candidate["diagrams"][identifier] = {
                    "kind": "LAB", "name": operation["name"], "target": operation["target"]}
            elif kind == "show_element":
                element = require(operation["element"])
                if operation["diagram"] not in candidate["diagrams"]:
                    raise PlanError("Missing diagram")
                visible = {v["element"] for v in candidate["views"].values()
                           if v["diagram"] == operation["diagram"]}
                if operation["element"] in visible:
                    raise PlanError("Element already visible")
                if element["kind"] == "functional_exchange" and not {
                    element["source"], element["target"]} <= visible:
                    raise PlanError("Show exchange endpoints before the exchange")
                candidate["views"][identifier] = {
                    "diagram": operation["diagram"], "element": operation["element"]}
        candidate["revision"] += 1
        return candidate

    def preview(self, plan):
        with self._lock:
            frozen_plan = deepcopy(plan)
            candidate = self._simulate(frozen_plan)
            return {"mode": "mock-only", "digest": _digest(frozen_plan),
                    "base_revision": frozen_plan["base_revision"],
                    "operation_count": len(frozen_plan["operations"]),
                    "candidate": candidate,
                    "limitations": ["Synthetic intent model only; no native Capella validation",
                                    "No native layout, ports, Parts or .aird persistence"]}

    def commit_mock(self, plan, preview_digest, request_id):
        with self._lock:
            frozen_plan = deepcopy(plan)
            validate_plan(frozen_plan)
            _identifier(request_id)
            digest = _digest(frozen_plan)
            if preview_digest != digest:
                raise PlanError("Plan does not match preview digest")
            if request_id in self._receipts:
                old_digest, receipt = self._receipts[request_id]
                if old_digest != digest:
                    raise PlanError("Request identifier reused for different plan")
                return deepcopy(receipt)
            candidate = self._simulate(frozen_plan)
            receipt = {"mode": "mock-only", "request_id": request_id,
                       "digest": digest, "revision": candidate["revision"],
                       "applied_operations": len(frozen_plan["operations"])}
            self._state = candidate
            self._receipts[request_id] = (digest, deepcopy(receipt))
            return receipt


def create_live_backend(*args, **kwargs):
    """A deliberate hard stop, not a configurable or discoverable connection."""
    raise PlanError("Live Capella access is not implemented or authorized in this groundwork")

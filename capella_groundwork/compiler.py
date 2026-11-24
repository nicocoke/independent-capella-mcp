"""Compile portable intent into explicit native work, without executing it.

Identifiers in this intermediate representation remain plan aliases. Native
lookup must use a caller-supplied binding table inside a single selected session.
"""
from copy import deepcopy
from .core import validate_plan, _digest


def compile_plan(plan):
    validate_plan(plan, native=True)
    commands = []
    for op in deepcopy(plan["operations"]):
        kind = op.pop("op")
        if kind == "create_component":
            recipe = "logical_component_with_part"
        elif kind == "create_function":
            recipe = "logical_function"
        elif kind == "allocate_function":
            recipe = "component_function_allocation"
        elif kind == "connect_functions":
            recipe = "functional_exchange_with_ports"
        elif kind == "create_diagram":
            recipe = "sirius_representation"
        elif kind == "show_element":
            recipe = "sirius_existing_element_view"
        else:
            recipe = kind
        commands.append({"recipe": recipe, **op})
    return {"contract": "capella-native-intent/1", "model_id": plan["model_id"],
            "expected_revision": plan["base_revision"], "plan_digest": _digest(plan),
            "commands": commands, "save": False,
            "requires": ["explicit_session_binding", "native_preflight", "exclusive_transaction",
                         "semantic_validation", "diagram_validation"]}

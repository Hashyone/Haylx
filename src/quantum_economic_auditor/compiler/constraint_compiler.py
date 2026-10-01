from __future__ import annotations

import re

from sympy import Eq, Ge, Le, Ne, parse_expr
from sympy.parsing.sympy_parser import standard_transformations

from quantum_economic_auditor.models.constraint import CompiledConstraint, Constraint
from quantum_economic_auditor.models.eir import EconomicIntermediateRepresentation


SOLIDITY_TO_SYMBOLIC_REPLACEMENTS = {
    "msg.sender": "sender",
    "msg.value": "value",
    "address(0)": "0",
}


def _sanitize_expression(expression: str) -> str:
    cleaned = expression.strip()
    for solidity_snippet, symbolic_text in SOLIDITY_TO_SYMBOLIC_REPLACEMENTS.items():
        cleaned = cleaned.replace(solidity_snippet, symbolic_text)
    cleaned = re.sub(r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*\(\)", r"\2", cleaned)
    cleaned = re.sub(r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)", r"\2", cleaned)
    cleaned = re.sub(r"\baddress\s*\(([^)]*)\)", r"\1", cleaned)
    cleaned = re.sub(r"\btrue\b", "1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bfalse\b", "0", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("&&", " and ")
    cleaned = cleaned.replace("||", " or ")
    return cleaned


def _split_constraint(normalized: str) -> tuple[str, str, str]:
    for operator in ("<=", ">=", "==", "!=", "=", "<", ">"):
        index = normalized.find(operator)
        if index != -1:
            lhs = normalized[:index].strip()
            rhs = normalized[index + len(operator) :].strip()
            return lhs, operator, rhs
    return normalized, "", ""


def _parse_side(side: str):
    normalized_side = _sanitize_expression(side)
    return parse_expr(normalized_side, transformations=standard_transformations)


def _compile_expression(expression: str) -> str:
    """Compile a protocol constraint string into a SymPy-aware symbolic form."""

    normalized = _sanitize_expression(expression)
    lhs, operator, rhs = _split_constraint(normalized)
    if not operator:
        return str(_parse_side(normalized))

    if operator in {"<=", "<"}:
        parsed = Le(_parse_side(lhs), _parse_side(rhs))
    elif operator in {">=", ">"}:
        parsed = Ge(_parse_side(lhs), _parse_side(rhs))
    elif operator == "!=":
        parsed = Ne(_parse_side(lhs), _parse_side(rhs))
    else:
        parsed = Eq(_parse_side(lhs), _parse_side(rhs))
    return str(parsed)


def compile_protocol_constraints(constraints: list[Constraint]) -> list[CompiledConstraint]:
    """Compile protocol constraints into deterministic symbolic expressions.

    The extractor emits structured textual expressions; the compiler then converts them
    into a symbolic form usable by the objective and encoding layers.
    """

    compiled: list[CompiledConstraint] = []
    for constraint in constraints:
        normalized = _sanitize_expression(constraint.expression)
        lhs, operator, rhs = _split_constraint(normalized)
        expression = _compile_expression(constraint.expression)
        if operator:
            lhs_expr = _parse_side(lhs)
            rhs_expr = _parse_side(rhs)
            symbol_map = {
                symbol.name: 1.0
                for symbol in lhs_expr.free_symbols.union(rhs_expr.free_symbols)
            }
        else:
            parsed_expression = _parse_side(normalized)
            symbol_map = {
                symbol.name: 1.0 for symbol in getattr(parsed_expression, "free_symbols", set())
            }
        compiled.append(
            CompiledConstraint(
                name=constraint.name,
                expression=expression,
                kind=constraint.kind,
                symbol_map=symbol_map,
            )
        )
    return compiled


def compile_eir_constraints(eir: EconomicIntermediateRepresentation) -> list[CompiledConstraint]:
    """Compile EIR invariants and objectives into deterministic symbolic constraints."""

    constraints: list[Constraint] = [
        Constraint(name=invariant.name, expression=invariant.expression, kind="equality" if "=" in invariant.expression else "inequality")
        for invariant in eir.invariants
    ]
    for objective in eir.objectives:
        constraints.append(Constraint(name=objective.name, expression=objective.expression, kind="objective"))

    compiled = compile_protocol_constraints(constraints)
    return compiled

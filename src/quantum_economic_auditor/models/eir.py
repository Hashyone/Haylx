from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

VariableCategory = Literal[
    "reserve",
    "collateral",
    "debt",
    "supply",
    "liquidity",
    "backing",
    "premium",
    "oracle_price",
    "interest_rate",
    "utilization",
    "share_supply",
    "capacity",
]

ActionKind = Literal["swap", "borrow", "repay", "deposit", "withdraw", "liquidate", "mint", "burn", "redeem", "flashloan", "bond"]
RelationshipKind = Literal["depends_on", "conserves", "updates", "consumes", "produces", "prices", "collateralizes"]
InvariantKind = Literal[
    "conservation",
    "collateralization",
    "constant_product",
    "supply_limit",
    "oracle_freshness",
    "debt_constraint",
]
ObjectiveKind = Literal["profit", "capital_efficiency", "gas_cost", "risk", "liquidity_usage"]


class EconomicVariable(BaseModel):
    """A typed economic variable in the protocol-level IR."""

    name: str
    category: VariableCategory
    description: str | None = None


class EconomicAction(BaseModel):
    """An economic action exposed by the protocol model."""

    name: str
    kind: ActionKind
    description: str | None = None


class EconomicRelationship(BaseModel):
    """A directional economic dependency between EIR nodes."""

    source: str
    relation: RelationshipKind
    target: str
    description: str | None = None


class EconomicInvariant(BaseModel):
    """A protocol invariant that becomes a symbolic mathematical constraint."""

    name: str
    kind: InvariantKind
    expression: str
    description: str | None = None


class EconomicObjective(BaseModel):
    """An objective expression that feeds the optimization engine."""

    name: str
    kind: ObjectiveKind
    expression: str
    weight: float = 1.0
    description: str | None = None


class EconomicIntermediateRepresentation(BaseModel):
    """Protocol-independent economics intermediate representation."""

    protocol_name: str
    variables: list[EconomicVariable] = Field(default_factory=list)
    actions: list[EconomicAction] = Field(default_factory=list)
    relationships: list[EconomicRelationship] = Field(default_factory=list)
    invariants: list[EconomicInvariant] = Field(default_factory=list)
    objectives: list[EconomicObjective] = Field(default_factory=list)

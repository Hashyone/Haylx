from __future__ import annotations

from pydantic import BaseModel, Field


class Actor(BaseModel):
    name: str
    permissions: list[str] = Field(default_factory=list)


class Role(BaseModel):
    name: str
    description: str | None = None


class TrustBoundary(BaseModel):
    name: str
    description: str | None = None


class CanonicalProtocolModel(BaseModel):
    protocol_name: str
    assets: list[str] = Field(default_factory=list)
    liabilities: list[str] = Field(default_factory=list)
    actors: list[Actor] = Field(default_factory=list)
    roles: list[Role] = Field(default_factory=list)
    trust_boundaries: list[TrustBoundary] = Field(default_factory=list)
    state_variables: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    accepted_tradeoffs: list[str] = Field(default_factory=list)
    invariants: list[str] = Field(default_factory=list)

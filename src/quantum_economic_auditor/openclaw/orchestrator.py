from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from quantum_economic_auditor.models.evidence import AgentEvidence


class CognitiveTarget(str, Enum):
    CLASSICAL = "classical"
    ML = "ml"
    QUANTUM = "quantum"
    SHARED = "shared"


class SpecialistAgent(ABC):
    """A specialist that produces evidence for the OpenClaw pipeline."""

    name: str = ""
    cognitive_targets: tuple[CognitiveTarget, ...] = (CognitiveTarget.SHARED,)

    @abstractmethod
    def run(self, payload: dict[str, Any]) -> list[AgentEvidence]:
        raise NotImplementedError


class OpenClawOrchestrator:
    """Route requests to specialist agents through a single entrypoint."""

    def __init__(self) -> None:
        self._agents: dict[str, SpecialistAgent] = {}

    def register_agent(self, agent: SpecialistAgent) -> None:
        self._agents[agent.name] = agent

    def run_agent(self, agent_name: str, payload: dict[str, Any]) -> list[AgentEvidence]:
        if agent_name not in self._agents:
            raise KeyError(f"Unknown agent: {agent_name}")
        return self._agents[agent_name].run(payload)

    def agents_for_target(self, target: CognitiveTarget) -> list[SpecialistAgent]:
        return [
            agent
            for agent in self._agents.values()
            if CognitiveTarget.SHARED in agent.cognitive_targets or target in agent.cognitive_targets
        ]

    def route_payload_by_target(self, payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Produce differentiated engine payloads from the same reconstructed protocol context."""
        return {
            CognitiveTarget.CLASSICAL.value: {
                "truth_layer": payload.get("truth_layer"),
                "constraint_graph": payload.get("constraint_graph"),
                "state_graph": payload.get("state_graph"),
                "evidence": payload.get("verified_evidence", []),
            },
            CognitiveTarget.ML.value: {
                "historical_patterns": payload.get("historical_patterns", []),
                "protocol_family": payload.get("protocol_family"),
                "reviewer_history": payload.get("reviewer_history", []),
                "accepted_findings": payload.get("accepted_findings", []),
                "rejected_findings": payload.get("rejected_findings", []),
            },
            CognitiveTarget.QUANTUM.value: {
                "protocol_graph": payload.get("protocol_graph"),
                "semantic_dossiers": payload.get("semantic_dossiers", []),
                "evidence_graph": payload.get("evidence_graph"),
                "expectation_graph": payload.get("expectation_graph"),
                "investigation_reports": payload.get("investigation_reports", []),
            },
        }

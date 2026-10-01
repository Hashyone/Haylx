from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PipelinePersistence:
    path: Path

    def write(self, payload: dict[str, Any]) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return self.path


@dataclass
class ValidationFinding:
    category: str
    severity: str
    summary: str
    evidence: str
    intended_behavior: bool


@dataclass
class ValidationResult:
    is_valid: bool
    issues: list[str] = field(default_factory=list)
    findings: list[ValidationFinding] = field(default_factory=list)


class IntentAwareValidationGate:
    """Assess whether a pattern is likely intentional protocol behavior or a real vulnerability."""

    def evaluate(self, *, evidence_text: str, invariants: list[str], known_issues: list[str] | None = None) -> ValidationResult:
        lowered = evidence_text.lower()
        findings: list[ValidationFinding] = []
        issues: list[str] = []
        known_issues = known_issues or []

        suspicious_terms = [term for term in ("reentrancy", "delegatecall", "selfdestruct", "unchecked", "overflow", "front-run", "oracle", "pause") if term in lowered]
        if suspicious_terms:
            aligned = any(invariant.lower() in lowered or any(token in lowered for token in ("guard", "check", "safety", "solvency")) for invariant in invariants)
            findings.append(
                ValidationFinding(
                    category="behavioral_consistency",
                    severity="warning" if aligned else "high",
                    summary="Suspicious code pattern detected",
                    evidence=", ".join(suspicious_terms),
                    intended_behavior=aligned,
                )
            )
            if not aligned:
                issues.append("Observed pattern may indicate an exploitable weakness")

        if known_issues:
            findings.append(
                ValidationFinding(
                    category="known_risk_context",
                    severity="info",
                    summary="Known issues were provided for the target scope",
                    evidence="; ".join(known_issues),
                    intended_behavior=True,
                )
            )

        if not findings:
            findings.append(
                ValidationFinding(
                    category="no_suspicious_behavior",
                    severity="info",
                    summary="No suspicious behavior surfaced from the current evidence",
                    evidence="",
                    intended_behavior=True,
                )
            )

        return ValidationResult(is_valid=not issues, issues=issues, findings=findings)

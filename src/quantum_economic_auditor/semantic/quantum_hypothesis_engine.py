from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import re
from typing import Iterable

from quantum_economic_auditor.parser.repository_loader import RepositoryModel
from quantum_economic_auditor.semantic.protocol_pattern_engine import ResearchHypothesis

try:
    import pennylane as qml
except ImportError:  # pragma: no cover - optional runtime dependency
    qml = None


@dataclass(slots=True)
class _FunctionCandidate:
    contract: str
    function: str
    signature: str
    file: str
    subsystem_hint: str
    risk_weight: float
    exploit_role: str


class QuantumHypothesisEngine:
    """Generate executable adversarial hypotheses from quantum search over callable paths."""

    def __init__(self, *, max_qubits: int = 6, max_hypotheses: int = 4) -> None:
        self.max_qubits = max(2, max_qubits)
        self.max_hypotheses = max(1, max_hypotheses)

    def generate(
        self,
        *,
        repository_model: RepositoryModel,
        pattern_label: str,
        pattern_id: str,
        existing_hypothesis_ids: Iterable[str] = (),
    ) -> list[ResearchHypothesis]:
        candidates = self._extract_function_candidates(repository_model)
        if len(candidates) < 2:
            return []

        ranked = sorted(candidates, key=lambda item: item.risk_weight, reverse=True)
        selected = ranked[: self.max_qubits]
        bitstrings = self._quantum_rank_bitstrings(selected)

        existing = set(existing_hypothesis_ids)
        hypotheses: list[ResearchHypothesis] = []
        for index, bitstring in enumerate(bitstrings):
            subset = [selected[pos] for pos, bit in enumerate(bitstring) if bit == "1"]
            if len(subset) < 2:
                continue

            ordered = self._order_attack_path(subset)
            attack_sequence = [
                f"attacker calls {item.contract}.{item.signature}"
                for item in ordered
            ]
            actors = self._derive_actors(ordered)
            threat_vectors = [
                f"path_role:{item.exploit_role}:{item.contract}.{item.function}"
                for item in ordered[:4]
            ]
            dominant_subsystem = max(
                (item.subsystem_hint for item in ordered),
                key=lambda hint: sum(1 for item in ordered if item.subsystem_hint == hint),
            )

            hid = self._next_hypothesis_id(pattern_id=pattern_id, index=index, existing=existing)
            existing.add(hid)
            risk_score = round(sum(item.risk_weight for item in ordered) / len(ordered), 3)
            required_capital = max(1, int(1000 * risk_score))
            predicted_profit = max(1, int(200 * risk_score * len(ordered)))

            hypotheses.append(
                ResearchHypothesis(
                    hypothesis_id=hid,
                    title=f"Quantum path: {ordered[0].contract} -> {ordered[-1].contract}",
                    rationale=(
                        "Quantum superposition search selected an entangled multi-function path with high "
                        "invariant-break potential that template generation does not prioritize."
                    ),
                    missing_subsystem=dominant_subsystem,
                    pattern_label=pattern_label,
                    expected_guarantees=[
                        "State transition chain remains safe under adversarial ordering",
                        "Economic extraction cannot exceed protocol accounting deltas",
                    ],
                    canonical_math=[
                        "attacker_delta + protocol_delta + victim_delta + fees = 0",
                        "post_invariant <= pre_invariant implies protective control activation",
                    ],
                    threat_vectors=["quantum_superposition_path_search", *threat_vectors],
                    priority="high" if risk_score >= 0.72 else "medium",
                    evidence_needed=[
                        f"Execute ordered path: {' -> '.join(item.function for item in ordered)}",
                        "Capture pre/post balances for attacker, protocol, and victim",
                        "Evaluate invariant delta for the dominant subsystem",
                    ],
                    required_actors=actors,
                    required_assumptions=[
                        "Target functions are externally reachable",
                        "State probes are readable on pre and post execution",
                    ],
                    expected_attack_sequence=attack_sequence,
                    expected_state_transition=(
                        f"baseline_{dominant_subsystem} -> adversarial_sequence -> "
                        f"invariant_drift_{dominant_subsystem}"
                    ),
                    required_capital=required_capital,
                    flashloan_principal=max(0, required_capital * 2 if any("borrow" in item.function.lower() or "loan" in item.function.lower() for item in ordered) else 0),
                    flashloan_fee=max(0, int(required_capital * 0.0009)),
                    predicted_attacker_profit=predicted_profit,
                    predicted_protocol_loss=predicted_profit,
                    predicted_victim_loss=max(1, int(predicted_profit * 0.7)),
                    economic_consequence=(
                        "Quantum-selected path can create economic divergence between expected accounting "
                        "and observed post-state balances."
                    ),
                )
            )
            if len(hypotheses) >= self.max_hypotheses:
                break
        return hypotheses

    def _extract_function_candidates(self, repository_model: RepositoryModel) -> list[_FunctionCandidate]:
        candidates: list[_FunctionCandidate] = []
        source_root = repository_model.root / "src"
        files = repository_model.contract_files
        for file_path in files:
            rel = str(file_path.relative_to(repository_model.root))
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            contract_names = re.findall(r"\bcontract\s+([A-Za-z_][A-Za-z0-9_]*)", text)
            contract = contract_names[0] if contract_names else Path(file_path).stem
            matches = re.findall(
                r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*([^;{]*)",
                text,
                flags=re.MULTILINE,
            )
            for fn_name, raw_params, suffix in matches:
                visibility = suffix.lower()
                if "internal" in visibility or "private" in visibility:
                    continue
                if " view" in visibility or " pure" in visibility:
                    continue
                params = [part.strip().split(" ")[0] for part in raw_params.split(",") if part.strip()]
                signature = f"{fn_name}({','.join(params)})" if params else f"{fn_name}()"
                exploit_role = self._classify_function_role(fn_name)
                subsystem_hint = self._infer_subsystem_hint(contract=contract, fn_name=fn_name, rel_path=rel)
                risk_weight = self._risk_weight(fn_name=fn_name, contract=contract, path=rel, role=exploit_role)
                candidates.append(
                    _FunctionCandidate(
                        contract=contract,
                        function=fn_name,
                        signature=signature,
                        file=rel,
                        subsystem_hint=subsystem_hint,
                        risk_weight=risk_weight,
                        exploit_role=exploit_role,
                    )
                )
        # Keep hypotheses grounded in core source rather than dependency libraries.
        if source_root.exists():
            candidates = [item for item in candidates if item.file.startswith("src/")]
        return candidates

    def _quantum_rank_bitstrings(self, candidates: list[_FunctionCandidate]) -> list[str]:
        qubits = len(candidates)
        weights = [item.risk_weight for item in candidates]
        if qml is None:
            return self._fallback_rank_bitstrings(weights)

        dev = qml.device("default.qubit", wires=qubits)

        @qml.qnode(dev)
        def circuit() -> list[float]:
            for wire in range(qubits):
                qml.Hadamard(wires=wire)
            for wire in range(qubits):
                phase = min(1.8, max(0.1, weights[wire] * 1.6))
                qml.RZ(phase, wires=wire)
            for wire in range(qubits - 1):
                qml.CNOT(wires=[wire, wire + 1])
            qml.CNOT(wires=[qubits - 1, 0])
            for wire in range(qubits):
                mixer = 0.55 + (weights[wire] * 0.25)
                qml.RX(mixer, wires=wire)
            return qml.probs(wires=range(qubits))

        probs = list(circuit())
        ranked = sorted(enumerate(probs), key=lambda item: item[1], reverse=True)
        bitstrings: list[str] = []
        for idx, _ in ranked:
            bits = format(idx, f"0{qubits}b")
            active = bits.count("1")
            if 2 <= active <= min(5, qubits):
                bitstrings.append(bits)
            if len(bitstrings) >= self.max_hypotheses * 3:
                break
        return bitstrings or self._fallback_rank_bitstrings(weights)

    def _fallback_rank_bitstrings(self, weights: list[float]) -> list[str]:
        qubits = len(weights)
        scored: list[tuple[str, float]] = []
        for idx in range(1, 2 ** qubits):
            bits = format(idx, f"0{qubits}b")
            active = bits.count("1")
            if active < 2 or active > min(5, qubits):
                continue
            score = 0.0
            for pos, bit in enumerate(bits):
                if bit == "1":
                    score += weights[pos]
            overlap_penalty = 0.03 * max(0, active - 3)
            scored.append((bits, score - overlap_penalty))
        scored.sort(key=lambda item: item[1], reverse=True)
        return [bits for bits, _ in scored[: self.max_hypotheses * 3]]

    @staticmethod
    def _order_attack_path(path: list[_FunctionCandidate]) -> list[_FunctionCandidate]:
        stage_order = {
            "setup": 0,
            "manipulate": 1,
            "extract": 2,
            "escape": 3,
        }
        return sorted(path, key=lambda item: (stage_order.get(item.exploit_role, 4), -item.risk_weight))

    @staticmethod
    def _derive_actors(path: list[_FunctionCandidate]) -> list[str]:
        actors = {"attacker", "protocol"}
        names = " ".join(item.function.lower() for item in path)
        if "flash" in names or "borrow" in names or "loan" in names:
            actors.add("lender")
        if "oracle" in names or "price" in names:
            actors.add("oracle")
        if "liquidat" in names:
            actors.add("liquidator")
        if "claim" in names or "redeem" in names:
            actors.add("victim")
        return sorted(actors)

    @staticmethod
    def _classify_function_role(function_name: str) -> str:
        lowered = function_name.lower()
        if any(token in lowered for token in ("init", "set", "configure", "approve", "grant", "permit")):
            return "setup"
        if any(token in lowered for token in ("swap", "deposit", "mint", "borrow", "loan", "flash", "liquidat", "transfer")):
            return "manipulate"
        if any(token in lowered for token in ("withdraw", "redeem", "claim", "collect", "harvest")):
            return "extract"
        if any(token in lowered for token in ("repay", "settle", "burn", "close")):
            return "escape"
        return "manipulate"

    @staticmethod
    def _infer_subsystem_hint(*, contract: str, fn_name: str, rel_path: str) -> str:
        text = f"{contract} {fn_name} {rel_path}".lower()
        if any(token in text for token in ("oracle", "price", "twap")):
            return "oracle"
        if any(token in text for token in ("swap", "pool", "pair", "liquidity")):
            return "swap"
        if any(token in text for token in ("vault", "collateral", "borrow", "lend")):
            return "lending"
        if any(token in text for token in ("fee", "reward", "claim", "harvest")):
            return "fees"
        if any(token in text for token in ("bridge", "relay", "cross")):
            return "bridge"
        if any(token in text for token in ("govern", "admin", "owner", "policy")):
            return "authority"
        return "generic"

    @staticmethod
    def _risk_weight(*, fn_name: str, contract: str, path: str, role: str) -> float:
        text = f"{fn_name} {contract} {path}".lower()
        weight = 0.4
        if role == "manipulate":
            weight += 0.22
        elif role == "extract":
            weight += 0.18
        elif role == "setup":
            weight += 0.08
        if any(token in text for token in ("flash", "borrow", "loan")):
            weight += 0.2
        if any(token in text for token in ("swap", "price", "oracle", "mint", "redeem", "withdraw")):
            weight += 0.13
        if any(token in text for token in ("pause", "owner", "govern", "admin", "upgrade")):
            weight += 0.11
        if "test" in path.lower():
            weight -= 0.25
        return round(max(0.15, min(0.98, weight)), 3)

    @staticmethod
    def _next_hypothesis_id(*, pattern_id: str, index: int, existing: set[str]) -> str:
        base = f"H-Q{pattern_id.upper()[:3]}-{index + 1:03d}"
        if base not in existing:
            return base
        offset = 2
        while True:
            candidate = f"H-Q{pattern_id.upper()[:3]}-{index + offset:03d}"
            if candidate not in existing:
                return candidate
            offset += 1

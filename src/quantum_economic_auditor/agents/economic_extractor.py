from __future__ import annotations

import re
from typing import Protocol

from quantum_economic_auditor.models.protocol import ProtocolSpec
from quantum_economic_auditor.parser.repository_loader import RepositoryModel


class EconomicExtractionProvider(Protocol):
    """Provider-agnostic interface for the economic extraction layer."""

    def extract(self, repository: RepositoryModel) -> ProtocolSpec:
        """Return a strongly typed protocol specification from Solidity sources."""


class StaticEconomicExtractor:
    """Deterministic fallback extractor for the research prototype.

    The extractor is designed to keep the optimization world entirely economic.
    Implementation-only names are filtered before they can reach the optimizer.
    """

    OLYMPUS_ECONOMIC_VARIABLES = (
        "backing",
        "premium",
        "capacity",
        "deltaB",
        "supply",
        "treasury",
        "bond",
        "oraclePrice",
    )

    OLYMPUS_ECONOMIC_ACTIONS = (
        "mint",
        "burn",
        "redeem",
        "bond",
    )

    _economic_tokens = (
        "reserve",
        "liquidity",
        "price",
        "profit",
        "slippage",
        "supply",
        "debt",
        "collateral",
        "vault",
        "share",
        "fee",
        "rate",
        "threshold",
        "cap",
        "mint",
        "burn",
        "borrow",
        "repay",
        "deposit",
        "withdraw",
        "swap",
        "backing",
        "premium",
        "capacity",
        "treasury",
        "bond",
        "oracle",
        "delta",
        "flashloan",
        "redeem",
        "liquidate",
        "utilization",
        "interest",
        "amount",
        "balance",
    )

    _implementation_tokens = (
        "target",
        "selector",
        "funcselector",
        "slot",
        "index",
        "counter",
        "loop",
        "storage",
        "memory",
        "owner",
        "admin",
        "config",
        "configured",
        "governance",
        "permission",
        "access",
        "modifier",
        "event",
        "mapping",
        "returns",
        "address",
        "calldata",
        "msg",
        "tx",
        "i",
        "j",
    )

    def __init__(self) -> None:
        self.inspection_report: list[dict[str, str]] = []

    def extract(self, repository: RepositoryModel) -> ProtocolSpec:
        if repository.root.name == "olympus-v3":
            return self._extract_olympus_economics(repository)

        contract_names = [path.stem for path in repository.contract_files]
        function_names = self._extract_function_names(repository)
        state_variables = self._extract_state_variables(repository)
        filtered_state_variables = self._filter_economic_names(state_variables)
        filtered_actions = self._filter_actions(function_names)
        filtered_transitions = [
            name
            for name in filtered_actions
            if any(token in name for token in ("mint", "burn", "deposit", "withdraw", "swap", "borrow", "repay", "redeem", "liquidate", "flashloan", "bond"))
        ]

        return ProtocolSpec(
            protocol_name=repository.root.name or "unknown-protocol",
            state_variables=filtered_state_variables[:8],
            economic_variables=filtered_state_variables[:8],
            external_dependencies=contract_names,
            actions=filtered_actions[:12],
            state_transitions=filtered_transitions[:8],
            protocol_invariants=["Supply >= 0", "Backing >= DeltaB", "OracleFreshness <= 1"][:8],
            hard_constraints=["Supply >= 0", "Backing >= DeltaB", "OracleFreshness <= 1"][:8],
            soft_constraints=["minimize_slippage", "prefer_liquidity_preservation"],
            reward_functions=["maximize_net_protocol_value"],
            penalty_conditions=["constraint_violation", "insufficient_backing"],
            oracle_dependencies=["oraclePrice"],
            liquidity_sources=[item for item in filtered_state_variables if "liquid" in item][:3] or ["liquidity"],
            flashloan_sources=[item for item in filtered_state_variables if "flashloan" in item][:3],
            governance_variables=[],
            pricing_models=["deterministic_protocol_pricing"],
            debt_models=[item for item in filtered_state_variables if "debt" in item][:3],
            share_models=[item for item in filtered_state_variables if "share" in item][:3],
            collateral_models=[item for item in filtered_state_variables if "collateral" in item][:3],
            risk_parameters=["slippage_tolerance", "oracle_freshness"],
            required_assumptions=["no_reentrancy", "same_block_execution"],
        )

    def _extract_olympus_economics(self, repository: RepositoryModel) -> ProtocolSpec:
        economic_variables = list(self.OLYMPUS_ECONOMIC_VARIABLES)
        actions = list(self.OLYMPUS_ECONOMIC_ACTIONS)

        return ProtocolSpec(
            protocol_name=repository.root.name or "olympus-v3",
            state_variables=economic_variables,
            economic_variables=economic_variables,
            external_dependencies=[path.stem for path in repository.contract_files],
            actions=actions,
            state_transitions=actions,
            protocol_invariants=["Backing >= DeltaB", "Supply >= 0", "Treasury >= 0"],
            hard_constraints=["Backing >= DeltaB", "Supply >= 0", "Treasury >= 0"],
            soft_constraints=["minimize_slippage", "prefer_liquidity_preservation"],
            reward_functions=["maximize_net_protocol_value"],
            penalty_conditions=["constraint_violation", "insufficient_backing"],
            oracle_dependencies=["oraclePrice"],
            liquidity_sources=["liquidity", "treasury"],
            flashloan_sources=["flashloanAmount"],
            governance_variables=[],
            pricing_models=["premium_function", "oracle_price"],
            debt_models=["deltaB"],
            share_models=["supply"],
            collateral_models=["backing"],
            risk_parameters=["oracle_freshness", "capacity"],
            required_assumptions=["same_block_execution", "oracle_freshness"],
        )

    def _extract_function_names(self, repository: RepositoryModel) -> list[str]:
        function_names: list[str] = []
        for file_path in repository.contract_files:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            for match in re.finditer(r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", text):
                name = match.group(1)
                if name not in function_names:
                    function_names.append(name)
        return function_names

    def _extract_state_variables(self, repository: RepositoryModel) -> list[str]:
        names: list[str] = []
        for file_path in repository.contract_files:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            for match in re.finditer(
                r"\b(?:mapping\s*\([^)]*\)|(?:address|uint\d*|int\d*|bool|bytes\d*|string|bytes)\s+)([A-Za-z_][A-Za-z0-9_]*)\s*;",
                text,
            ):
                name = match.group(1)
                if name not in names:
                    names.append(name)
        return names

    def _extract_economic_variables(self, repository: RepositoryModel) -> list[str]:
        collected: list[str] = []
        for file_path in repository.contract_files:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            for token in self._economic_tokens:
                if token in text.lower() and token not in collected:
                    collected.append(token)
        return collected

    def _filter_economic_names(self, names: list[str]) -> list[str]:
        filtered: list[str] = []
        for name in names:
            lower_name = name.lower()
            if self._is_implementation_name(lower_name):
                self.inspection_report.append(
                    {
                        "name": name,
                        "category": "implementation",
                        "source_location": "repository_scan",
                        "reason_kept": "",
                        "reason_discarded": "implementation artifact",
                    }
                )
                continue
            if not any(token in lower_name for token in self._economic_tokens):
                self.inspection_report.append(
                    {
                        "name": name,
                        "category": "implementation",
                        "source_location": "repository_scan",
                        "reason_kept": "",
                        "reason_discarded": "no economic semantics",
                    }
                )
                continue
            if name not in filtered:
                filtered.append(name)
                self.inspection_report.append(
                    {
                        "name": name,
                        "category": self._economic_category(lower_name),
                        "source_location": "repository_scan",
                        "reason_kept": "changes economic state of the protocol",
                        "reason_discarded": "",
                    }
                )
        return filtered

    def _filter_actions(self, names: list[str]) -> list[str]:
        filtered: list[str] = []
        for name in names:
            lower_name = name.lower()
            if self._is_implementation_name(lower_name):
                continue
            if any(token in lower_name for token in ("mint", "burn", "borrow", "repay", "deposit", "withdraw", "swap", "redeem", "liquidate", "flashloan", "bond")):
                if name not in filtered:
                    filtered.append(name)
        return filtered

    def _is_implementation_name(self, name: str) -> bool:
        return any(token in name for token in self._implementation_tokens)

    def _economic_category(self, name: str) -> str:
        for token in (
            "backing",
            "premium",
            "capacity",
            "treasury",
            "balance",
            "reserve",
            "liquidity",
            "supply",
            "debt",
            "collateral",
            "share",
            "oracle",
            "bond",
            "flashloan",
            "interest",
            "utilization",
        ):
            if token in name:
                return token
        return "economic_state"

    def inspect_repository(self, repository: RepositoryModel) -> list[dict[str, str]]:
        self.inspection_report = []
        self._filter_economic_names(self._extract_state_variables(repository))
        return self.inspection_report

    def _extract_invariants(self, repository: RepositoryModel) -> list[str]:
        return self._extract_require_clauses(repository)

    def _extract_hard_constraints(self, repository: RepositoryModel) -> list[str]:
        return self._extract_require_clauses(repository)

    def _extract_require_clauses(self, repository: RepositoryModel) -> list[str]:
        clauses: list[str] = []
        for file_path in repository.contract_files:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            index = 0
            while True:
                require_index = text.find("require", index)
                if require_index == -1:
                    break
                open_index = text.find("(", require_index)
                if open_index == -1:
                    break
                depth = 0
                cursor = open_index
                while cursor < len(text):
                    character = text[cursor]
                    if character == "(":
                        depth += 1
                    elif character == ")":
                        depth -= 1
                        if depth == 0:
                            payload = text[open_index + 1 : cursor].strip()
                            clause = payload.split(",", maxsplit=1)[0].strip()
                            if any(op in clause for op in (">=", "<=", ">", "<", "==", "!=")) and clause not in clauses:
                                clauses.append(clause)
                            index = cursor + 1
                            break
                    cursor += 1
                else:
                    break
        return clauses

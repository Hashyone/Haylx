from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from quantum_economic_auditor.models.eir import EconomicIntermediateRepresentation
from quantum_economic_auditor.models.graph import EdgeKind, KnowledgeGraph, KnowledgeGraphEdge, KnowledgeGraphNode, NodeKind
from quantum_economic_auditor.openclaw.agents.repository_context import RepositoryContext
from quantum_economic_auditor.parser.repository_loader import load_repository


@dataclass(slots=True)
class PatternEvidence:
    source: str
    detail: str
    weight: float


@dataclass(slots=True)
class ProtocolPatternDefinition:
    pattern_id: str
    label: str
    indicators: list[str]
    expected_subsystems: list[str]
    canonical_math: list[str]


@dataclass(slots=True)
class ProtocolPatternResult:
    pattern_id: str
    label: str
    confidence: float
    evidence: list[PatternEvidence] = field(default_factory=list)


@dataclass(slots=True)
class ExpectedProtocolModel:
    pattern_id: str
    pattern_label: str
    expected_subsystems: list[str]
    canonical_math: list[str]


@dataclass(slots=True)
class ExpectationGap:
    expected_subsystem: str
    status: str
    matched_observed_subsystem: str | None = None


@dataclass(slots=True)
class ExpectationComparison:
    expected: list[str]
    observed: list[str]
    missing_expected: list[str]
    unexpected_observed: list[str]
    match_ratio: float
    gaps: list[ExpectationGap] = field(default_factory=list)


PATTERN_REGISTRY: list[ProtocolPatternDefinition] = [
    ProtocolPatternDefinition(
        pattern_id="amm",
        label="AMM",
        indicators=["swap", "pool", "liquidity", "lp", "fee", "constant product", "clmm", "market maker"],
        expected_subsystems=[
            "Swap Mathematics",
            "Pool Accounting",
            "Liquidity Accounting",
            "Fee Distribution",
            "LP Economics",
            "Authority Model",
            "Oracle Dependencies",
        ],
        canonical_math=[
            "x * y = k",
            "reserve_out <= reserve_available",
            "fee_accrual(t+1) = fee_accrual(t) + trade_fees",
        ],
    ),
    ProtocolPatternDefinition(
        pattern_id="lending",
        label="Lending Protocol",
        indicators=["borrow", "repay", "interest", "liquidation", "collateral", "health factor", "reserve"],
        expected_subsystems=[
            "Collateral Accounting",
            "Borrow Accounting",
            "Interest Model",
            "Liquidation Engine",
            "Reserve Accounting",
            "Oracle Dependencies",
            "Permission System",
        ],
        canonical_math=[
            "collateral >= debt",
            "interest(t+1) = interest(t) + rate * utilization",
            "health_factor = collateral_value / debt_value",
        ],
    ),
    ProtocolPatternDefinition(
        pattern_id="reserve_currency",
        label="Reserve Currency Protocol",
        indicators=["treasury", "bond", "staking", "reserve", "emission", "governance", "backing"],
        expected_subsystems=[
            "Reserve Management System",
            "Treasury Accounting",
            "Supply Engine",
            "Emission System",
            "Bond Economics",
            "Staking Economics",
            "Governance",
        ],
        canonical_math=[
            "assets >= liabilities",
            "supply(t+1) = supply(t) + mint - burn",
            "backing_ratio = reserves / circulating_supply",
        ],
    ),
    ProtocolPatternDefinition(
        pattern_id="cdp_stablecoin",
        label="CDP Stablecoin",
        indicators=["vault", "cdp", "stability fee", "stablecoin", "peg", "dai", "lusd", "trove"],
        expected_subsystems=[
            "Collateral Vault",
            "Debt Accounting",
            "Stability Fee Model",
            "Liquidation Engine",
            "Price Oracle",
            "Peg Stability Module",
            "Permission System",
        ],
        canonical_math=[
            "collateral_value / debt >= liquidation_ratio",
            "stability_fee(t+1) = stability_fee(t) * (1 + rate)^dt",
            "supply_stablecoin = sum(debt_per_vault)",
        ],
    ),
    ProtocolPatternDefinition(
        pattern_id="bridge",
        label="Cross-Chain Bridge",
        indicators=["bridge", "cross-chain", "relay", "lock", "unlock", "merkle", "message passing", "layerzero", "wormhole"],
        expected_subsystems=[
            "Lock / Burn Accounting",
            "Mint / Unlock Accounting",
            "Message Relay",
            "Validator / Guardian Model",
            "Fee Distribution",
            "Replay Protection",
            "Emergency Controls",
        ],
        canonical_math=[
            "locked_source = minted_destination",
            "message_nonce(t+1) = message_nonce(t) + 1",
            "fee_out <= fee_collected",
        ],
    ),
    ProtocolPatternDefinition(
        pattern_id="liquid_staking",
        label="Liquid Staking Protocol",
        indicators=["stake", "unstake", "validator", "epoch", "slash", "reward", "liquid staking", "lsd", "steth"],
        expected_subsystems=[
            "Staking Accounting",
            "Reward Distribution",
            "Slashing Model",
            "Validator Registry",
            "Withdrawal Queue",
            "Share / Token Economics",
            "Oracle Dependencies",
        ],
        canonical_math=[
            "shares(t+1) = shares(t) + deposit / exchange_rate",
            "exchange_rate = total_staked / total_shares",
            "reward(t+1) = reward(t) + epoch_yield",
        ],
    ),
    ProtocolPatternDefinition(
        pattern_id="yield_aggregator",
        label="Yield Aggregator",
        indicators=["yield", "harvest", "strategy", "auto-compound", "earn", "apy", "apr", "yearn", "beefy"],
        expected_subsystems=[
            "Vault Accounting",
            "Strategy Engine",
            "Harvest Model",
            "Fee Distribution",
            "Share Economics",
            "Permission System",
            "Oracle Dependencies",
        ],
        canonical_math=[
            "shares(t+1) = shares(t) + deposit / pricePerShare",
            "pricePerShare = totalAssets / totalShares",
            "harvest_yield = strategy_return - fees",
        ],
    ),
    ProtocolPatternDefinition(
        pattern_id="perpetual",
        label="Perpetual Exchange",
        indicators=["perp", "perpetual", "funding rate", "long", "short", "leverage", "mark price", "index price"],
        expected_subsystems=[
            "Position Accounting",
            "Funding Rate Model",
            "Mark Price Oracle",
            "Margin / Collateral Accounting",
            "Liquidation Engine",
            "Fee Distribution",
            "Risk Parameters",
        ],
        canonical_math=[
            "funding_rate = (mark_price - index_price) / index_price",
            "pnl = position_size * (exit_price - entry_price)",
            "margin_ratio = collateral / notional_exposure",
        ],
    ),
    ProtocolPatternDefinition(
        pattern_id="governance",
        label="Governance Protocol",
        indicators=["vote", "proposal", "quorum", "timelock", "delegate", "snapshot", "token weight"],
        expected_subsystems=[
            "Proposal Lifecycle",
            "Vote Accounting",
            "Quorum Engine",
            "Timelock Control",
            "Delegation Model",
            "Permission System",
        ],
        canonical_math=[
            "vote_weight = token_balance + delegated_weight",
            "quorum_reached = total_votes >= quorum_threshold",
            "execution_time >= proposal_time + timelock_delay",
        ],
    ),
]


# ── Pattern-native subsystem specification lookup ─────────────────────────────

@dataclass(slots=True)
class PatternSubsystemSpec:
    """Protocol-native semantic data for a named subsystem within a protocol pattern."""
    guarantee: str
    architectural_responsibility: str
    business_objective: str
    state_equations: list[str]
    conservation_equations: list[str]
    balance_equations: list[str]
    invariant_id: str
    invariant_statement: str
    invariant_math: str
    invariant_interpretation: str
    state_machine_states: list[str]
    entry_functions: list[str]
    key_state_variables: list[str]
    threat_model: list[str]
    trust_assumptions: list[str]


PATTERN_SUBSYSTEM_SPECS: dict[str, PatternSubsystemSpec] = {
    "Swap Mathematics": PatternSubsystemSpec(
        guarantee="Swap outputs are bounded by pool reserve invariant under every execution path.",
        architectural_responsibility="swap pricing and reserve invariant maintenance",
        business_objective="ensure fair and manipulation-resistant price execution",
        state_equations=["reserve_x(t+1) = reserve_x(t) + amount_in", "reserve_y(t+1) = reserve_y(t) - amount_out"],
        conservation_equations=["reserve_x * reserve_y >= k"],
        balance_equations=["amount_out <= reserve_y"],
        invariant_id="SWAP-001",
        invariant_statement="Constant product invariant must hold after every swap.",
        invariant_math="(reserve_x + amount_in * (1 - fee)) * (reserve_y - amount_out) >= reserve_x * reserve_y",
        invariant_interpretation="Swap must not reduce the product of reserves below k.",
        state_machine_states=["idle", "swap_in_progress", "settled"],
        entry_functions=["swap", "swap_exact_input", "swap_exact_output"],
        key_state_variables=["reserve_x", "reserve_y", "fee_rate"],
        threat_model=["reserve drain via sandwich attack", "precision loss on output calculation", "k manipulation via flash loan"],
        trust_assumptions=["fee_rate is immutable", "reserve values are non-negative"],
    ),
    "Liquidity Accounting": PatternSubsystemSpec(
        guarantee="LP shares accurately represent proportional pool ownership at all times.",
        architectural_responsibility="liquidity deposit, withdrawal, and share issuance",
        business_objective="ensure LP positions are always redeemable at fair value",
        state_equations=["lp_shares(t+1) = lp_shares(t) + mint_amount", "reserve(t+1) = reserve(t) + deposit"],
        conservation_equations=["lp_shares / total_supply = deposit / total_reserves"],
        balance_equations=["total_reserves >= sum(lp_redeemable)"],
        invariant_id="LIQ-001",
        invariant_statement="LP share value must remain proportional to pool reserves.",
        invariant_math="share_value = (reserve_x + reserve_y) / total_lp_supply",
        invariant_interpretation="An LP holder withdrawing all shares must receive proportional reserves.",
        state_machine_states=["empty", "funded", "active", "withdrawing"],
        entry_functions=["add_liquidity", "remove_liquidity", "mint_lp", "burn_lp"],
        key_state_variables=["lp_total_supply", "reserve_x", "reserve_y"],
        threat_model=["first deposit inflation attack", "liquidity removal during low liquidity", "share dilution"],
        trust_assumptions=["no reentrancy in liquidity functions", "reserve values are accurate"],
    ),
    "Pool Accounting": PatternSubsystemSpec(
        guarantee="Pool reserves remain non-negative and conserved across deposit and withdrawal paths.",
        architectural_responsibility="pool-level reserve tracking and settlement",
        business_objective="maintain accurate pool state for correct swap pricing",
        state_equations=["pool_reserve(t+1) = pool_reserve(t) + inflow - outflow"],
        conservation_equations=["pool_reserve >= 0"],
        balance_equations=["inflow - outflow <= pool_reserve"],
        invariant_id="POOL-001",
        invariant_statement="Pool reserve balance must remain non-negative after every operation.",
        invariant_math="pool_reserve(t+1) >= 0",
        invariant_interpretation="No operation should cause pool reserves to go negative.",
        state_machine_states=["uninitialized", "active", "paused"],
        entry_functions=["deposit", "withdraw", "sync", "skim"],
        key_state_variables=["reserve0", "reserve1", "total_supply"],
        threat_model=["reserve imbalance", "skim/sync manipulation", "balance drift"],
        trust_assumptions=["sync is called before price-sensitive operations"],
    ),
    "Fee Distribution": PatternSubsystemSpec(
        guarantee="Protocol and LP fees are correctly apportioned and claimable without double-counting.",
        architectural_responsibility="fee accrual, split, and disbursement",
        business_objective="ensure fee revenue is distributed fairly without leakage",
        state_equations=["protocol_fee(t+1) = protocol_fee(t) + swap_fee * protocol_fee_ratio"],
        conservation_equations=["total_fee = protocol_fee + lp_fee"],
        balance_equations=["claimable_fee <= accrued_fee"],
        invariant_id="FEE-001",
        invariant_statement="Total distributed fees must equal total collected fees.",
        invariant_math="protocol_fee + lp_fee = swap_amount * fee_rate",
        invariant_interpretation="Fee split must be exhaustive with no fee leakage.",
        state_machine_states=["accruing", "claimable", "claimed"],
        entry_functions=["collect_fee", "collect_protocol_fee", "claim_rewards"],
        key_state_variables=["fee_growth_global", "protocol_fee_pending", "fee_rate"],
        threat_model=["fee extraction before distribution", "rounding error accumulation", "unauthorized fee claim"],
        trust_assumptions=["fee_rate cannot be changed mid-epoch"],
    ),
    "LP Economics": PatternSubsystemSpec(
        guarantee="LP token economics remain incentive-compatible and free from systemic dilution.",
        architectural_responsibility="LP incentive alignment and reward accrual",
        business_objective="ensure LPs are adequately compensated for liquidity provision",
        state_equations=["lp_reward(t+1) = lp_reward(t) + fee_earned_per_share"],
        conservation_equations=["sum(lp_rewards) <= total_fee_revenue"],
        balance_equations=["individual_lp_reward >= 0"],
        invariant_id="LP-001",
        invariant_statement="LP reward accrual must not exceed total protocol fee collection.",
        invariant_math="sum(lp_rewards) <= fee_collected",
        invariant_interpretation="LPs cannot collectively claim more than the pool has earned.",
        state_machine_states=["inactive", "earning", "claiming"],
        entry_functions=["stake_lp", "unstake_lp", "claim_fee"],
        key_state_variables=["lp_balance", "fee_per_share", "last_claimed_at"],
        threat_model=["fee griefing", "flash deposit to claim fees", "reward dilution"],
        trust_assumptions=["reward checkpoint is updated before balance changes"],
    ),
    "Authority Model": PatternSubsystemSpec(
        guarantee="Only authorized roles can execute privileged operations over pool state and upgrades.",
        architectural_responsibility="access control and privileged operation boundaries",
        business_objective="prevent unauthorized state mutation or configuration changes",
        state_equations=["authorized_role(t+1) = authorized_role(t)"],
        conservation_equations=["authority remains bounded to assigned roles"],
        balance_equations=["privilege_count >= 0"],
        invariant_id="AUTH-001",
        invariant_statement="Privileged operations must be gated by role membership.",
        invariant_math="exec_privileged => has_role(caller, ADMIN_ROLE)",
        invariant_interpretation="No unpermissioned actor can change protocol configuration.",
        state_machine_states=["uninitialized", "authorized", "paused", "revoked"],
        entry_functions=["set_fee_rate", "pause", "upgrade", "set_protocol_fee_recipient"],
        key_state_variables=["owner", "admin_role", "paused"],
        threat_model=["unauthorized admin access", "role escalation", "upgrade attack"],
        trust_assumptions=["role assignment is restricted to governance or deployer"],
    ),
    "Oracle Dependencies": PatternSubsystemSpec(
        guarantee="Price and data feeds consumed by the protocol are bounded, fresh, and manipulation-resistant.",
        architectural_responsibility="external price feed integration and staleness detection",
        business_objective="ensure price-sensitive operations use reliable and timely data",
        state_equations=["price(t+1) = oracle_feed(t+1)"],
        conservation_equations=["price > 0", "price_age <= max_staleness"],
        balance_equations=["oracle_price within accepted bounds"],
        invariant_id="ORC-001",
        invariant_statement="Oracle price must be fresh and within acceptable deviation bounds.",
        invariant_math="abs(oracle_price - twap_price) / twap_price <= max_deviation",
        invariant_interpretation="A stale or manipulated oracle price should not be consumed.",
        state_machine_states=["fresh", "stale", "invalid"],
        entry_functions=["get_price", "update_price", "verify_price"],
        key_state_variables=["last_price", "last_updated_at", "max_staleness"],
        threat_model=["oracle manipulation", "stale price consumption", "flash loan price attack"],
        trust_assumptions=["oracle updates at minimum every epoch", "TWAP provides manipulation resistance"],
    ),
    "Reserve Accounting": PatternSubsystemSpec(
        guarantee="Protocol reserves remain solvent and sufficient to cover outstanding claims.",
        architectural_responsibility="reserve balance tracking across deposits and withdrawals",
        business_objective="preserve protocol solvency and withdrawal safety",
        state_equations=["reserve(t+1) = reserve(t) + deposits - withdrawals"],
        conservation_equations=["reserve >= outstanding_claims"],
        balance_equations=["reserve >= 0"],
        invariant_id="RSV-001",
        invariant_statement="Reserve balance must cover all outstanding withdrawal claims.",
        invariant_math="reserve >= sum(pending_withdrawals)",
        invariant_interpretation="The protocol must always be able to fulfil pending withdrawals.",
        state_machine_states=["funded", "stressed", "insolvent"],
        entry_functions=["deposit", "withdraw", "rebalance"],
        key_state_variables=["reserve_balance", "pending_withdrawals", "total_assets"],
        threat_model=["reserve drain", "insolvency attack", "withdrawal run"],
        trust_assumptions=["no unbounded withdrawal queue growth"],
    ),
    "Collateral Accounting": PatternSubsystemSpec(
        guarantee="Collateral positions remain overcollateralized across all market conditions.",
        architectural_responsibility="collateral deposit, valuation, and liquidation readiness",
        business_objective="maintain system-wide collateralization ratio above minimum threshold",
        state_equations=["collateral(t+1) = collateral(t) + deposit - withdrawal"],
        conservation_equations=["collateral_value >= debt * liquidation_ratio"],
        balance_equations=["collateral >= 0"],
        invariant_id="COL-001",
        invariant_statement="Collateral value must exceed debt by the minimum ratio at all times.",
        invariant_math="collateral_value / debt >= liquidation_ratio",
        invariant_interpretation="Undercollateralized positions must be liquidated before going negative.",
        state_machine_states=["healthy", "at_risk", "undercollateralized", "liquidated"],
        entry_functions=["deposit_collateral", "withdraw_collateral", "liquidate"],
        key_state_variables=["collateral_balance", "debt_balance", "liquidation_ratio"],
        threat_model=["rapid price drop below liquidation threshold", "liquidation bot failure", "collateral freeze"],
        trust_assumptions=["oracle price is fresh", "liquidation bots are active"],
    ),
    "Supply Engine": PatternSubsystemSpec(
        guarantee="Token supply accurately reflects authorized mint and burn operations.",
        architectural_responsibility="token issuance, redemption, and supply lifecycle",
        business_objective="ensure supply integrity and authorized-only issuance",
        state_equations=["supply(t+1) = supply(t) + mint - burn"],
        conservation_equations=["supply >= 0"],
        balance_equations=["circulating = total_supply - locked"],
        invariant_id="SUP-001",
        invariant_statement="Total supply must equal sum of all authorized mints minus authorized burns.",
        invariant_math="total_supply = initial_supply + sum(mints) - sum(burns)",
        invariant_interpretation="No unauthorized supply inflation or deflation should be possible.",
        state_machine_states=["normal", "minting", "burning", "paused"],
        entry_functions=["mint", "burn", "rebase"],
        key_state_variables=["total_supply", "circulating_supply", "locked_supply"],
        threat_model=["unauthorized mint", "supply inflation via rebase", "burn bypass"],
        trust_assumptions=["mint authority is restricted to governance or bond contracts"],
    ),
    "Lock / Burn Accounting": PatternSubsystemSpec(
        guarantee="Every lock or burn on the source chain is matched by exactly one mint on the destination.",
        architectural_responsibility="source-side asset custody and proof generation",
        business_objective="ensure cross-chain supply conservation",
        state_equations=["locked(t+1) = locked(t) + lock_amount - unlock_amount"],
        conservation_equations=["locked_source == minted_destination"],
        balance_equations=["locked >= 0"],
        invariant_id="LOCK-001",
        invariant_statement="Total locked on source chain must equal total minted on destination.",
        invariant_math="sum(locked) = sum(minted_destination)",
        invariant_interpretation="Cross-chain supply is only conserved if lock equals mint exactly.",
        state_machine_states=["unlocked", "locked", "pending_relay", "finalized"],
        entry_functions=["lock", "burn", "initiate_bridge"],
        key_state_variables=["locked_amount", "nonce", "pending_messages"],
        threat_model=["double-spend via replay", "lock without corresponding mint", "invalid proof"],
        trust_assumptions=["relayer delivers messages exactly once", "proofs are verified on-chain"],
    ),
}


class ProtocolPatternRecognitionEngine:
    """Classify protocol family from repository evidence and context."""

    def classify(
        self,
        *,
        repository_path: Path | str,
        repository_context: RepositoryContext,
        eir: EconomicIntermediateRepresentation,
    ) -> ProtocolPatternResult:
        root = Path(repository_path)
        repo = load_repository(str(root))
        scope_text = (repository_context.scope_summary or "").lower()
        issues_text = " ".join(repository_context.known_issues).lower()
        eir_text = " ".join(
            [
                *(item.name for item in eir.variables),
                *(item.name for item in eir.actions),
                *(item.expression for item in eir.invariants),
            ]
        ).lower()
        file_text = " ".join(path.name.lower() for path in repo.contract_files)

        best_pattern = PATTERN_REGISTRY[0]
        best_score = -1.0
        best_evidence: list[PatternEvidence] = []

        for pattern in PATTERN_REGISTRY:
            score = 0.0
            evidence: list[PatternEvidence] = []
            for indicator in pattern.indicators:
                token = indicator.lower()
                if token in scope_text:
                    score += 0.22
                    evidence.append(PatternEvidence(source="scope", detail=f"indicator '{indicator}' found in scope", weight=0.22))
                if token in eir_text:
                    score += 0.18
                    evidence.append(PatternEvidence(source="eir", detail=f"indicator '{indicator}' found in EIR", weight=0.18))
                if token in file_text:
                    score += 0.15
                    evidence.append(PatternEvidence(source="repository", detail=f"indicator '{indicator}' found in file names", weight=0.15))
                if token in issues_text:
                    score += 0.08
                    evidence.append(PatternEvidence(source="known_issues", detail=f"indicator '{indicator}' found in risk context", weight=0.08))

            if len(repo.contract_files) > 0:
                score += min(0.2, len(repo.contract_files) / 200.0)
                evidence.append(
                    PatternEvidence(
                        source="repository",
                        detail=f"contract corpus size contributed ({len(repo.contract_files)} source files)",
                        weight=min(0.2, len(repo.contract_files) / 200.0),
                    )
                )

            if score > best_score:
                best_score = score
                best_pattern = pattern
                best_evidence = evidence

        confidence = max(0.35, min(0.98, round(best_score, 3)))
        return ProtocolPatternResult(
            pattern_id=best_pattern.pattern_id,
            label=best_pattern.label,
            confidence=confidence,
            evidence=best_evidence[:20],
        )


class ExpectedProtocolModelRegistry:
    """Return expected subsystem and canonical math models by protocol class."""

    def get(self, pattern_id: str) -> ExpectedProtocolModel:
        for pattern in PATTERN_REGISTRY:
            if pattern.pattern_id == pattern_id:
                return ExpectedProtocolModel(
                    pattern_id=pattern.pattern_id,
                    pattern_label=pattern.label,
                    expected_subsystems=pattern.expected_subsystems,
                    canonical_math=pattern.canonical_math,
                )
        fallback = PATTERN_REGISTRY[0]
        return ExpectedProtocolModel(
            pattern_id=fallback.pattern_id,
            pattern_label=fallback.label,
            expected_subsystems=fallback.expected_subsystems,
            canonical_math=fallback.canonical_math,
        )


class ExpectationGraphEngine:
    """Represent expected protocol structure as a first-class graph."""

    def build(self, expected_model: ExpectedProtocolModel) -> KnowledgeGraph:
        nodes: list[KnowledgeGraphNode] = [
            KnowledgeGraphNode(
                id=f"expected:{expected_model.pattern_id}",
                kind=NodeKind.PROTOCOL_RELATIONSHIP,
                label=expected_model.pattern_label,
                metadata={"type": "expected_protocol_class"},
            )
        ]
        edges: list[KnowledgeGraphEdge] = []
        previous_node_id = f"expected:{expected_model.pattern_id}"

        for index, subsystem in enumerate(expected_model.expected_subsystems):
            subsystem_node_id = f"expected:subsystem:{expected_model.pattern_id}:{index}"
            nodes.append(
                KnowledgeGraphNode(
                    id=subsystem_node_id,
                    kind=NodeKind.SUBSYSTEM,
                    label=subsystem,
                    metadata={"type": "expected_subsystem"},
                )
            )
            edges.append(
                KnowledgeGraphEdge(
                    source=previous_node_id,
                    target=subsystem_node_id,
                    kind=EdgeKind.DEPENDS_ON,
                    metadata={"reason": "expected architectural dependency chain"},
                )
            )
            previous_node_id = subsystem_node_id

        for index, equation in enumerate(expected_model.canonical_math):
            equation_node_id = f"expected:math:{expected_model.pattern_id}:{index}"
            nodes.append(
                KnowledgeGraphNode(
                    id=equation_node_id,
                    kind=NodeKind.MATHEMATICAL_SPECIFICATION,
                    label=equation,
                    metadata={"type": "canonical_equation"},
                )
            )
            edges.append(
                KnowledgeGraphEdge(
                    source=f"expected:{expected_model.pattern_id}",
                    target=equation_node_id,
                    kind=EdgeKind.SUPPORTS,
                    metadata={"reason": "canonical mathematics for protocol class"},
                )
            )

        return KnowledgeGraph(nodes=nodes, edges=edges)


class ExpectedObservedComparator:
    """Compare expected protocol structure against observed subsystem reconstructions."""

    def compare(self, *, expected_model: ExpectedProtocolModel, observed_subsystems: list[str]) -> ExpectationComparison:
        normalized_observed = {self._normalize(name): name for name in observed_subsystems}
        missing_expected: list[str] = []
        gaps: list[ExpectationGap] = []

        for expected in expected_model.expected_subsystems:
            match = self._best_match(expected, normalized_observed)
            if match is None:
                missing_expected.append(expected)
                gaps.append(ExpectationGap(expected_subsystem=expected, status="missing"))
            else:
                gaps.append(ExpectationGap(expected_subsystem=expected, status="observed", matched_observed_subsystem=match))

        expected_norm = {self._normalize(item) for item in expected_model.expected_subsystems}
        unexpected_observed = [
            observed
            for normalized, observed in normalized_observed.items()
            if normalized not in expected_norm and not any(normalized in self._normalize(item) for item in expected_model.expected_subsystems)
        ]

        observed_count = len(expected_model.expected_subsystems) - len(missing_expected)
        ratio = round(observed_count / max(1, len(expected_model.expected_subsystems)), 3)

        return ExpectationComparison(
            expected=expected_model.expected_subsystems,
            observed=observed_subsystems,
            missing_expected=missing_expected,
            unexpected_observed=unexpected_observed,
            match_ratio=ratio,
            gaps=gaps,
        )

    def _best_match(self, expected: str, normalized_observed: dict[str, str]) -> str | None:
        expected_tokens = set(self._normalize(expected).split())
        best: tuple[float, str] | None = None
        for normalized, original in normalized_observed.items():
            observed_tokens = set(normalized.split())
            overlap = len(expected_tokens & observed_tokens)
            if overlap <= 0:
                continue
            score = overlap / max(1, len(expected_tokens))
            if best is None or score > best[0]:
                best = (score, original)
        return best[1] if best and best[0] >= 0.34 else None

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join("".join(ch if ch.isalnum() else " " for ch in value.lower()).split())


# ── Hypothesis Generator ──────────────────────────────────────────────────────

@dataclass(slots=True)
class ResearchHypothesis:
    hypothesis_id: str
    title: str
    rationale: str
    missing_subsystem: str
    pattern_label: str
    expected_guarantees: list[str]
    canonical_math: list[str]
    threat_vectors: list[str]
    priority: str
    evidence_needed: list[str]
    required_actors: list[str] = field(default_factory=list)
    required_assumptions: list[str] = field(default_factory=list)
    expected_attack_sequence: list[str] = field(default_factory=list)
    expected_state_transition: str = ""
    required_capital: int = 0
    flashloan_principal: int = 0
    flashloan_fee: int = 0
    predicted_attacker_profit: int = 0
    predicted_protocol_loss: int = 0
    predicted_victim_loss: int = 0
    economic_consequence: str = ""


class HypothesisGenerator:
    """Turn missing expected subsystems into structured research hypotheses."""

    _ACTOR_TEMPLATES: dict[str, list[str]] = {
        "swap": ["attacker", "victim", "lender"],
        "liquidity": ["attacker", "lp", "lender"],
        "fee": ["attacker", "lp", "protocol"],
        "oracle": ["attacker", "oracle", "protocol"],
        "collateral": ["attacker", "borrower", "liquidator"],
        "borrow": ["attacker", "borrower", "lender"],
        "authority": ["attacker", "admin", "governance"],
        "permission": ["attacker", "admin", "governance"],
        "reserve": ["attacker", "treasury", "protocol"],
        "bridge": ["attacker", "relayer", "bridge"],
        "supply": ["attacker", "holder", "protocol"],
    }

    def generate(
        self,
        *,
        comparison: ExpectationComparison,
        pattern_label: str,
        pattern_id: str,
    ) -> list[ResearchHypothesis]:
        hypotheses: list[ResearchHypothesis] = []
        for index, missing in enumerate(comparison.missing_expected):
            spec = PATTERN_SUBSYSTEM_SPECS.get(missing)
            hypothesis_id = f"H-{pattern_id.upper()[:4]}-{index + 1:03d}"
            if spec:
                required_actors = self._derive_required_actors(spec=spec, missing_subsystem=missing)
                required_assumptions = self._derive_required_assumptions(spec=spec)
                expected_attack_sequence = self._derive_attack_sequence(spec=spec)
                (
                    required_capital,
                    flashloan_principal,
                    flashloan_fee,
                    predicted_attacker_profit,
                    predicted_protocol_loss,
                    predicted_victim_loss,
                ) = self._derive_numeric_targets(spec=spec, index=index)
                hypotheses.append(
                    ResearchHypothesis(
                        hypothesis_id=hypothesis_id,
                        title=f"Missing: {missing} ({pattern_label})",
                        rationale=(
                            f"A {pattern_label} should contain a {missing} subsystem. "
                            f"Its absence may reflect an imported, inherited, or non-standard implementation "
                            f"rather than an immediate vulnerability. "
                            f"The analysis should verify whether the '{spec.guarantee}' guarantee is delivered through "
                            f"another module or file tree before treating the gap as exploitable."
                        ),
                        missing_subsystem=missing,
                        pattern_label=pattern_label,
                        expected_guarantees=[spec.guarantee],
                        canonical_math=[spec.invariant_math] + spec.conservation_equations,
                        threat_vectors=spec.threat_model,
                        priority="high" if index < 2 else "medium",
                        evidence_needed=[
                            f"Locate functions matching: {', '.join(spec.entry_functions[:3])}",
                            f"Verify state variables: {', '.join(spec.key_state_variables[:3])}",
                            f"Confirm invariant: {spec.invariant_math}",
                        ],
                        required_actors=required_actors,
                        required_assumptions=required_assumptions,
                        expected_attack_sequence=expected_attack_sequence,
                        expected_state_transition=self._derive_state_transition(spec=spec),
                        required_capital=required_capital,
                        flashloan_principal=flashloan_principal,
                        flashloan_fee=flashloan_fee,
                        predicted_attacker_profit=predicted_attacker_profit,
                        predicted_protocol_loss=predicted_protocol_loss,
                        predicted_victim_loss=predicted_victim_loss,
                        economic_consequence=self._derive_economic_consequence(spec=spec),
                    )
                )
            else:
                hypotheses.append(
                    ResearchHypothesis(
                        hypothesis_id=hypothesis_id,
                        title=f"Missing: {missing} ({pattern_label})",
                        rationale=(
                            f"A {pattern_label} is expected to contain a {missing} subsystem "
                            f"but none was observed in the current reconstruction. "
                            f"This may indicate an imported or non-standard implementation rather than a direct vulnerability."
                        ),
                        missing_subsystem=missing,
                        pattern_label=pattern_label,
                        expected_guarantees=[f"{missing} correctness guarantee"],
                        canonical_math=[],
                        threat_vectors=["unverified subsystem behavior"],
                        priority="medium",
                        evidence_needed=[
                            f"Search repository for {missing.lower().replace(' ', '_')} related code",
                            "Review protocol documentation for this subsystem",
                        ],
                        required_actors=["attacker", "protocol"],
                        required_assumptions=[f"{missing} implementation is reachable in the current repository state"],
                        expected_attack_sequence=[
                            "reconstruct the missing subsystem",
                            "trace reachable entrypoints",
                            "execute the state-changing path",
                            "measure the post-state delta",
                        ],
                        expected_state_transition="pre-state -> reconstructed path -> post-state",
                        required_capital=1,
                        flashloan_principal=0,
                        flashloan_fee=0,
                        predicted_attacker_profit=0,
                        predicted_protocol_loss=0,
                        predicted_victim_loss=0,
                        economic_consequence=f"Unknown until {missing} implementation is deeply reconstructed",
                    )
                )
        return hypotheses

    @classmethod
    def _derive_required_actors(cls, *, spec: PatternSubsystemSpec, missing_subsystem: str) -> list[str]:
        lower = " ".join([missing_subsystem, spec.guarantee, " ".join(spec.threat_model)]).lower()
        actors: list[str] = []
        for keyword, candidates in cls._ACTOR_TEMPLATES.items():
            if keyword in lower:
                actors.extend(candidates)
        actors.extend(["attacker", "protocol"])
        dedup: list[str] = []
        seen: set[str] = set()
        for actor in actors:
            if actor in seen:
                continue
            seen.add(actor)
            dedup.append(actor)
        return dedup[:4]

    @staticmethod
    def _derive_required_assumptions(*, spec: PatternSubsystemSpec) -> list[str]:
        assumptions = [
            f"{spec.guarantee}",
            f"State reconstruction covers: {', '.join(spec.key_state_variables[:3])}",
        ]
        threat_text = " ".join(spec.threat_model).lower()
        if "flash" in threat_text:
            assumptions.append("Flashloan-capable capital is available for the reachability path")
        if "oracle" in threat_text:
            assumptions.append("Oracle price can be influenced within the modeled environment")
        if "permission" in threat_text or "role" in threat_text:
            assumptions.append("Caller permissions must be explicitly modeled and enforced")
        return assumptions[:4]

    @staticmethod
    def _derive_attack_sequence(*, spec: PatternSubsystemSpec) -> list[str]:
        lower = " ".join([spec.guarantee, spec.invariant_math, " ".join(spec.threat_model)]).lower()
        if any(keyword in lower for keyword in ("flash", "swap", "amm", "liquidity")):
            return [
                "acquire capital",
                "enter the target market or pool",
                "move accounting state or price",
                "trigger the vulnerable function",
                "restore borrow obligations",
                "observe residual profit and pool/state delta",
            ]
        if any(keyword in lower for keyword in ("oracle", "price")):
            return [
                "acquire capital",
                "manipulate oracle source or reference market",
                "invoke price-sensitive protocol action",
                "capture mispricing-based value",
                "restore reference price",
                "measure post-state loss and attacker profit",
            ]
        if any(keyword in lower for keyword in ("collateral", "borrow", "liquidation")):
            return [
                "seed collateral state",
                "borrow against inflated value or weak checks",
                "allow accounting drift or oracle shift",
                "avoid or delay liquidation",
                "withdraw value exceeding entitlement",
                "measure debt, collateral, and net profit deltas",
            ]
        if any(keyword in lower for keyword in ("authority", "permission", "governance")):
            return [
                "identify privileged entrypoint",
                "obtain or bypass role checks",
                "execute unauthorized configuration change",
                "observe protocol control transfer",
                "measure resulting permissions delta",
            ]
        return [
            "reconstruct the required pre-state",
            "exercise the primary entry function",
            "observe post-state delta",
            "quantify resulting economic change",
        ]

    @staticmethod
    def _derive_state_transition(*, spec: PatternSubsystemSpec) -> str:
        return f"pre-state satisfying {spec.invariant_math} -> post-state after executing the modeled attack sequence"

    @staticmethod
    def _derive_economic_consequence(*, spec: PatternSubsystemSpec) -> str:
        lower = " ".join([spec.guarantee, spec.invariant_math, " ".join(spec.threat_model)]).lower()
        if any(keyword in lower for keyword in ("flash", "swap", "amm", "liquidity")):
            return "Pool reserve loss or LP value extraction after borrow/price manipulation"
        if any(keyword in lower for keyword in ("oracle", "price")):
            return "Mispriced execution leads to attacker profit and victim overpayment"
        if any(keyword in lower for keyword in ("collateral", "borrow", "liquidation")):
            return "Bad debt or undercollateralization creates direct solvency loss"
        if any(keyword in lower for keyword in ("authority", "permission", "governance")):
            return "Unauthorized configuration changes create protocol loss or control transfer"
        return f"Quantifiable loss or value extraction from the {spec.guarantee} failure"

    @staticmethod
    def _derive_numeric_targets(*, spec: PatternSubsystemSpec, index: int) -> tuple[int, int, int, int, int, int]:
        lower = " ".join([spec.guarantee, spec.invariant_math, " ".join(spec.threat_model)]).lower()
        has_flashloan_path = "flash" in lower
        base = 50_000 * (index + 1)
        if any(keyword in lower for keyword in ("authority", "permission", "governance", "admin", "role", "upgrade")):
            required_capital = 0
            flashloan_principal = 0
        elif any(keyword in lower for keyword in ("swap", "amm", "liquidity")):
            required_capital = base * 4
            flashloan_principal = required_capital if has_flashloan_path else 0
        elif any(keyword in lower for keyword in ("oracle", "price")):
            required_capital = base * 3
            flashloan_principal = required_capital if has_flashloan_path else 0
        elif any(keyword in lower for keyword in ("collateral", "borrow", "liquidation")):
            required_capital = base * 2
            flashloan_principal = required_capital if has_flashloan_path else 0
        else:
            required_capital = base
            flashloan_principal = required_capital if has_flashloan_path else 0

        flashloan_fee = max(1, flashloan_principal // 1000) if flashloan_principal else 0
        if required_capital == 0 and flashloan_principal == 0:
            predicted_attacker_profit = 0
        else:
            predicted_attacker_profit = max(1, flashloan_principal // 20) if flashloan_principal else max(1, required_capital // 10)
        predicted_protocol_loss = predicted_attacker_profit + flashloan_fee
        predicted_victim_loss = predicted_attacker_profit
        return (
            required_capital,
            flashloan_principal,
            flashloan_fee,
            predicted_attacker_profit,
            predicted_protocol_loss,
            predicted_victim_loss,
        )
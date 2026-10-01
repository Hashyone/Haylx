"""
Halyx v12 Investigator Engine

Transforms static guarantee reconstruction into dynamic adversarial investigation.
The engine generates structured lines of inquiry, causal chains, counterfactual
challenges, and adversarial hypotheses from subsystem dossiers.

Philosophy:
  Protocol reconstruction explains reality.
  Protocol investigation attempts to falsify reality.
  Truth should survive investigation, not merely be reconstructed.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ── Causal Chain ──────────────────────────────────────────────────────────────

@dataclass(slots=True)
class CausalLink:
    layer: str
    description: str
    evidence_strength: float
    is_weak: bool = False


@dataclass(slots=True)
class CausalChain:
    guarantee: str
    subsystem: str
    links: list[CausalLink] = field(default_factory=list)
    weakest_link: str | None = None
    chain_confidence: float = 0.0
    is_research_priority: bool = False


# ── Counterfactual ────────────────────────────────────────────────────────────

@dataclass(slots=True)
class CounterfactualChallenge:
    guarantee: str
    subsystem: str
    challenge: str
    broken_invariants: list[str] = field(default_factory=list)
    broken_accounting: list[str] = field(default_factory=list)
    broken_subsystems: list[str] = field(default_factory=list)
    economic_consequences: list[str] = field(default_factory=list)
    severity: str = "medium"


# ── Adversarial Hypothesis ────────────────────────────────────────────────────

@dataclass(slots=True)
class AdversarialHypothesis:
    hypothesis_id: str
    subsystem: str
    guarantee: str
    attack_vector: str
    attack_description: str
    preconditions: list[str] = field(default_factory=list)
    execution_steps: list[str] = field(default_factory=list)
    violated_invariant: str = ""
    economic_impact: str = ""
    severity: str = "medium"
    requires_privilege: bool = False


# ── Investigation Task ────────────────────────────────────────────────────────

@dataclass(slots=True)
class InvestigationTask:
    task_id: str
    subsystem: str
    guarantee: str
    question: str
    question_type: str
    priority: str
    related_invariant: str = ""
    related_assumption: str = ""


# ── Investigation Report ──────────────────────────────────────────────────────

@dataclass(slots=True)
class InvestigationReport:
    subsystem: str
    guarantee: str
    causal_chain: CausalChain
    counterfactuals: list[CounterfactualChallenge]
    adversarial_hypotheses: list[AdversarialHypothesis]
    investigation_tasks: list[InvestigationTask]
    implicit_assumptions: list[str]
    cross_subsystem_dependencies: list[str]
    temporal_risks: list[str]
    overall_risk_signal: str


# ── Causal Chain Builder ──────────────────────────────────────────────────────

class CausalChainBuilder:
    """Build a causal chain from a guarantee down to user-level consequences."""

    def build(
        self,
        *,
        subsystem_name: str,
        guarantee: str,
        invariant_math: str,
        state_equations: list[str],
        trust_assumptions: list[str],
        threat_model: list[str],
    ) -> CausalChain:
        links: list[CausalLink] = [
            CausalLink(layer="Guarantee", description=guarantee, evidence_strength=0.9),
            CausalLink(
                layer="Supporting assumptions",
                description="; ".join(trust_assumptions[:3]) if trust_assumptions else "implicit: all inputs are valid",
                evidence_strength=0.65 if not trust_assumptions else 0.8,
                is_weak=not trust_assumptions,
            ),
            CausalLink(
                layer="Implementation",
                description=f"State transitions enforce: {'; '.join(state_equations[:2]) if state_equations else 'unknown'}",
                evidence_strength=0.7,
            ),
            CausalLink(
                layer="Mathematical consequence",
                description=f"Formal invariant: {invariant_math}",
                evidence_strength=0.85,
            ),
            CausalLink(
                layer="Economic consequence",
                description=self._economic_consequence(subsystem_name, guarantee),
                evidence_strength=0.7,
            ),
            CausalLink(
                layer="Security consequence",
                description=threat_model[0] if threat_model else "unspecified threat",
                evidence_strength=0.75,
            ),
            CausalLink(
                layer="User consequence",
                description=self._user_consequence(subsystem_name),
                evidence_strength=0.7,
            ),
        ]

        weakest = min(links, key=lambda link: link.evidence_strength)
        weakest.is_weak = True
        chain_confidence = sum(link.evidence_strength for link in links) / len(links)
        is_priority = weakest.evidence_strength < 0.7

        return CausalChain(
            guarantee=guarantee,
            subsystem=subsystem_name,
            links=links,
            weakest_link=weakest.layer,
            chain_confidence=round(chain_confidence, 3),
            is_research_priority=is_priority,
        )

    @staticmethod
    def _economic_consequence(subsystem_name: str, guarantee: str) -> str:
        subsystem_lower = subsystem_name.lower()
        if "swap" in subsystem_lower or "amm" in subsystem_lower:
            return "Incorrect output amounts can be extracted by arbitrageurs, draining pool reserves"
        if "liquidity" in subsystem_lower:
            return "LP positions could be worth less than the assets deposited, representing a loss for liquidity providers"
        if "fee" in subsystem_lower:
            return "Protocol revenue is silently misallocated, either extracted by attackers or lost"
        if "collateral" in subsystem_lower or "vault" in subsystem_lower:
            return "Under-collateralized positions persist, creating bad debt that the protocol cannot recover"
        if "oracle" in subsystem_lower:
            return "Price-sensitive operations execute at incorrect valuations, enabling profitable manipulation"
        if "supply" in subsystem_lower or "emission" in subsystem_lower:
            return "Unauthorized supply inflation dilutes existing holders and breaks backing assumptions"
        if "authority" in subsystem_lower or "permission" in subsystem_lower:
            return "Privileged operations can be executed by unintended actors, bypassing protocol safety controls"
        if "reserve" in subsystem_lower or "treasury" in subsystem_lower:
            return "Reserve insolvency propagates: withdrawals fail, protocol loses credibility, users face losses"
        if "bridge" in subsystem_lower or "lock" in subsystem_lower:
            return "Cross-chain supply becomes inconsistent; bridged assets may become unbacked"
        return f"Failure of the {subsystem_name} guarantee exposes users to quantifiable financial loss"

    @staticmethod
    def _user_consequence(subsystem_name: str) -> str:
        subsystem_lower = subsystem_name.lower()
        if "swap" in subsystem_lower:
            return "Users receive fewer tokens than mathematically guaranteed by the pool state"
        if "liquidity" in subsystem_lower:
            return "LPs cannot redeem their share of pool assets at fair value"
        if "fee" in subsystem_lower:
            return "Fee income is silently stolen or lost rather than distributed to LPs and protocol"
        if "collateral" in subsystem_lower:
            return "Borrowers face unexpected liquidations; lenders face bad debt exposure"
        if "oracle" in subsystem_lower:
            return "Users transact at incorrect prices, losing value to manipulation or stale data"
        if "authority" in subsystem_lower or "permission" in subsystem_lower:
            return "Protocol configuration is changed without user consent or governance process"
        if "reserve" in subsystem_lower or "treasury" in subsystem_lower:
            return "Users cannot withdraw assets they are owed due to reserve insolvency"
        if "supply" in subsystem_lower:
            return "Token holders suffer dilution without consent"
        return "Users suffer financial loss or loss of access to protocol functionality"


# ── Counterfactual Engine ─────────────────────────────────────────────────────

class CounterfactualEngine:
    """Generate counterfactual challenges for each guarantee."""

    _GENERIC_BROKEN_SUBSYSTEMS: dict[str, list[str]] = {
        "Swap Mathematics": ["Liquidity Accounting", "Fee Distribution", "Pool Accounting"],
        "Liquidity Accounting": ["Swap Mathematics", "LP Economics", "Fee Distribution"],
        "Fee Distribution": ["LP Economics", "Swap Mathematics"],
        "LP Economics": ["Fee Distribution", "Liquidity Accounting"],
        "Authority Model": ["Swap Mathematics", "Fee Distribution", "Liquidity Accounting"],
        "Oracle Dependencies": ["Swap Mathematics", "Collateral Accounting", "Liquidation Engine"],
        "Collateral Accounting": ["Borrow Accounting", "Liquidation Engine", "Reserve Accounting"],
        "Reserve Accounting": ["Collateral Accounting", "Borrow Accounting"],
        "Supply Engine": ["Reserve Management System", "Treasury Accounting"],
        "Reserve Management System": ["Supply Engine", "Treasury Accounting"],
        "Lock / Burn Accounting": ["Mint / Unlock Accounting", "Fee Distribution"],
    }

    def challenge(
        self,
        *,
        subsystem_name: str,
        guarantee: str,
        invariant_math: str,
        key_state_variables: list[str],
        threat_model: list[str],
    ) -> list[CounterfactualChallenge]:
        challenges: list[CounterfactualChallenge] = []
        broken_subsystems = self._GENERIC_BROKEN_SUBSYSTEMS.get(subsystem_name, ["dependent subsystems"])

        challenges.append(CounterfactualChallenge(
            guarantee=guarantee,
            subsystem=subsystem_name,
            challenge=f"Suppose the guarantee '{guarantee}' is silently removed. What immediately breaks?",
            broken_invariants=[invariant_math],
            broken_accounting=[f"{var} accounting becomes unconstrained" for var in key_state_variables[:2]],
            broken_subsystems=broken_subsystems,
            economic_consequences=self._economic_consequences(subsystem_name),
            severity="high",
        ))

        challenges.append(CounterfactualChallenge(
            guarantee=guarantee,
            subsystem=subsystem_name,
            challenge=f"Suppose one of the trust assumptions supporting '{subsystem_name}' is violated. How does the guarantee degrade?",
            broken_invariants=[f"partial: {invariant_math}"],
            broken_accounting=[],
            broken_subsystems=broken_subsystems[:1],
            economic_consequences=[threat_model[0] if threat_model else "unspecified consequence"],
            severity="medium",
        ))

        challenges.append(CounterfactualChallenge(
            guarantee=guarantee,
            subsystem=subsystem_name,
            challenge=f"Suppose '{subsystem_name}' and one adjacent subsystem execute concurrently or out of order. What inconsistency arises?",
            broken_invariants=[],
            broken_accounting=[f"race condition on {var}" for var in key_state_variables[:1]],
            broken_subsystems=broken_subsystems[:2],
            economic_consequences=["state becomes inconsistent across subsystems"],
            severity="medium",
        ))

        return challenges

    @staticmethod
    def _economic_consequences(subsystem_name: str) -> list[str]:
        sn = subsystem_name.lower()
        if "swap" in sn:
            return ["attackers extract reserves via incorrect output calculation", "pool becomes economically unsustainable"]
        if "liquidity" in sn:
            return ["LP positions lose value faster than fees compensate", "capital flight from the pool"]
        if "fee" in sn:
            return ["revenue silently accrues to attacker rather than LPs", "LP incentive to provide liquidity disappears"]
        if "oracle" in sn:
            return ["flash loan price manipulation becomes profitable", "all price-sensitive operations mispriced"]
        if "collateral" in sn:
            return ["bad debt accumulates across positions", "solvency crisis propagates to reserve accounting"]
        if "authority" in sn or "permission" in sn:
            return ["protocol parameters changed without governance", "fee extraction or upgrade attack"]
        if "supply" in sn:
            return ["supply inflation outpaces backing", "token value collapses"]
        return ["economic value can be extracted from the protocol without providing equivalent value"]


# ── Adversarial Hypothesis Engine ─────────────────────────────────────────────

class AdversarialHypothesisEngine:
    """Generate attack hypotheses for each subsystem guarantee."""

    _ATTACK_PATTERNS: dict[str, list[dict[str, object]]] = {
        "Swap Mathematics": [
            {
                "vector": "flash loan sandwich",
                "description": "Borrow large amount, move pool price, victim swaps at bad price, repay loan keeping profit",
                "steps": ["flash borrow reserve_x", "swap to move price", "victim swap executes at manipulated price", "reverse swap", "repay loan"],
                "violated_invariant": "reserve_x * reserve_y >= k for fair user execution",
                "privilege": False,
                "severity": "critical",
            },
            {
                "vector": "precision loss exploitation",
                "description": "Exploit integer rounding in output calculation to extract extra tokens over many transactions",
                "steps": ["identify rounding direction in swap math", "execute repeated swaps at rounding boundary", "accumulate dust extractions"],
                "violated_invariant": "amount_out <= reserve_y",
                "privilege": False,
                "severity": "low",
            },
        ],
        "Liquidity Accounting": [
            {
                "vector": "first deposit inflation attack",
                "description": "Attacker is first depositor, donates large amount directly, then forces share rounding to zero for subsequent depositors",
                "steps": ["deposit minimal amount as first LP", "transfer large token amount directly to pool", "victim deposit rounds to 0 shares", "attacker redeems inflated share value"],
                "violated_invariant": "lp_shares / total_supply = deposit / total_reserves",
                "privilege": False,
                "severity": "high",
            },
            {
                "vector": "reentrancy during liquidity removal",
                "description": "Trigger callback during remove_liquidity before state update, re-enter to remove same liquidity again",
                "steps": ["call remove_liquidity", "callback fires before state update", "re-enter remove_liquidity", "state updates twice but liquidity removed once"],
                "violated_invariant": "total_reserves >= sum(lp_redeemable)",
                "privilege": False,
                "severity": "critical",
            },
        ],
        "Fee Distribution": [
            {
                "vector": "flash deposit fee capture",
                "description": "Deposit large amount immediately before fee distribution snapshot, capture fees earned by others, withdraw",
                "steps": ["observe pending fee distribution", "flash borrow to deposit large amount", "trigger fee distribution", "capture disproportionate share of fees", "withdraw"],
                "violated_invariant": "sum(lp_rewards) <= fee_collected",
                "privilege": False,
                "severity": "high",
            },
        ],
        "Oracle Dependencies": [
            {
                "vector": "oracle manipulation via low liquidity",
                "description": "Manipulate oracle price by trading in low liquidity pool used as price source",
                "steps": ["identify oracle price source pool", "measure manipulation cost", "execute large trade to move price", "trigger price-sensitive operation at manipulated price", "reverse trade"],
                "violated_invariant": "abs(oracle_price - twap_price) / twap_price <= max_deviation",
                "privilege": False,
                "severity": "critical",
            },
        ],
        "Collateral Accounting": [
            {
                "vector": "oracle price manipulation to avoid liquidation",
                "description": "Manipulate oracle to report inflated collateral value, borrow maximum, let oracle return to true price",
                "steps": ["manipulate oracle price upward", "deposit collateral at inflated price", "borrow maximum against inflated collateral", "oracle reverts to true price", "position is undercollateralized but not liquidated in time"],
                "violated_invariant": "collateral_value / debt >= liquidation_ratio",
                "privilege": False,
                "severity": "critical",
            },
        ],
        "Authority Model": [
            {
                "vector": "role escalation via misconfigured grant",
                "description": "A role that can grant other roles is itself incorrectly scoped, allowing an attacker to escalate to admin",
                "steps": ["identify role with grant capability", "check if role scope is too broad", "call role grant to assign admin role to attacker address"],
                "violated_invariant": "exec_privileged => has_role(caller, ADMIN_ROLE)",
                "privilege": True,
                "severity": "critical",
            },
        ],
        "Reserve Accounting": [
            {
                "vector": "reserve drain via accounting bypass",
                "description": "Trigger a code path that withdraws from reserves without updating the accounting balance",
                "steps": ["identify withdrawal path with missing accounting update", "call withdrawal function", "reserve balance decreases but accounting shows full amount", "repeat to drain"],
                "violated_invariant": "reserve >= outstanding_claims",
                "privilege": False,
                "severity": "critical",
            },
        ],
        "Supply Engine": [
            {
                "vector": "unauthorized mint via permission gap",
                "description": "Find a code path where mint authority check is incomplete or bypassable",
                "steps": ["enumerate all mint entrypoints", "test each for missing role checks", "call mint without authorization"],
                "violated_invariant": "total_supply = initial_supply + sum(mints) - sum(burns)",
                "privilege": False,
                "severity": "critical",
            },
        ],
        "Lock / Burn Accounting": [
            {
                "vector": "replay attack on bridge message",
                "description": "Replay a valid bridge message on same or different chain to mint without corresponding lock",
                "steps": ["capture valid bridge message", "relay same message again on destination chain", "second mint executes without second lock on source"],
                "violated_invariant": "sum(locked) = sum(minted_destination)",
                "privilege": False,
                "severity": "critical",
            },
        ],
    }

    def generate(
        self,
        *,
        subsystem_name: str,
        guarantee: str,
        hypothesis_prefix: str = "ADV",
    ) -> list[AdversarialHypothesis]:
        patterns = self._ATTACK_PATTERNS.get(subsystem_name, [])
        hypotheses: list[AdversarialHypothesis] = []

        for index, pattern in enumerate(patterns):
            hypotheses.append(AdversarialHypothesis(
                hypothesis_id=f"{hypothesis_prefix}-{subsystem_name.upper()[:4].replace(' ', '')}-{index + 1:03d}",
                subsystem=subsystem_name,
                guarantee=guarantee,
                attack_vector=str(pattern["vector"]),
                attack_description=str(pattern["description"]),
                preconditions=["attacker controls an EOA or contract"],
                execution_steps=list(pattern["steps"]),  # type: ignore[arg-type]
                violated_invariant=str(pattern["violated_invariant"]),
                economic_impact=f"Attacker can extract value by violating: {pattern['violated_invariant']}",
                severity=str(pattern["severity"]),
                requires_privilege=bool(pattern["privilege"]),
            ))

        if not hypotheses:
            hypotheses.append(AdversarialHypothesis(
                hypothesis_id=f"{hypothesis_prefix}-{subsystem_name.upper()[:4].replace(' ', '')}-001",
                subsystem=subsystem_name,
                guarantee=guarantee,
                attack_vector="unspecified",
                attack_description=f"No pre-catalogued attack pattern exists for {subsystem_name}. Requires manual investigation of the subsystem-specific implementation.",
                preconditions=["depends on implementation"],
                execution_steps=["review entry functions", "trace state variable mutations", "identify unchecked paths"],
                violated_invariant=f"{subsystem_name} primary invariant",
                economic_impact="Unknown until implementation is deeply reconstructed",
                severity="medium",
                requires_privilege=False,
            ))

        return hypotheses


# ── Investigation Task Generator ──────────────────────────────────────────────

class InvestigationTaskGenerator:
    """Generate structured investigation questions from a subsystem dossier."""

    def generate(
        self,
        *,
        subsystem_name: str,
        guarantee: str,
        trust_assumptions: list[str],
        key_state_variables: list[str],
        entry_functions: list[str],
        cross_subsystem_deps: list[str],
        invariant_math: str,
    ) -> list[InvestigationTask]:
        tasks: list[InvestigationTask] = []
        prefix = f"INV-{subsystem_name.replace(' ', '-').upper()[:6]}"

        tasks.append(InvestigationTask(
            task_id=f"{prefix}-001",
            subsystem=subsystem_name,
            guarantee=guarantee,
            question=f"Is the guarantee '{guarantee}' explicitly enforced by code, or is it only implied by design?",
            question_type="assumption_audit",
            priority="high",
            related_invariant=invariant_math,
        ))

        for i, assumption in enumerate(trust_assumptions[:3]):
            tasks.append(InvestigationTask(
                task_id=f"{prefix}-{i + 2:03d}",
                subsystem=subsystem_name,
                guarantee=guarantee,
                question=f"What happens if the assumption '{assumption}' is violated? Is there a defensive path?",
                question_type="counterfactual",
                priority="high",
                related_assumption=assumption,
                related_invariant=invariant_math,
            ))

        for i, fn in enumerate(entry_functions[:3]):
            tasks.append(InvestigationTask(
                task_id=f"{prefix}-{len(trust_assumptions[:3]) + i + 2:03d}",
                subsystem=subsystem_name,
                guarantee=guarantee,
                question=f"Does `{fn}` fully enforce the invariant '{invariant_math}' before returning? Are there partial-update paths?",
                question_type="implementation_audit",
                priority="medium",
                related_invariant=invariant_math,
            ))

        for dep in cross_subsystem_deps[:2]:
            tasks.append(InvestigationTask(
                task_id=f"{prefix}-X{cross_subsystem_deps.index(dep) + 1:03d}",
                subsystem=subsystem_name,
                guarantee=guarantee,
                question=f"Could a failure in '{dep}' invalidate the '{subsystem_name}' guarantee? Is there a circuit breaker?",
                question_type="cross_subsystem",
                priority="high",
            ))

        tasks.append(InvestigationTask(
            task_id=f"{prefix}-T001",
            subsystem=subsystem_name,
            guarantee=guarantee,
            question=f"Is the guarantee preserved across multi-step execution sequences involving {subsystem_name}? Consider: deposit → action → withdraw → claim.",
            question_type="temporal",
            priority="medium",
            related_invariant=invariant_math,
        ))

        return tasks


# ── Investigator Engine ───────────────────────────────────────────────────────

class InvestigatorEngine:
    """
    Transforms static guarantee dossiers into dynamic investigation reports.
    Runs after subsystem reconstruction and before Trinity reasoning.

    Output feeds directly into the truth layer and reasoning engines as
    structured adversarial context rather than passive reconstruction.
    """

    def __init__(self) -> None:
        self.causal_builder = CausalChainBuilder()
        self.counterfactual_engine = CounterfactualEngine()
        self.adversarial_engine = AdversarialHypothesisEngine()
        self.task_generator = InvestigationTaskGenerator()

    def investigate(
        self,
        *,
        subsystem_name: str,
        guarantee: str,
        invariant_math: str,
        state_equations: list[str],
        conservation_equations: list[str],
        trust_assumptions: list[str],
        threat_model: list[str],
        key_state_variables: list[str],
        entry_functions: list[str],
        cross_subsystem_deps: list[str],
    ) -> InvestigationReport:
        causal_chain = self.causal_builder.build(
            subsystem_name=subsystem_name,
            guarantee=guarantee,
            invariant_math=invariant_math,
            state_equations=state_equations,
            trust_assumptions=trust_assumptions,
            threat_model=threat_model,
        )
        counterfactuals = self.counterfactual_engine.challenge(
            subsystem_name=subsystem_name,
            guarantee=guarantee,
            invariant_math=invariant_math,
            key_state_variables=key_state_variables,
            threat_model=threat_model,
        )
        adversarial_hypotheses = self.adversarial_engine.generate(
            subsystem_name=subsystem_name,
            guarantee=guarantee,
        )
        tasks = self.task_generator.generate(
            subsystem_name=subsystem_name,
            guarantee=guarantee,
            trust_assumptions=trust_assumptions,
            key_state_variables=key_state_variables,
            entry_functions=entry_functions,
            cross_subsystem_deps=cross_subsystem_deps,
            invariant_math=invariant_math,
        )
        implicit_assumptions = [
            assumption
            for assumption in trust_assumptions
            if "explicitly" not in assumption.lower() and "enforced" not in assumption.lower()
        ] or ["no explicit enforcement confirmed — all assumptions implicit"]

        temporal_risks = [
            f"State variable '{var}' may be read before update in multi-step sequences" for var in key_state_variables[:2]
        ] + [f"Entry function '{fn}' may not be atomic across dependent subsystems" for fn in entry_functions[:1]]

        high_severity_adversarial = [h for h in adversarial_hypotheses if h.severity in {"critical", "high"}]
        overall_risk = (
            "critical" if causal_chain.is_research_priority and high_severity_adversarial
            else "high" if high_severity_adversarial
            else "medium" if counterfactuals
            else "low"
        )

        return InvestigationReport(
            subsystem=subsystem_name,
            guarantee=guarantee,
            causal_chain=causal_chain,
            counterfactuals=counterfactuals,
            adversarial_hypotheses=adversarial_hypotheses,
            investigation_tasks=tasks,
            implicit_assumptions=implicit_assumptions,
            cross_subsystem_dependencies=cross_subsystem_deps,
            temporal_risks=temporal_risks,
            overall_risk_signal=overall_risk,
        )

    def investigate_all(
        self,
        *,
        subsystem_dossiers: list[dict[str, object]],
    ) -> list[InvestigationReport]:
        from quantum_economic_auditor.semantic.protocol_pattern_engine import PATTERN_SUBSYSTEM_SPECS

        reports: list[InvestigationReport] = []
        for dossier in subsystem_dossiers:
            subsystem_name = str(dossier.get("subsystem_identity") or dossier.get("name") or "Unknown")
            guarantee = str(dossier.get("protocol_guarantee") or "")
            cross_deps = [dep.get("target", "") for dep in dossier.get("cross_subsystem_dependencies", [])]

            spec = PATTERN_SUBSYSTEM_SPECS.get(subsystem_name)
            if spec:
                invariant_math = spec.invariant_math
                state_equations = spec.state_equations
                conservation_equations = spec.conservation_equations
                trust_assumptions = spec.trust_assumptions
                threat_model = spec.threat_model
                key_state_variables = spec.key_state_variables
                entry_functions = spec.entry_functions
            else:
                observed_math = dossier.get("observed_mathematics") or []
                canonical_math = dossier.get("canonical_mathematics") or []
                invariant_math = observed_math[0] if observed_math else (canonical_math[0] if canonical_math else "unknown")
                state_equations = list(observed_math[:2]) if observed_math else []
                conservation_equations = list(canonical_math[:2]) if canonical_math else []
                trust_assumptions = []
                threat_model = []
                key_state_variables = []
                entry_functions = list(
                    (dossier.get("implementation_traces") or [{}])[0].get("functions", [])
                )

            reports.append(self.investigate(
                subsystem_name=subsystem_name,
                guarantee=guarantee if guarantee else f"{subsystem_name} correctness guarantee",
                invariant_math=invariant_math,
                state_equations=state_equations,
                conservation_equations=conservation_equations,
                trust_assumptions=trust_assumptions,
                threat_model=threat_model,
                key_state_variables=key_state_variables,
                entry_functions=entry_functions,
                cross_subsystem_deps=[str(d) for d in cross_deps if d],
            ))

        return reports


def serialize_investigation_reports(reports: list[InvestigationReport]) -> list[dict[str, object]]:
    """Serialize investigation reports to pipeline-compatible dicts."""
    result = []
    for report in reports:
        result.append({
            "subsystem": report.subsystem,
            "guarantee": report.guarantee,
            "overall_risk_signal": report.overall_risk_signal,
            "implicit_assumptions": report.implicit_assumptions,
            "temporal_risks": report.temporal_risks,
            "cross_subsystem_dependencies": report.cross_subsystem_dependencies,
            "causal_chain": {
                "chain_confidence": report.causal_chain.chain_confidence,
                "weakest_link": report.causal_chain.weakest_link,
                "is_research_priority": report.causal_chain.is_research_priority,
                "links": [
                    {
                        "layer": link.layer,
                        "description": link.description,
                        "evidence_strength": link.evidence_strength,
                        "is_weak": link.is_weak,
                    }
                    for link in report.causal_chain.links
                ],
            },
            "counterfactuals": [
                {
                    "challenge": cf.challenge,
                    "broken_invariants": cf.broken_invariants,
                    "broken_accounting": cf.broken_accounting,
                    "broken_subsystems": cf.broken_subsystems,
                    "economic_consequences": cf.economic_consequences,
                    "severity": cf.severity,
                }
                for cf in report.counterfactuals
            ],
            "adversarial_hypotheses": [
                {
                    "hypothesis_id": ah.hypothesis_id,
                    "attack_vector": ah.attack_vector,
                    "attack_description": ah.attack_description,
                    "execution_steps": ah.execution_steps,
                    "violated_invariant": ah.violated_invariant,
                    "economic_impact": ah.economic_impact,
                    "severity": ah.severity,
                    "requires_privilege": ah.requires_privilege,
                }
                for ah in report.adversarial_hypotheses
            ],
            "investigation_tasks": [
                {
                    "task_id": task.task_id,
                    "question": task.question,
                    "question_type": task.question_type,
                    "priority": task.priority,
                    "related_invariant": task.related_invariant,
                    "related_assumption": task.related_assumption,
                }
                for task in report.investigation_tasks
            ],
        })
    return result

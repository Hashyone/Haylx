from __future__ import annotations

from dataclasses import dataclass

from quantum_economic_auditor.models.objective import ObjectiveSpec


@dataclass
class Hamiltonian:
    reward_term: float
    constraint_penalty: float
    gas_penalty: float
    liquidity_penalty: float
    capital_penalty: float
    total_energy: float


def build_hamiltonian(
    objective_spec: ObjectiveSpec,
    profit_estimate: float,
    constraint_penalty: float,
    gas_estimate: float,
    liquidity_penalty: float,
    capital_required: float,
) -> Hamiltonian:
    """Generate a deterministic cost Hamiltonian for the quantum stage.

    All terms are computed from the same mathematical model used by the classical
    optimizer, ensuring a fair apples-to-apples comparison.
    """

    weights = objective_spec.weights
    reward_term = profit_estimate * weights.profit
    gas_penalty = gas_estimate * weights.gas
    liquidity_penalty = liquidity_penalty * weights.flashloan_size
    capital_penalty = capital_required * weights.capital_required
    constraint_penalty = constraint_penalty * weights.transaction_count

    total_energy = -(reward_term) + gas_penalty + liquidity_penalty + capital_penalty + constraint_penalty
    return Hamiltonian(
        reward_term=reward_term,
        constraint_penalty=constraint_penalty,
        gas_penalty=gas_penalty,
        liquidity_penalty=liquidity_penalty,
        capital_penalty=capital_penalty,
        total_energy=total_energy,
    )

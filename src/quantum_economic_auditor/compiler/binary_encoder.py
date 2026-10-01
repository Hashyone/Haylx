from __future__ import annotations

from math import ceil, log2

from quantum_economic_auditor.models.state import EncodedVariable


def gray_encode(bits: list[int]) -> list[int]:
    """Convert a binary bitstring into Gray code."""

    if not bits:
        return []
    gray = [bits[0]]
    for prev, curr in zip(bits, bits[1:]):
        gray.append(prev ^ curr)
    return gray


def encode_variable(
    name: str,
    value: float,
    lower_bound: float = 0.0,
    upper_bound: float = 1000.0,
    precision: float = 1.0,
    use_gray_code: bool = False,
) -> EncodedVariable:
    """Deterministically discretize a continuous variable into binary bits.

    The encoding stage is entirely deterministic and independent from the LLM.
    """

    if upper_bound <= lower_bound:
        raise ValueError("upper_bound must exceed lower_bound")
    if precision <= 0:
        raise ValueError("precision must be positive")

    step_count = int(round((upper_bound - lower_bound) / precision))
    if step_count < 1:
        step_count = 1

    step_index = int(round((value - lower_bound) / precision))
    step_index = min(max(step_index, 0), step_count)
    bit_width = max(1, ceil(log2(step_count + 1)))
    encoded_bits = [int((step_index >> shift) & 1) for shift in range(bit_width - 1, -1, -1)]
    gray_bits = gray_encode(encoded_bits) if use_gray_code else []
    return EncodedVariable(
        name=name,
        raw_value=value,
        encoded_bits=encoded_bits,
        gray_encoded_bits=gray_bits,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
    )

from __future__ import annotations

from quantum_economic_auditor.models.transition import ProtocolExecutionHistory


class ExplanationEngine:
    """Create human-readable reachability explanations for ranked candidates."""

    def explain(self, history: ProtocolExecutionHistory) -> str:
        parts: list[str] = [
            f"Initial state: backing={history.initial_state.backing}, supply={history.initial_state.supply}, treasury={history.initial_state.treasury}",
            f"Reachability status: {history.constraint_status}",
            f"Profit: {history.profit}",
        ]

        for index, step in enumerate(history.steps, start=1):
            parts.append(
                (
                    f"Step {index}: {step.action} amount={step.decision_variable}; "
                    f"reachable={step.reachable}; "
                    f"preconditions={','.join(step.satisfied_preconditions) or 'none'}; "
                    f"rejections={','.join(step.rejected_preconditions) or 'none'}"
                )
            )
            parts.append(
                (
                    f"State after step {index}: backing={step.state_after.backing}, "
                    f"supply={step.state_after.supply}, treasury={step.state_after.treasury}, "
                    f"capacity={step.state_after.capacity}, debt={step.state_after.debt}"
                )
            )

        parts.append(f"Final state: backing={history.final_state.backing}, supply={history.final_state.supply}, treasury={history.final_state.treasury}")
        parts.append(history.explanation)
        return "\n".join(parts)

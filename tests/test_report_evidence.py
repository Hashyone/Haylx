from __future__ import annotations

from pathlib import Path

from quantum_economic_auditor.report.report_generator import AuditReportGenerator


def test_report_includes_economic_evidence_package(tmp_path: Path) -> None:
    payload = {
        "repository_context": {"repository_path": "/tmp/olympus-contracts"},
        "falsification_execution": {
            "mode": "foundry_isolated",
            "generated_test_file": "/tmp/olympus-contracts/.halyx/falsification_harness/test/HalyxHypothesisEvidence.t.sol",
            "harness_dir": "/tmp/olympus-contracts/.halyx/falsification_harness",
            "fork_rpc_source": "environment",
            "return_code": 0,
            "passed": True,
            "stdout_tail": "[PASS] test_HalyxHypothesis_H_AMM_001()",
            "stderr_tail": "",
            "reason": None,
            "cases": [
                {
                    "hypothesis_id": "H-AMM-001",
                    "test_name": "test_HalyxHypothesis_H_AMM_001",
                    "status": "execution_proof_criteria_satisfied",
                    "rationale": "Behavioral exploit sequence completed.",
                    "should_fail": True,
                    "execution_sequence_id": "seq:H-AMM-001",
                    "execution_steps": [{"index": 1, "handler": "borrow", "caller": "attacker", "from_state": "pre", "to_state": "post"}],
                    "economic_consequence": "protocol loss",
                    "violated_invariants": ["INV-1"],
                    "target_contracts": ["Vault"],
                    "target_addresses": ["0x1111111111111111111111111111111111111111"],
                    "target_functions": ["borrow(uint256)"],
                    "target_invariants": ["INV-1"],
                    "invariant_assertion": "attackerNetProfit > 0",
                    "proof_marker": "HALYX_TEST_COMPLETED:H-AMM-001",
                    "proof_summary": "Replay sequence confirmed.",
                    "required_capital": 100,
                    "flashloan_principal": 1000,
                    "flashloan_fee": 3,
                    "predicted_attacker_profit": 50,
                    "predicted_protocol_loss": 53,
                    "predicted_victim_loss": 53,
                    "assumptions": ["Flashloan available"],
                    "actors": ["attacker", "lender"],
                }
            ],
        },
        "hypothesis_evidence_objects": [
            {
                "hypothesis_id": "H-AMM-001",
                "title": "Missing: Fee Distribution (AMM)",
                "subsystem": "Fee Distribution",
                "current_stage": "finding_confirmed",
                "stage_history": [],
                "reconstructed_protocol_state": {"initial_state": "pre", "resulting_state": "post"},
                "required_assumptions": ["Flashloan available"],
                "required_actors": ["attacker", "lender"],
                "required_permissions": ["operator"],
                "executable_sequence": [{"index": 1, "handler": "borrow", "caller": "attacker", "from_state": "pre", "to_state": "post", "preconditions": ["pre"], "postconditions": ["post"], "state_writes": ["reserve"], "state_reads": ["reserve"], "emitted_events": [], "trust_boundary": None, "permissions_required": [], "constraint_ids": [], "invariant_ids": ["INV-1"]}],
                "expected_invariant": "attackerNetProfit > 0",
                "observed_invariant_result": "execution_proof_criteria_satisfied",
                "accounting_delta": "protocol loss",
                "state_transition": "pre -> post",
                "execution_logs": ["step 1"],
                "foundry_test_reference": "test_HalyxHypothesis_H_AMM_001",
                "environment": "foundry_fork",
                "fork_block": None,
                "assumptions": ["Flashloan available"],
                "limitations": ["Flashloan mechanism was not reproduced; scenario remains an economic capital assumption."],
                "predicted_values": {"required_capital": 100, "flashloan_principal": 1000, "flashloan_fee": 3, "predicted_attacker_profit": 50, "predicted_protocol_loss": 53, "predicted_victim_loss": 53},
                "observed_values": {"execution_steps_exercised": 1},
                "invariant_delta": {"violated_invariant_count": 1},
                "economic_delta": {"predicted_attacker_profit": 50, "predicted_protocol_loss": 53, "predicted_victim_loss": 53},
                "verdict": "BEHAVIORALLY_CONFIRMED",
                "verdict_basis": "Behavioral evidence confirmed.",
                "final_confidence": 0.93,
            }
        ],
        "hypothesis_evidence_ledger": [
            {
                "hypothesis_id": "H-AMM-001",
                "title": "Missing: Fee Distribution (AMM)",
                "subsystem": "Fee Distribution",
                "status": "supported",
                "execution_case": {"proof_marker": "HALYX_TEST_COMPLETED:H-AMM-001"},
                "final_confidence": 0.93,
                "proof_attempts": [],
                "falsification_attempts": [],
                "confidence_trajectory": [],
                "verdict_basis": {},
            }
        ],
        "consensus": {"classification": "survives", "research_priority": 0.1},
        "planning": {"next_action": {"action": "test", "rationale": "", "expected_information_gain": 0.0, "uncertainty_reduction": 0.0}},
        "methodology": {"phases": []},
        "protocol_pattern": {},
        "expected_vs_observed": {},
        "tutor_research": [],
        "verification_reports": [],
        "investigation_reports": [],
        "research_hypotheses": [],
        "subsystems": [],
        "reasoning": {"classical_summary": "", "ml_summary": "", "quantum_summary": ""},
        "training": {},
        "execution_sequences": [],
        "rejected_execution_sequences": [],
        "execution_sequence_coverage": {"minimum_threshold": 0.35, "subsystems": []},
        "hypothesis_trace": [],
        "evidence_graph": {},
        "protocol_reconstruction": {},
        "protocol_semantics": {},
    }

    generator = AuditReportGenerator()
    output_path = generator.generate(payload, output_dir=tmp_path)
    content = output_path.read_text(encoding="utf-8")

    assert "Economic evidence package" in content
    assert "Flashloan principal" in content
    assert "Predicted attacker profit" in content
    assert "limitations" in content.lower()
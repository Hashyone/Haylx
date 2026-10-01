from __future__ import annotations

import quantum_economic_auditor.api.app as api_app


def test_poc_analysis_marks_target_validation_failures_inconclusive() -> None:
    stdout = (
        "[FAIL: H-AMM-001 could not be validated on fork state] test_HalyxHypothesis_H_AMM_001()\n"
        "[FAIL: H-AMM-002 could not be validated on fork state] test_HalyxHypothesis_H_AMM_002()\n"
    )
    analysis = api_app._analyze_poc_output(stdout=stdout, stderr="", return_code=1)

    assert analysis["implication"] == "inconclusive_target_validation"
    assert analysis["verdict"] == "INCONCLUSIVE"
    assert len(analysis["failed_tests"]) == 2
    assert len(analysis["target_validation_miss_tests"]) == 2


def test_poc_analysis_marks_compile_failures_inconclusive_toolchain() -> None:
    analysis = api_app._analyze_poc_output(
        stdout="Compiler run failed",
        stderr="Error: Compilation failed",
        return_code=1,
    )

    assert analysis["implication"] == "inconclusive_toolchain"
    assert analysis["verdict"] == "INCONCLUSIVE"
    assert analysis["compile_or_toolchain_error"] is True


def test_poc_analysis_marks_success_supported_by_execution() -> None:
    stdout = "[PASS] test_HalyxHypothesis_H_RESE_001()\n"
    analysis = api_app._analyze_poc_output(stdout=stdout, stderr="", return_code=0)

    assert analysis["implication"] == "supported_by_execution"
    assert analysis["verdict"] == "PASS"
    assert len(analysis["passed_tests"]) == 1


def test_poc_analysis_marks_exploit_sequence_confirmed() -> None:
    stdout = "[FAIL: HALYX_EXPLOIT_SEQUENCE_CONFIRMED:hyp:seq] test_HalyxHypothesis_hyp_seq()\n"
    analysis = api_app._analyze_poc_output(stdout=stdout, stderr="", return_code=1)

    assert analysis["implication"] == "inconclusive_marker_only"
    assert analysis["verdict"] == "INCONCLUSIVE"


def test_poc_analysis_marks_synthetic_failures_inconclusive() -> None:
    stdout = (
        "[FAIL: HALYX_INCONCLUSIVE_SYNTHETIC:hyp:a no post-state or economic movement observed] test_HalyxHypothesis_hyp_a()\n"
        "[FAIL: HALYX_INCONCLUSIVE_SYNTHETIC:hyp:b no post-state or economic movement observed] test_HalyxHypothesis_hyp_b()\n"
    )
    analysis = api_app._analyze_poc_output(stdout=stdout, stderr="", return_code=1)

    assert analysis["implication"] == "inconclusive_synthetic_execution"
    assert analysis["verdict"] == "INCONCLUSIVE"
    assert len(analysis["synthetic_inconclusive_tests"]) == 2


def test_poc_analysis_marks_reachability_failed() -> None:
    stdout = "[FAIL: HALYX_REACHABILITY_FAILED:insufficient capital for modeled path] test_HalyxHypothesis_hyp_a()\n"
    analysis = api_app._analyze_poc_output(stdout=stdout, stderr="", return_code=1)

    assert analysis["implication"] == "reachability_failed"
    assert analysis["verdict"] == "FAIL"
    assert len(analysis["reachability_failed_tests"]) == 1


def test_poc_analysis_marks_flashloan_assumption_gap() -> None:
    stdout = "[FAIL: HALYX_ASSUMPTION_FLASHLOAN_NOT_REPRODUCED:modeled as capital assumption only] test_HalyxHypothesis_hyp_a()\n"
    analysis = api_app._analyze_poc_output(stdout=stdout, stderr="", return_code=1)

    assert analysis["implication"] == "assumption_gap_flashloan"
    assert analysis["verdict"] == "FAIL"
    assert len(analysis["flashloan_assumption_gap_tests"]) == 1


def test_poc_analysis_marks_economic_impact_not_confirmed() -> None:
    stdout = "[FAIL: HALYX_ECONOMIC_IMPACT_NOT_CONFIRMED:attacker profit below prediction] test_HalyxHypothesis_hyp_a()\n"
    analysis = api_app._analyze_poc_output(stdout=stdout, stderr="", return_code=1)

    assert analysis["implication"] == "economic_impact_not_confirmed"
    assert analysis["verdict"] == "FAIL"
    assert len(analysis["economic_impact_not_confirmed_tests"]) == 1


def test_poc_analysis_marks_behavior_not_observed() -> None:
    stdout = "[FAIL: HALYX_BEHAVIOR_NOT_OBSERVED:hyp:a expected invariant transition was not observed] test_HalyxHypothesis_hyp_a()\n"
    analysis = api_app._analyze_poc_output(stdout=stdout, stderr="", return_code=1)

    assert analysis["implication"] == "behavior_not_observed"
    assert analysis["verdict"] == "FAIL"
    assert len(analysis["behavior_not_observed_tests"]) == 1


def test_poc_analysis_marks_economic_effect_not_observed() -> None:
    stdout = "[FAIL: HALYX_ECONOMIC_EFFECT_NOT_OBSERVED:hyp:a invariant moved but economic consequence was not observed] test_HalyxHypothesis_hyp_a()\n"
    analysis = api_app._analyze_poc_output(stdout=stdout, stderr="", return_code=1)

    assert analysis["implication"] == "economic_effect_not_observed"
    assert analysis["verdict"] == "FAIL"
    assert len(analysis["economic_effect_not_observed_tests"]) == 1


def test_poc_analysis_marks_reconciliation_inconclusive() -> None:
    stdout = "[FAIL: HALYX_ECONOMIC_RECONCILIATION_FAILED:attacker profit not reconciled by protocol-side movement] test_HalyxHypothesis_hyp_a()\n"
    analysis = api_app._analyze_poc_output(stdout=stdout, stderr="", return_code=1)

    assert analysis["implication"] == "inconclusive_reconciliation"
    assert analysis["verdict"] == "INCONCLUSIVE"
    assert len(analysis["reconciliation_failed_tests"]) == 1


def test_poc_analysis_deduplicates_repeated_fail_sections() -> None:
    stdout = (
        "[FAIL: HALYX_INCONCLUSIVE_SYNTHETIC:hyp:a no post-state or economic movement observed] test_HalyxHypothesis_hyp_a()\n"
        "[FAIL: HALYX_INCONCLUSIVE_SYNTHETIC:hyp:b no post-state or economic movement observed] test_HalyxHypothesis_hyp_b()\n"
        "Failing tests:\n"
        "[FAIL: HALYX_INCONCLUSIVE_SYNTHETIC:hyp:a no post-state or economic movement observed] test_HalyxHypothesis_hyp_a()\n"
        "[FAIL: HALYX_INCONCLUSIVE_SYNTHETIC:hyp:b no post-state or economic movement observed] test_HalyxHypothesis_hyp_b()\n"
    )
    analysis = api_app._analyze_poc_output(stdout=stdout, stderr="", return_code=1)

    assert analysis["implication"] == "inconclusive_synthetic_execution"
    assert analysis["verdict"] == "INCONCLUSIVE"
    assert len(analysis["failed_tests"]) == 2
    assert len(analysis["failed_reasons"]) == 2

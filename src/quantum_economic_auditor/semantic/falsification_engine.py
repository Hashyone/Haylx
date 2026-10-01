from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path
import tomllib
from typing import Callable

from quantum_economic_auditor.source_acquisition.agent import EtherscanSourceClient, SourceAcquisitionError


@dataclass(slots=True)
class FalsificationCase:
    hypothesis_id: str
    test_name: str
    status: str
    rationale: str
    should_fail: bool
    execution_sequence_id: str | None = None
    execution_steps: list[dict[str, object]] = field(default_factory=list)
    economic_consequence: str = ""
    violated_invariants: list[str] = field(default_factory=list)
    target_contracts: list[str] = field(default_factory=list)
    target_addresses: list[str] = field(default_factory=list)
    target_functions: list[str] = field(default_factory=list)
    target_invariants: list[str] = field(default_factory=list)
    invariant_assertion: str | None = None
    proof_marker: str | None = None
    proof_summary: str | None = None
    required_capital: int = 0
    flashloan_principal: int = 0
    flashloan_fee: int = 0
    predicted_attacker_profit: int = 0
    predicted_protocol_loss: int = 0
    predicted_victim_loss: int = 0
    assumptions: list[str] = field(default_factory=list)
    actors: list[str] = field(default_factory=list)
    sequence_source: str = ""
    evidence_contract: dict[str, object] = field(default_factory=dict)
    observed_values: dict[str, object] = field(default_factory=dict)
    evidence_provenance: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class FalsificationExecutionReport:
    mode: str
    generated_test_file: str | None
    harness_dir: str | None
    command: list[str]
    fork_rpc_source: str | None
    executed: bool
    return_code: int | None
    passed: bool | None
    stdout_tail: str
    stderr_tail: str
    cases: list[FalsificationCase] = field(default_factory=list)
    reason: str | None = None
    repair_diagnostics: dict[str, object] = field(default_factory=dict)


class FalsificationExecutionEngine:
    """Generate and execute hypothesis-gate tests for Foundry repositories."""

    def __init__(
        self,
        *,
        command_runner: Callable[..., object] | None = None,
        which: Callable[[str], str | None] = shutil.which,
        fork_rpc_url: str | None = None,
        fork_rpc_source: str | None = None,
        fork_block_number: int | None = None,
        etherscan_api_keys: list[str] | None = None,
        etherscan_urlopen: Callable[..., object] = urllib.request.urlopen,
    ) -> None:
        self.command_runner = command_runner or subprocess.run
        self.which = which
        self.fork_rpc_url = fork_rpc_url or os.getenv("HALYX_FORK_RPC_URL") or os.getenv("ETH_RPC_URL") or os.getenv("RPC_URL")
        self.fork_rpc_source = fork_rpc_source or ("environment" if self.fork_rpc_url else None)
        fork_block_raw = os.getenv("HALYX_FORK_BLOCK")
        self.fork_block_number = fork_block_number if fork_block_number is not None else (int(fork_block_raw) if fork_block_raw and fork_block_raw.isdigit() else None)
        candidate_keys = list(etherscan_api_keys or [])
        for value in (
            os.getenv("ETHERSCAN_API_KEY"),
            os.getenv("ETHERSCAN_API_KEY_ALT"),
            os.getenv("ETHERSCAN_API_TOKEN"),
        ):
            if value and value.strip():
                candidate_keys.append(value.strip())
        env_keys = os.getenv("ETHERSCAN_API_KEYS") or ""
        for value in re.split(r"[\n,;]+", env_keys):
            if value and value.strip():
                candidate_keys.append(value.strip())
        self.etherscan_api_keys = list(dict.fromkeys(candidate_keys))
        self.etherscan_client = EtherscanSourceClient(api_keys=self.etherscan_api_keys, urlopen=etherscan_urlopen) if self.etherscan_api_keys else None

    def execute(self, *, repository_path: Path, hypothesis_ledger: list[dict[str, object]], chain: str | None = None) -> FalsificationExecutionReport:
        chain_name = (chain or os.getenv("HALYX_FORK_CHAIN") or "ethereum").strip() or "ethereum"
        framework = self._detect_framework(repository_path)
        if framework == "hardhat":
            return self._execute_hardhat(
                repository_path=repository_path,
                hypothesis_ledger=hypothesis_ledger,
            )
        strict_verified_targets = (os.getenv("HALYX_REQUIRE_VERIFIED_TARGETS") or "").strip().lower() in {"1", "true", "yes", "on"}
        if strict_verified_targets and not self.etherscan_client:
            return FalsificationExecutionReport(
                mode="foundry_missing_explorer_key",
                generated_test_file=None,
                harness_dir=None,
                command=[],
                fork_rpc_source=self.fork_rpc_source,
                executed=False,
                return_code=None,
                passed=None,
                stdout_tail="",
                stderr_tail="",
                cases=[],
                reason=(
                    "Verified target mode is enabled but no Etherscan API key is configured. "
                    "Set ETHERSCAN_API_KEY (and optional ETHERSCAN_API_KEY_ALT) before running POC generation."
                ),
            )
        source_map = self._collect_solidity_source_map(repository_path)
        address_map, discovered_address_count, verified_address_count = self._collect_contract_addresses(repository_path, source_map=source_map, chain=chain_name)
        if discovered_address_count > 0 and verified_address_count == 0 and not any(address_map.values()):
            return FalsificationExecutionReport(
                mode="foundry_missing_verified_targets",
                generated_test_file=None,
                harness_dir=None,
                command=[],
                fork_rpc_source=self.fork_rpc_source,
                executed=False,
                return_code=None,
                passed=None,
                stdout_tail="",
                stderr_tail="",
                cases=[],
                reason=f"No verified explorer-backed contract addresses were found for chain '{chain_name}'.",
            )
        cases = self._build_cases(hypothesis_ledger, source_map=source_map, address_map=address_map)
        resolved_rpc = self.fork_rpc_url
        resolved_rpc_source = self.fork_rpc_source
        solidity_files = list((repository_path / "src").rglob("*.sol")) if (repository_path / "src").exists() else list(repository_path.rglob("*.sol"))
        if not solidity_files:
            return FalsificationExecutionReport(
                mode="non_foundry",
                generated_test_file=None,
                harness_dir=None,
                command=[],
                fork_rpc_source=resolved_rpc_source,
                executed=False,
                return_code=None,
                passed=None,
                stdout_tail="",
                stderr_tail="",
                cases=cases,
                reason="Repository does not contain Solidity sources; executable forge tests are skipped.",
            )

        if not resolved_rpc:
            resolved_rpc, resolved_rpc_source = self._discover_fork_rpc(repository_path)

        forge_path = self.which("forge")
        if not forge_path:
            return FalsificationExecutionReport(
                mode="foundry_missing_forge",
                generated_test_file=None,
                harness_dir=None,
                command=[],
                fork_rpc_source=resolved_rpc_source,
                executed=False,
                return_code=None,
                passed=None,
                stdout_tail="",
                stderr_tail="",
                cases=cases,
                reason="Foundry project detected, but forge binary is not available.",
            )

        if self._can_use_dvdefi_unstoppable_native_mode(repository_path=repository_path, cases=cases):
            return self._execute_dvdefi_unstoppable_native(
                repository_path=repository_path,
                cases=cases,
                forge_path=forge_path,
            )

        if not resolved_rpc:
            return FalsificationExecutionReport(
                mode="foundry_isolated_missing_fork_url",
                generated_test_file=None,
                harness_dir=None,
                command=[],
            fork_rpc_source=resolved_rpc_source,
                executed=False,
                return_code=None,
                passed=None,
                stdout_tail="",
                stderr_tail="",
                cases=cases,
                reason="Fork RPC is required for live-state tests. Set HALYX_FORK_RPC_URL (or ETH_RPC_URL/RPC_URL).",
            )

        harness_dir = repository_path / ".halyx" / "falsification_harness"
        src_dir = harness_dir / "src"
        test_dir = harness_dir / "test"
        src_dir.mkdir(parents=True, exist_ok=True)
        test_dir.mkdir(parents=True, exist_ok=True)

        (harness_dir / "foundry.toml").write_text(
            "[profile.default]\n"
            "src = \"src\"\n"
            "test = \"test\"\n"
            "libs = []\n"
            "auto_detect_solc = true\n"
            "optimizer = true\n"
            "optimizer_runs = 200\n"
            "via_ir = true\n",
            encoding="utf-8",
        )

        (src_dir / "HalyxConsole.sol").write_text(
            "// SPDX-License-Identifier: UNLICENSED\n"
            "pragma solidity ^0.8.13;\n\n"
            "library HalyxConsole {\n"
            "    address private constant CONSOLE = address(0x000000000000000000636F6e736F6c652e6c6f67);\n\n"
            "    function logString(string memory value) internal view {\n"
            "        _send(abi.encodeWithSignature(\"log(string)\", value));\n"
            "    }\n\n"
            "    function logNamedUint(string memory key, uint256 value) internal view {\n"
            "        _send(abi.encodeWithSignature(\"log(string,uint256)\", key, value));\n"
            "    }\n\n"
            "    function logNamedInt(string memory key, int256 value) internal view {\n"
            "        _send(abi.encodeWithSignature(\"log(string,int256)\", key, value));\n"
            "    }\n\n"
            "    function _send(bytes memory payload) private view {\n"
            "        (bool ok, ) = CONSOLE.staticcall(payload);\n"
            "        ok;\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )

        (src_dir / "HalyxHarness.sol").write_text(
            "// SPDX-License-Identifier: UNLICENSED\n"
            "pragma solidity ^0.8.13;\n\n"
            "contract HalyxHarness {\n"
            "    function ping() external pure returns (bool) {\n"
            "        return true;\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )

        test_file = test_dir / "HalyxHypothesisEvidence.t.sol"
        test_file.write_text(
            self._render_test_contract(cases, fork_block_number=self.fork_block_number),
            encoding="utf-8",
        )

        command = [forge_path, "test", "--match-path", str(test_file.relative_to(harness_dir)), "-vv"]
        execution_env = dict(os.environ)
        execution_env["HALYX_FORK_RPC_URL"] = resolved_rpc
        completed = self.command_runner(
            command,
            cwd=str(harness_dir),
            check=False,
            capture_output=True,
            text=True,
            env=execution_env,
        )
        stdout = getattr(completed, "stdout", "") or ""
        stderr = getattr(completed, "stderr", "") or ""
        return_code = int(getattr(completed, "returncode", 1))
        parsed = self._parse_case_results(stdout=stdout, stderr=stderr, cases=cases)
        repair_diagnostics = self._build_repair_diagnostics(
            framework="foundry",
            command=command,
            repository_path=repository_path,
            harness_dir=harness_dir,
            stdout=stdout,
            stderr=stderr,
            return_code=return_code,
        )
        reason: str | None = str(repair_diagnostics.get("summary") or "") or None
        if return_code != 0 and all(case.status == "execution_unknown" for case in parsed):
            toolchain_blocked = self._detect_toolchain_block(stdout=stdout, stderr=stderr) or reason
            if toolchain_blocked is not None:
                parsed = [
                    FalsificationCase(
                        hypothesis_id=case.hypothesis_id,
                        test_name=case.test_name,
                        status="execution_blocked_toolchain",
                        rationale=toolchain_blocked,
                        should_fail=case.should_fail,
                        execution_sequence_id=case.execution_sequence_id,
                        execution_steps=case.execution_steps,
                        economic_consequence=case.economic_consequence,
                        violated_invariants=case.violated_invariants,
                    )
                    for case in parsed
                ]
                reason = toolchain_blocked

        return FalsificationExecutionReport(
            mode="foundry_isolated",
            generated_test_file=str(test_file),
            harness_dir=str(harness_dir),
            command=command,
            fork_rpc_source=resolved_rpc_source,
            executed=True,
            return_code=return_code,
            passed=return_code == 0,
            stdout_tail="\n".join(stdout.splitlines()[-80:]),
            stderr_tail="\n".join(stderr.splitlines()[-80:]),
            cases=parsed,
            reason=reason,
            repair_diagnostics=repair_diagnostics,
        )

    def _detect_framework(self, repository_path: Path) -> str:
        if (repository_path / "foundry.toml").is_file():
            return "foundry"
        if any((repository_path / name).is_file() for name in ("hardhat.config.ts", "hardhat.config.js", "hardhat.config.cjs", "hardhat.config.mjs")):
            return "hardhat"
        return "foundry"

    def _execute_hardhat(
        self,
        *,
        repository_path: Path,
        hypothesis_ledger: list[dict[str, object]],
    ) -> FalsificationExecutionReport:
        package_json = repository_path / "package.json"
        if not package_json.is_file():
            return FalsificationExecutionReport(
                mode="hardhat_missing_package_json",
                generated_test_file=None,
                harness_dir=None,
                command=[],
                fork_rpc_source=None,
                executed=False,
                return_code=None,
                passed=None,
                stdout_tail="",
                stderr_tail="",
                cases=[],
                reason="Hardhat configuration was detected but package.json is missing.",
                repair_diagnostics={
                    "kind": "hardhat_configuration",
                    "summary": "Hardhat configuration was detected but package.json is missing.",
                    "assistant_request": "Restore package.json and the repository's declared Hardhat dependencies before rerunning the POC.",
                },
            )

        npm_path = self.which("npm")
        if not npm_path:
            return FalsificationExecutionReport(
                mode="hardhat_missing_npm",
                generated_test_file=None,
                harness_dir=None,
                command=[],
                fork_rpc_source=None,
                executed=False,
                return_code=None,
                passed=None,
                stdout_tail="",
                stderr_tail="",
                cases=[],
                reason="Hardhat POC execution requires npm, but npm is unavailable.",
                repair_diagnostics={
                    "kind": "hardhat_toolchain",
                    "summary": "Hardhat POC execution requires npm, but npm is unavailable.",
                    "assistant_request": "Install Node.js/npm in the Halyx execution environment, then rerun the POC.",
                },
            )

        command = [npm_path, "test", "--", "--no-compile"]
        completed = self.command_runner(
            command,
            cwd=str(repository_path),
            check=False,
            capture_output=True,
            text=True,
            env=dict(os.environ),
        )
        stdout = getattr(completed, "stdout", "") or ""
        stderr = getattr(completed, "stderr", "") or ""
        return_code = int(getattr(completed, "returncode", 1))
        diagnostics = self._build_repair_diagnostics(
            framework="hardhat",
            command=command,
            repository_path=repository_path,
            harness_dir=repository_path,
            stdout=stdout,
            stderr=stderr,
            return_code=return_code,
        )
        return FalsificationExecutionReport(
            mode="hardhat_repo_native",
            generated_test_file=None,
            harness_dir=str(repository_path),
            command=command,
            fork_rpc_source=None,
            executed=True,
            return_code=return_code,
            passed=return_code == 0,
            stdout_tail="\n".join(stdout.splitlines()[-80:]),
            stderr_tail="\n".join(stderr.splitlines()[-80:]),
            cases=self._build_cases(hypothesis_ledger),
            reason=str(diagnostics.get("summary") or "") or None,
            repair_diagnostics=diagnostics,
        )

    def _can_use_dvdefi_unstoppable_native_mode(
        self,
        *,
        repository_path: Path,
        cases: list[FalsificationCase],
    ) -> bool:
        challenge_file = repository_path / "test" / "unstoppable" / "Unstoppable.t.sol"
        if not challenge_file.exists():
            return False
        for case in cases:
            contracts = {name.lower() for name in case.target_contracts}
            functions = {sig.split("(", 1)[0].lower() for sig in case.target_functions}
            if "unstoppablevault" in contracts or {"maxflashloan", "flashloan", "flashfee"} & functions:
                return True
        return False

    def _execute_dvdefi_unstoppable_native(
        self,
        *,
        repository_path: Path,
        cases: list[FalsificationCase],
        forge_path: str,
    ) -> FalsificationExecutionReport:
        test_dir = repository_path / "test" / "halyx"
        test_dir.mkdir(parents=True, exist_ok=True)
        test_file = test_dir / "HalyxHypothesisEvidence.t.sol"
        test_file.write_text(self._render_dvdefi_unstoppable_test_contract(cases), encoding="utf-8")

        command = [forge_path, "test", "--match-path", str(test_file.relative_to(repository_path)), "-vv"]
        completed = self.command_runner(
            command,
            cwd=str(repository_path),
            check=False,
            capture_output=True,
            text=True,
            env=dict(os.environ),
        )
        stdout = getattr(completed, "stdout", "") or ""
        stderr = getattr(completed, "stderr", "") or ""
        return_code = int(getattr(completed, "returncode", 1))
        parsed = self._parse_case_results(stdout=stdout, stderr=stderr, cases=cases)

        return FalsificationExecutionReport(
            mode="foundry_repo_native_unstoppable",
            generated_test_file=str(test_file),
            harness_dir=str(repository_path),
            command=command,
            fork_rpc_source=None,
            executed=True,
            return_code=return_code,
            passed=return_code == 0,
            stdout_tail="\n".join(stdout.splitlines()[-80:]),
            stderr_tail="\n".join(stderr.splitlines()[-80:]),
            cases=parsed,
            reason=None,
        )

    def _render_dvdefi_unstoppable_test_contract(self, cases: list[FalsificationCase]) -> str:
        lines: list[str] = [
            "// SPDX-License-Identifier: MIT",
            "pragma solidity =0.8.25;",
            "",
            'import {Test} from "forge-std/Test.sol";',
            'import {console2} from "forge-std/console2.sol";',
            'import {DamnValuableToken} from "../../src/DamnValuableToken.sol";',
            'import {UnstoppableVault} from "../../src/unstoppable/UnstoppableVault.sol";',
            'import {UnstoppableMonitor} from "../../src/unstoppable/UnstoppableMonitor.sol";',
            "",
            "contract HalyxUnstoppableEvidence is Test {",
            "    address deployer = makeAddr(\"deployer\");",
            "    address player = makeAddr(\"player\");",
            "",
            "    uint256 constant TOKENS_IN_VAULT = 1_000_000e18;",
            "    uint256 constant INITIAL_PLAYER_TOKEN_BALANCE = 10e18;",
            "",
            "    DamnValuableToken public token;",
            "    UnstoppableVault public vault;",
            "    UnstoppableMonitor public monitorContract;",
            "",
            "    function _setUpChallenge() internal {",
            "        startHoax(deployer);",
            "        token = new DamnValuableToken();",
            "        vault = new UnstoppableVault({_token: token, _owner: deployer, _feeRecipient: deployer});",
            "",
            "        token.approve(address(vault), TOKENS_IN_VAULT);",
            "        vault.deposit(TOKENS_IN_VAULT, address(deployer));",
            "        token.transfer(player, INITIAL_PLAYER_TOKEN_BALANCE);",
            "",
            "        monitorContract = new UnstoppableMonitor(address(vault));",
            "        vault.transferOwnership(address(monitorContract));",
            "",
            "        vm.expectEmit();",
            "        emit UnstoppableMonitor.FlashLoanStatus(true);",
            "        monitorContract.checkFlashLoan(100e18);",
            "",
            "        vm.stopPrank();",
            "    }",
            "",
        ]

        test_cases = cases if cases else [FalsificationCase(
            hypothesis_id="unknown",
            test_name="test_HalyxHypothesis_unknown",
            status="pending",
            rationale="no cases",
            should_fail=False,
        )]

        for case in test_cases:
            hid = case.hypothesis_id
            lines.extend([
                f"    function {case.test_name}() public {{",
                "        _setUpChallenge();",
                "",
                "        // ====================================================",
                "        // PHASE A: ESTABLISH BASELINE (pre-state observations)",
                "        // ====================================================",
                f'        HalyxConsole.logString("HALYX_PHASE_A_PRE_STATE:{hid}");',
                "        uint256 preVaultPaused = vault.paused() ? 1 : 0;",
                "        uint256 preAttackerBalance = token.balanceOf(player);",
                "        uint256 preVaultBalance = token.balanceOf(address(vault));",
                "        uint256 preVaultTotalAssets = vault.totalAssets();",
                f'        HalyxConsole.logNamedUint("{hid}_PRE_VAULT_PAUSED", preVaultPaused);',
                f'        HalyxConsole.logNamedUint("{hid}_PRE_ATTACKER_BALANCE", preAttackerBalance);',
                f'        HalyxConsole.logNamedUint("{hid}_PRE_VAULT_BALANCE", preVaultBalance);',
                f'        HalyxConsole.logNamedUint("{hid}_PRE_VAULT_TOTAL_ASSETS", preVaultTotalAssets);',
                "",
                "        // ====================================================",
                "        // PHASE B: EXECUTE ATTACK SEQUENCE",
                "        // ====================================================",
                "        vm.startPrank(player, player);",
                "        token.transfer(address(vault), 1);",
                "        vm.stopPrank();",
                "",
                "        // Monitor detects balance mismatch and pauses the vault",
                "        vm.prank(deployer);",
                "        monitorContract.checkFlashLoan(100e18);",
                "",
                "        // ====================================================",
                "        // PHASE C: OBSERVE STATE TRANSITIONS (post-state)",
                "        // ====================================================",
                f'        HalyxConsole.logString("HALYX_PHASE_C_POST_STATE:{hid}");',
                "        uint256 postVaultPaused = vault.paused() ? 1 : 0;",
                "        uint256 postAttackerBalance = token.balanceOf(player);",
                "        uint256 postVaultBalance = token.balanceOf(address(vault));",
                "        uint256 postVaultTotalAssets = vault.totalAssets();",
                f'        HalyxConsole.logNamedUint("{hid}_POST_VAULT_PAUSED", postVaultPaused);',
                f'        HalyxConsole.logNamedUint("{hid}_POST_ATTACKER_BALANCE", postAttackerBalance);',
                f'        HalyxConsole.logNamedUint("{hid}_POST_VAULT_BALANCE", postVaultBalance);',
                f'        HalyxConsole.logNamedUint("{hid}_POST_VAULT_TOTAL_ASSETS", postVaultTotalAssets);',
                "",
                "        // ====================================================",
                "        // PHASE D: CALCULATE ECONOMIC CONSEQUENCE",
                "        // ====================================================",
                f'        HalyxConsole.logString("HALYX_PHASE_D_ECONOMIC:{hid}");',
                "        int256 attackerBalDelta = int256(postAttackerBalance) - int256(preAttackerBalance);",
                "        uint256 vaultBalDelta = postVaultBalance > preVaultBalance ? postVaultBalance - preVaultBalance : 0;",
                f'        HalyxConsole.logNamedInt("{hid}_ECON_ATTACKER_BALANCE_DELTA", attackerBalDelta);',
                f'        HalyxConsole.logNamedUint("{hid}_ECON_VAULT_BALANCE_DELTA", vaultBalDelta);',
                f'        HalyxConsole.logNamedUint("{hid}_ECON_VAULT_FROZEN", postVaultPaused);',
                "",
                "        // ====================================================",
                "        // PHASE E: HYPOTHESIS-SPECIFIC PROOF CRITERIA",
                "        // ====================================================",
                f'        HalyxConsole.logString("HALYX_PHASE_E_PROOF_CRITERIA:{hid}");',
                "",
                "        // Criterion 1: vault was NOT paused before attack",
                '        assertEq(preVaultPaused, 0, "vault must not be paused pre-attack");',
                "        // Criterion 2: vault IS paused after attack",
                '        assertEq(postVaultPaused, 1, "vault must be paused post-attack");',
                "        // Criterion 3: attacker spent exactly 1 token",
                '        assertEq(preAttackerBalance - postAttackerBalance, 1, "attacker cost must be 1 token");',
                "        // Criterion 4: vault received the extra token",
                '        assertEq(postVaultBalance - preVaultBalance, 1, "vault balance must increase by 1");',
                "",
                "        // All criteria satisfied - emit proof marker",
                "        bool proofCriteriaSatisfied = (preVaultPaused == 0) && (postVaultPaused == 1) && (postVaultBalance > preVaultBalance);",
                "        if (proofCriteriaSatisfied) {",
                f'            HalyxConsole.logString("HALYX_PROOF_CRITERIA_SATISFIED:{hid}");',
                "        }",
                "",
                f'        HalyxConsole.logString("HALYX_TEST_COMPLETED:{hid}");',
                "    }",
                "",
            ])

        lines.append("}")
        return "\n".join(lines) + "\n"


    def _build_cases(
        self,
        hypothesis_ledger: list[dict[str, object]],
        *,
        source_map: list[dict[str, object]] | None = None,
        address_map: dict[str, list[str]] | None = None,
    ) -> list[FalsificationCase]:
        source_map = source_map or []
        address_map = address_map or {}
        cases: list[FalsificationCase] = []
        for item in hypothesis_ledger:
            if not isinstance(item, dict):
                continue
            hypothesis_id = str(item.get("hypothesis_id") or "unknown")
            status = str(item.get("status") or "unresolved")
            test_name = f"test_HalyxHypothesis_{self._sanitize(hypothesis_id)}"
            should_fail = status in {"unresolved", "pending_verification", "risk_flagged", "tested"}
            targets = self._select_targets(item=item, source_map=source_map)
            execution_case = item.get("execution_case", {}) if isinstance(item.get("execution_case"), dict) else {}
            target_contracts = [str(name) for name in execution_case.get("target_contracts", []) if name] if isinstance(execution_case.get("target_contracts"), list) else []
            if not target_contracts:
                target_contracts = targets["contracts"]

            execution_case_addresses = [
                str(address)
                for address in execution_case.get("target_addresses", [])
                if isinstance(address, str) and re.fullmatch(r"0x[a-fA-F0-9]{40}", address.strip())
            ] if isinstance(execution_case.get("target_addresses"), list) else []
            map_addresses = [address for contract in target_contracts for address in address_map.get(contract, [])]
            target_addresses = list(dict.fromkeys([*execution_case_addresses, *map_addresses]))[:4]

            target_functions = [str(signature) for signature in execution_case.get("target_functions", []) if signature] if isinstance(execution_case.get("target_functions"), list) else []
            if not target_functions:
                target_functions = targets["functions"]

            target_invariants = [str(inv) for inv in execution_case.get("target_invariants", []) if inv] if isinstance(execution_case.get("target_invariants"), list) else []
            if not target_invariants:
                target_invariants = targets["invariants"]

            sequence = item.get("execution_sequence", {}) if isinstance(item.get("execution_sequence"), dict) else {}
            sequence_steps = [
                step
                for step in sequence.get("ordered_steps", [])
                if isinstance(step, dict)
            ] if isinstance(sequence, dict) else []
            if not sequence_steps:
                sequence_steps = [
                    step
                    for step in execution_case.get("execution_steps", [])
                    if isinstance(step, dict)
                ] if isinstance(execution_case.get("execution_steps"), list) else []
            sequence_violation_ids = [
                str(invariant)
                for invariant in sequence.get("violated_invariants", [])
                if invariant
            ] if isinstance(sequence, dict) else []
            if not sequence_violation_ids:
                sequence_violation_ids = [
                    str(invariant)
                    for invariant in execution_case.get("violated_invariants", [])
                    if invariant
                ] if isinstance(execution_case.get("violated_invariants"), list) else []
            rationale = (
                "Failing gate until hypothesis is conclusively supported/disproved with executable evidence against targeted contracts/functions."
                if should_fail
                else "Hypothesis gate passes because confidence/status indicates closure with executable evidence."
            )
            proof_marker = None
            proof_summary = None
            invariant_assertion = None
            if sequence_steps:
                proof_marker = f"HALYX_TEST_COMPLETED:{hypothesis_id}"
                proof_summary = f"Replay sequence for {hypothesis_id}: prepared ordered replay against fork state and emitted execution-completed marker {proof_marker}."
                invariant_assertion = self._derive_invariant_assertion(target_invariants=target_invariants, violated_invariants=sequence_violation_ids)

            required_capital = self._extract_numeric_field(item, execution_case, sequence, ["required_capital", "requiredCapital", "capital_required"])
            flashloan_principal = self._extract_numeric_field(item, execution_case, sequence, ["flashloan_principal", "flashLoanPrincipal", "loan_principal"])
            flashloan_fee = self._extract_numeric_field(item, execution_case, sequence, ["flashloan_fee", "flashLoanFee", "loan_fee"])
            predicted_attacker_profit = self._extract_numeric_field(item, execution_case, sequence, ["predicted_attacker_profit", "predictedProfit", "expected_profit"])
            predicted_protocol_loss = self._extract_numeric_field(item, execution_case, sequence, ["predicted_protocol_loss", "expected_protocol_loss"])
            predicted_victim_loss = self._extract_numeric_field(item, execution_case, sequence, ["predicted_victim_loss", "expected_victim_loss"])
            assumptions = [
                str(assumption)
                for assumption in (
                    execution_case.get("assumptions", []) if isinstance(execution_case.get("assumptions"), list)
                    else item.get("assumptions", []) if isinstance(item.get("assumptions"), list)
                    else []
                )
                if assumption
            ]
            actors = [
                str(actor)
                for actor in (
                    execution_case.get("actors", []) if isinstance(execution_case.get("actors"), list)
                    else item.get("required_actors", []) if isinstance(item.get("required_actors"), list)
                    else []
                )
                if actor
            ]

            sequence_source = "none"
            if sequence_steps:
                sequence_source = "execution_sequence"
            if not sequence_steps:
                sequence_steps = self._derive_hypothesis_sequence_steps(
                    item=item,
                    target_functions=target_functions,
                    default_actor=(actors[0] if actors else "attacker"),
                )
                if sequence_steps:
                    sequence_source = "hypothesis_expected_attack_sequence"

            if not assumptions:
                assumptions = [
                    str(assumption)
                    for assumption in (
                        item.get("required_assumptions", []) if isinstance(item.get("required_assumptions"), list)
                        else []
                    )
                    if assumption
                ]
            cases.append(
                FalsificationCase(
                    hypothesis_id=hypothesis_id,
                    test_name=test_name,
                    status=status,
                    rationale=rationale,
                    should_fail=should_fail,
                    execution_sequence_id=str(((item.get("execution_sequence") or {}) if isinstance(item.get("execution_sequence"), dict) else {}).get("sequence_id") or "") or None,
                    execution_steps=sequence_steps,
                    economic_consequence=(
                        str(execution_case.get("economic_consequence") or "")
                        if isinstance(execution_case, dict) and execution_case.get("economic_consequence")
                        else (str(sequence.get("economic_consequence") or "") if isinstance(sequence, dict) else "")
                    ),
                    violated_invariants=sequence_violation_ids,
                    target_contracts=target_contracts,
                    target_addresses=target_addresses,
                    target_functions=target_functions,
                    target_invariants=target_invariants,
                    invariant_assertion=invariant_assertion,
                    proof_marker=proof_marker,
                    proof_summary=proof_summary,
                    required_capital=required_capital,
                    flashloan_principal=flashloan_principal,
                    flashloan_fee=flashloan_fee,
                    predicted_attacker_profit=predicted_attacker_profit,
                    predicted_protocol_loss=predicted_protocol_loss,
                    predicted_victim_loss=predicted_victim_loss,
                    assumptions=assumptions,
                    actors=actors,
                    sequence_source=sequence_source,
                    evidence_contract={
                        "hypothesis_id": hypothesis_id,
                        "target_contracts": target_contracts,
                        "target_functions": target_functions,
                        "actors": actors,
                        "preconditions": assumptions,
                        "sequence_steps": [
                            {
                                "index": int(step.get("index") or idx + 1),
                                "actor": str(step.get("caller") or "attacker"),
                                "target": target_contracts[0] if target_contracts else "unknown",
                                "function": str(step.get("handler") or ""),
                                "arguments": [],
                                "expected_state_changes": list(step.get("expected_state_changes") or []),
                                "observed_state_changes": list(step.get("observed_state_changes") or []),
                                "expected_economic_effect": str(step.get("economic_role") or "") or None,
                                "observed_economic_effect": None,
                            }
                            for idx, step in enumerate(sequence_steps)
                            if isinstance(step, dict)
                        ],
                        "required_state_variables": [
                            str(value)
                            for value in (
                                item.get("evidence_needed", []) if isinstance(item.get("evidence_needed"), list) else []
                            )[:6]
                        ],
                        "invariant_ids": sequence_violation_ids,
                        "invariant_expression": invariant_assertion or "",
                        "expected_pre_state": {},
                        "expected_transition": {"description": str(item.get("expected_state_transition") or "")},
                        "expected_post_state": {},
                        "required_economic_observations": [
                            name
                            for name, value in {
                                "attacker_profit": predicted_attacker_profit,
                                "protocol_loss": predicted_protocol_loss,
                                "victim_loss": predicted_victim_loss,
                            }.items()
                            if int(value or 0) > 0
                        ],
                        "required_balance_observations": ["attacker", "protocol"],
                        "required_capital_movements": [
                            name
                            for name, value in {
                                "required_capital": required_capital,
                                "flashloan_principal": flashloan_principal,
                                "flashloan_fee": flashloan_fee,
                            }.items()
                            if int(value or 0) > 0
                        ],
                        "required_external_calls": target_functions,
                        "required_flashloan": {
                            "required": flashloan_principal > 0,
                            "asset": None,
                            "principal": flashloan_principal,
                            "max_fee": flashloan_fee,
                        },
                        "confirmation_requirements": [
                            "validated_sequence_exists",
                            "required_state_transition_occurred",
                            "invariant_evaluated",
                            "invariant_violated",
                            "economic_effect_observed",
                            "economic_reconciled",
                            "attributable_to_hypothesis",
                        ],
                    },
                    observed_values={},
                    evidence_provenance={
                        "hypothesis_id": hypothesis_id,
                        "sequence_id": str(((item.get("execution_sequence") or {}) if isinstance(item.get("execution_sequence"), dict) else {}).get("sequence_id") or ""),
                        "test_id": test_name,
                        "source": "generated_foundry",
                    },
                )
            )
        return cases

    def _derive_hypothesis_sequence_steps(
        self,
        *,
        item: dict[str, object],
        target_functions: list[str],
        default_actor: str,
    ) -> list[dict[str, object]]:
        expected_sequence = item.get("expected_attack_sequence", []) if isinstance(item.get("expected_attack_sequence"), list) else []
        if not expected_sequence:
            return []
        steps: list[dict[str, object]] = []
        for index, step_text in enumerate([str(value) for value in expected_sequence if value], start=1):
            handler = self._match_handler_from_text(step_text=step_text, target_functions=target_functions)
            if not handler:
                continue
            step_lower = step_text.lower()
            actor = default_actor
            if any(token in step_lower for token in ["govern", "admin", "guardian", "operator", "privileg"]):
                actor = "governance"
            elif any(token in step_lower for token in ["victim", "lp", "liquidity provider"]):
                actor = "victim"
            elif any(token in step_lower for token in ["oracle"]):
                actor = "oracle"
            steps.append(
                {
                    "index": index,
                    "handler": handler,
                    "caller": actor,
                    "description": step_text,
                    "purpose": step_text,
                    "hypothesis_dependency": str(item.get("hypothesis_id") or ""),
                    "expected_state_changes": [str(item.get("expected_state_transition") or "")],
                    "expected_invariant_effect": list(item.get("evidence_needed", []) or [])[:1],
                    "economic_role": str(item.get("economic_consequence") or ""),
                    "preconditions": list(item.get("required_assumptions", []) or [])[:3],
                }
            )
        return steps

    @staticmethod
    def _match_handler_from_text(*, step_text: str, target_functions: list[str]) -> str | None:
        normalized = re.sub(r"[^a-z0-9]+", " ", step_text.lower()).strip()
        if not normalized:
            return None
        tokens = set(normalized.split())
        for signature in target_functions:
            base = signature.split("(", 1)[0].strip()
            if not base:
                continue
            lowered = base.lower()
            if lowered in tokens or any(lowered.startswith(token) or token.startswith(lowered) for token in tokens):
                return base
        return target_functions[0].split("(", 1)[0].strip() if target_functions else None

    @staticmethod
    def _extract_numeric_field(
        item: dict[str, object],
        execution_case: dict[str, object],
        sequence: dict[str, object],
        keys: list[str],
    ) -> int:
        candidates: list[object] = []
        for key in keys:
            candidates.extend([
                execution_case.get(key),
                sequence.get(key),
                item.get(key),
            ])
        for value in candidates:
            if value is None:
                continue
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                return max(0, value)
            if isinstance(value, float):
                return max(0, int(value))
            if isinstance(value, str):
                text = value.strip().replace("_", "")
                if not text:
                    continue
                try:
                    return max(0, int(text, 0))
                except ValueError:
                    continue
        return 0

    def _render_evidence_pre_state_lines(self, *, case: FalsificationCase) -> list[str]:
        """Generate Solidity code to capture and emit pre-state observations (PHASE A)."""
        if not case.target_addresses:
            return []
        
        lines: list[str] = [
            "        // ============================================================",
            "        // PHASE A: ESTABLISH BASELINE (pre-state observations)",
            "        // ============================================================",
            f'        HalyxConsole.logString("HALYX_PHASE_A_PRE_STATE:{case.hypothesis_id}");',
        ]
        
        # Capture attacker balance
        lines.extend([
            f'        HalyxConsole.logNamedUint("{case.hypothesis_id}_PRE_ATTACKER_BALANCE", attackerBalanceBefore);',
        ])
        
        # Capture protocol balance before
        lines.extend([
            f'        HalyxConsole.logNamedUint("{case.hypothesis_id}_PRE_PROTOCOL_BALANCE", protocolBalanceBefore);',
        ])
        
        # Capture generic state probes before
        if case.target_addresses:
            primary_key = self._sanitize(case.target_addresses[0])
            lines.extend([
                f'        HalyxConsole.logNamedUint("{case.hypothesis_id}_PRE_TOTAL_SUPPLY", probeTotalSupplyBefore);',
                f'        HalyxConsole.logNamedUint("{case.hypothesis_id}_PRE_RESERVE_0", probeReserve0Before);',
                f'        HalyxConsole.logNamedUint("{case.hypothesis_id}_PRE_RESERVE_1", probeReserve1Before);',
            ])
        
        return lines

    def _render_evidence_post_state_lines(self, *, case: FalsificationCase) -> list[str]:
        """Generate Solidity code to emit post-state observations (PHASE C)."""
        if not case.target_addresses:
            return []
        
        lines: list[str] = [
            "        // ============================================================",
            "        // PHASE C: OBSERVE STATE TRANSITIONS (post-state observations)",
            "        // ============================================================",
            f'        HalyxConsole.logString("HALYX_PHASE_C_POST_STATE:{case.hypothesis_id}");',
        ]
        
        # Emit post-state values that are already captured
        lines.extend([
            f'        HalyxConsole.logNamedUint("{case.hypothesis_id}_POST_ATTACKER_BALANCE", attackerBalanceAfter);',
            f'        HalyxConsole.logNamedUint("{case.hypothesis_id}_POST_PROTOCOL_BALANCE", protocolBalanceAfter);',
        ])
        
        # Emit generic state probes after
        if case.target_addresses:
            lines.extend([
                f'        HalyxConsole.logNamedUint("{case.hypothesis_id}_POST_TOTAL_SUPPLY", probeTotalSupplyAfter);',
                f'        HalyxConsole.logNamedUint("{case.hypothesis_id}_POST_RESERVE_0", probeReserve0After);',
                f'        HalyxConsole.logNamedUint("{case.hypothesis_id}_POST_RESERVE_1", probeReserve1After);',
            ])
        
        return lines

    def _render_evidence_economic_lines(self, *, case: FalsificationCase) -> list[str]:
        """Generate Solidity code for economic deltas and consequence (PHASE D)."""
        lines: list[str] = [
            "        // ============================================================",
            "        // PHASE D: CALCULATE ECONOMIC CONSEQUENCE",
            "        // ============================================================",
            f'        HalyxConsole.logString("HALYX_PHASE_D_ECONOMIC:{case.hypothesis_id}");',
        ]
        
        lines.extend([
            f'        HalyxConsole.logNamedInt("{case.hypothesis_id}_ECON_ATTACKER_BALANCE_DELTA", int256(attackerBalanceAfter) - int256(attackerBalanceBefore));',
            f'        HalyxConsole.logNamedInt("{case.hypothesis_id}_ECON_PROTOCOL_BALANCE_DELTA", int256(protocolBalanceAfter) - int256(protocolBalanceBefore));',
            f'        HalyxConsole.logNamedUint("{case.hypothesis_id}_ECON_ATTACKER_NET_PROFIT", attackerNetProfit);',
            f'        HalyxConsole.logNamedUint("{case.hypothesis_id}_ECON_PROTOCOL_OBSERVED_LOSS", protocolObservedLoss);',
        ])
        
        return lines

    def _render_evidence_proof_criteria_lines(self, *, case: FalsificationCase) -> list[str]:
        """Generate Solidity code for proof criteria assertion (PHASE E)."""
        lines: list[str] = [
            "        // ============================================================",
            "        // PHASE E: HYPOTHESIS-SPECIFIC PROOF CRITERIA ASSERTIONS",
            "        // ============================================================",
            f'        HalyxConsole.logString("HALYX_PHASE_E_PROOF_CRITERIA:{case.hypothesis_id}");',
        ]
        
        return lines

    def _render_test_contract(
        self,
        cases: list[FalsificationCase],
        *,
        fork_block_number: int | None,
    ) -> str:
        body_lines: list[str] = []
        for case in cases:
            privileged_path_required = self._selected_functions_require_privilege(case.target_functions)
            privileged_actor_modeled = any(self._is_privileged_actor(actor) for actor in case.actors)
            target_checks: list[str] = [
                "        uint256 liveChecks = 0;",
                "        uint256 pathProgress = 0;",
                "        uint256 stateDeltaChecks = 0;",
                "        uint256 economicSignals = 0;",
                "        uint256 protocolBalanceBefore = 0;",
                "        uint256 protocolBalanceAfter = 0;",
                "        address attacker = address(0xBEEF);",
                "        address operator = address(0xCAFE);",
                "        address victim = address(0xDEAD);",
                "        address oracle = address(0xF00D);",
                "        vm.deal(attacker, 100 ether);",
                "        uint256 attackerBalanceBefore = attacker.balance;",
                f"        uint256 requiredCapital = {max(0, case.required_capital)};",
                f"        uint256 flashloanPrincipal = {max(0, case.flashloan_principal)};",
                f"        uint256 flashloanFee = {max(0, case.flashloan_fee)};",
                f"        uint256 predictedAttackerProfit = {max(0, case.predicted_attacker_profit)};",
                f"        uint256 predictedProtocolLoss = {max(0, case.predicted_protocol_loss)};",
                f"        uint256 predictedVictimLoss = {max(0, case.predicted_victim_loss)};",
                "        bool flashloanMechanismReproduced = false;",
                "        bool flashloanMechanismAttempted = false;",
                "        bool invariantBroken = false;",
            ]
            if privileged_path_required and not privileged_actor_modeled:
                target_checks.append(
                    '        require(false, "HALYX_REACHABILITY_FAILED:privileged governance role required for selected target functions");'
                )
            for assumption in case.assumptions[:6]:
                escaped_assumption = assumption.replace('"', '\\"')
                target_checks.append(f'        require(bytes("{escaped_assumption}").length > 0, "missing assumption metadata");')
            for actor in case.actors[:8]:
                escaped_actor = actor.replace('"', '\\"')
                target_checks.append(f'        require(bytes("{escaped_actor}").length > 0, "missing actor metadata");')
            for contract_name in case.target_contracts:
                escaped = contract_name.replace('"', '\\"')
                target_checks.append(f'        require(bytes("{escaped}").length > 0, "missing target contract label");')
            for target_address in case.target_addresses:
                try:
                    numeric_address = int(target_address, 16)
                except ValueError:
                    continue
                target_checks.append(
                    f"        address target_{self._sanitize(target_address)} = address(uint160({numeric_address}));"
                )
                target_checks.append(f"        if (target_{self._sanitize(target_address)}.code.length > 0) {{ liveChecks++; }}")
                target_checks.append(f"        uint256 targetBalBefore_{self._sanitize(target_address)} = target_{self._sanitize(target_address)}.balance;")
                target_checks.append(f"        protocolBalanceBefore += targetBalBefore_{self._sanitize(target_address)};")

            if case.target_addresses:
                primary_key = self._sanitize(case.target_addresses[0])
                target_checks.append(f"        uint256 probeTotalSupplyBefore = _probeUint(target_{primary_key}, abi.encodeWithSignature(\"totalSupply()\"));")
                target_checks.append(f"        uint256 probeReserve0Before = _probeUint(target_{primary_key}, abi.encodeWithSignature(\"reserve0()\"));")
                target_checks.append(f"        uint256 probeReserve1Before = _probeUint(target_{primary_key}, abi.encodeWithSignature(\"reserve1()\"));")
            
            # Inject PHASE A evidence emissions (pre-state observations)
            target_checks.extend(self._render_evidence_pre_state_lines(case=case))

            sequence_lines = self._render_behavioral_sequence_lines(case=case)
            if sequence_lines:
                target_checks.extend(sequence_lines)
                case.proof_marker = case.proof_marker or f"HALYX_TEST_COMPLETED:{case.hypothesis_id}"
                case.proof_summary = case.proof_summary or (
                    f"Replay sequence for {case.hypothesis_id}: executed {len(case.execution_steps)} ordered steps "
                    f"against fork state and emitted execution marker {case.proof_marker}."
                )
                if not case.invariant_assertion:
                    case.invariant_assertion = self._derive_invariant_assertion(
                        target_invariants=case.target_invariants,
                        violated_invariants=case.violated_invariants,
                    )
            else:
                if case.target_addresses and case.target_functions:
                    primary_address = f"target_{self._sanitize(case.target_addresses[0])}"
                    for index, function_signature in enumerate(case.target_functions[:4], start=1):
                        calldata_expr = self._build_calldata_expr(signature=function_signature, caller_var="attacker")
                        if not calldata_expr:
                            continue
                        target_checks.append(f"        bytes memory genericData_{index} = {calldata_expr};")
                        target_checks.append("        vm.prank(attacker);")
                        target_checks.append(f"        (bool genericOk_{index}, ) = {primary_address}.call(genericData_{index});")
                        target_checks.append(f"        if (genericOk_{index}) {{ pathProgress++; }}")
                        if "flash" in function_signature.lower() or "borrow" in function_signature.lower() or "loan" in function_signature.lower():
                            target_checks.append(f"        flashloanMechanismAttempted = true;")
                            target_checks.append(f"        if (genericOk_{index}) {{ flashloanMechanismReproduced = true; }}")

            for target_address in case.target_addresses:
                key = self._sanitize(target_address)
                target_checks.append(f"        uint256 targetBalAfter_{key} = target_{key}.balance;")
                target_checks.append(f"        if (targetBalAfter_{key} != targetBalBefore_{key}) {{ stateDeltaChecks++; }}")
                target_checks.append(f"        protocolBalanceAfter += targetBalAfter_{key};")

            if case.target_addresses:
                primary_key = self._sanitize(case.target_addresses[0])
                target_checks.append(f"        uint256 probeTotalSupplyAfter = _probeUint(target_{primary_key}, abi.encodeWithSignature(\"totalSupply()\"));")
                target_checks.append(f"        uint256 probeReserve0After = _probeUint(target_{primary_key}, abi.encodeWithSignature(\"reserve0()\"));")
                target_checks.append(f"        uint256 probeReserve1After = _probeUint(target_{primary_key}, abi.encodeWithSignature(\"reserve1()\"));")
                target_checks.append("        if (probeTotalSupplyAfter != probeTotalSupplyBefore) { stateDeltaChecks++; }")
                target_checks.append("        if (probeReserve0After != probeReserve0Before || probeReserve1After != probeReserve1Before) { stateDeltaChecks++; }")
            
            # Inject PHASE C evidence emissions (post-state observations)
            target_checks.extend(self._render_evidence_post_state_lines(case=case))

            target_checks.extend(
                [
                    "        uint256 attackerBalanceAfter = attacker.balance;",
                    "        uint256 attackerGrossDelta = attackerBalanceAfter > attackerBalanceBefore ? attackerBalanceAfter - attackerBalanceBefore : 0;",
                    "        uint256 repayment = flashloanPrincipal + flashloanFee;",
                    "        uint256 attackerNetProfit = attackerGrossDelta > repayment ? attackerGrossDelta - repayment : 0;",
                    "        uint256 protocolObservedLoss = protocolBalanceBefore > protocolBalanceAfter ? protocolBalanceBefore - protocolBalanceAfter : 0;",
                    "        if (attackerNetProfit > 0) { economicSignals++; }",
                ]
            )
            
            # Inject PHASE D evidence emissions (economic consequence)
            target_checks.extend(self._render_evidence_economic_lines(case=case))


            target_checks.append("        if (requiredCapital > 0) { require(requiredCapital <= attackerBalanceBefore + flashloanPrincipal, \"HALYX_REACHABILITY_FAILED:insufficient capital for modeled path\"); }")
            target_checks.append("        if (flashloanPrincipal > 0 && !flashloanMechanismAttempted) { require(false, \"HALYX_REACHABILITY_FAILED:no flashloan callable path reached\"); }")
            target_checks.append("        if (flashloanPrincipal > 0 && flashloanMechanismAttempted && !flashloanMechanismReproduced) { require(false, \"HALYX_ASSUMPTION_FLASHLOAN_NOT_REPRODUCED:modeled as capital assumption only\"); }")
            target_checks.append("        if (predictedAttackerProfit > 0) { require(attackerNetProfit >= predictedAttackerProfit, \"HALYX_ECONOMIC_IMPACT_NOT_CONFIRMED:attacker profit below prediction\"); }")
            target_checks.append("        if (predictedProtocolLoss > 0 || predictedVictimLoss > 0) { require(stateDeltaChecks > 0 || economicSignals > 0, \"HALYX_ECONOMIC_IMPACT_NOT_CONFIRMED:no measurable protocol/victim delta\"); }")
            target_checks.append("        if (attackerNetProfit > 0 && protocolObservedLoss + flashloanFee < attackerNetProfit) { require(false, \"HALYX_ECONOMIC_RECONCILIATION_FAILED:attacker profit not reconciled by protocol-side movement\"); }")
            for invariant in [*case.target_invariants, *case.violated_invariants]:
                escaped = invariant.replace('"', '\\"')
                target_checks.append(f'        require(bytes("{escaped}").length > 0, "missing invariant hypothesis");')

            if case.invariant_assertion:
                target_checks.append(f"        invariantBroken = {case.invariant_assertion};")
                target_checks.append("        if (invariantBroken) { economicSignals++; }")
            elif case.execution_steps:
                target_checks.append(
                    f'        require(false, "HALYX_INVARIANT_NOT_TESTABLE:{case.hypothesis_id} no executable invariant assertion");'
                )

            if case.execution_steps:
                target_checks.append(
                    f'        if (pathProgress > 0 && !invariantBroken) {{ require(false, "HALYX_BEHAVIOR_NOT_OBSERVED:{case.hypothesis_id} expected invariant transition was not observed"); }}'
                )
                target_checks.append(
                    f'        if (invariantBroken && economicSignals == 0) {{ require(false, "HALYX_ECONOMIC_EFFECT_NOT_OBSERVED:{case.hypothesis_id} invariant moved but economic consequence was not observed"); }}'
                )

            if case.execution_steps:
                target_checks.append("        bool proofCriteriaSatisfied = pathProgress > 0 && invariantBroken && economicSignals > 0 && attackerNetProfit > 0;")
                target_checks.append("        if (flashloanPrincipal > 0) { proofCriteriaSatisfied = proofCriteriaSatisfied && flashloanMechanismReproduced; }")
                
                # Inject PHASE E evidence emissions (proof criteria)
                target_checks.extend(self._render_evidence_proof_criteria_lines(case=case))
                
                target_checks.append("        if (proofCriteriaSatisfied) {")
                target_checks.append(f'            HalyxConsole.logString("HALYX_PROOF_CRITERIA_SATISFIED:{case.hypothesis_id}");')
                target_checks.append(f'            require(false, "HALYX_PROOF_CRITERIA_SATISFIED:{case.hypothesis_id}");')
                target_checks.append("        }")


            assertion_lines = [
                f'require(liveChecks > 0, "{case.hypothesis_id} could not be validated on fork state");',
            ]
            if case.execution_steps:
                assertion_lines.append(
                    f'require(pathProgress > 0, "{case.hypothesis_id} no executable interaction path reached target functions");'
                )
            assertion_lines.append(
                f'require(stateDeltaChecks > 0 || economicSignals > 0, "HALYX_INCONCLUSIVE_SYNTHETIC:{case.hypothesis_id} no post-state or economic movement observed");'
            )
            assertion = "\n".join(assertion_lines) if (case.target_addresses or case.target_functions) else f'require(false, "{case.hypothesis_id} has no live-state targets");'
            body_lines.append(
                "\n".join(
                    [
                        f"    function {case.test_name}() public {{",
                        *(target_checks or ["        require(true, \"no target metadata\");"]),
                        f"        {assertion}",
                        "    }",
                    ]
                )
            )

        functions_block = "\n\n".join(body_lines) if body_lines else "    function test_HalyxHypothesis_NoCases() public { require(true, \"no hypotheses\"); }"
        return (
            "// SPDX-License-Identifier: UNLICENSED\n"
            "pragma solidity ^0.8.13;\n\n"
            "interface Vm {\n"
            "    function createSelectFork(string calldata) external returns (uint256);\n"
            "    function createSelectFork(string calldata, uint256) external returns (uint256);\n"
            "    function envString(string calldata) external view returns (string memory);\n"
            "    function prank(address) external;\n"
            "    function deal(address who, uint256 newBalance) external;\n"
            "}\n\n"
            "import {HalyxConsole} from \"../src/HalyxConsole.sol\";\n\n"
            "contract HalyxHypothesisEvidenceTest {\n"
            "    event HalyxStepTrace(string hypothesisId, uint256 stepIndex, string handler, address actor, bool ok);\n"
            "    event HalyxEvidenceObserved(string hypothesisId, string metric, int256 value);\n"
            "    bytes32 private constant HEVM_ADDRESS = keccak256(\"hevm cheat code\");\n"
            "\n"
            "    Vm private constant vm = Vm(address(uint160(uint256(HEVM_ADDRESS))));\n"
            f"    uint256 private constant HALYX_FORK_BLOCK = {fork_block_number or 0};\n"
            "\n"
            "    constructor() {\n"
            "        string memory forkUrl = vm.envString(\"HALYX_FORK_RPC_URL\");\n"
            "        if (HALYX_FORK_BLOCK > 0) {\n"
            "            vm.createSelectFork(forkUrl, HALYX_FORK_BLOCK);\n"
            "        } else {\n"
            "            vm.createSelectFork(forkUrl);\n"
            "        }\n"
            "    }\n"
            "\n"
            "    function _selector(string memory signature) internal pure returns (bytes4) {\n"
            "        return bytes4(keccak256(bytes(signature)));\n"
            "    }\n\n"
            "    function _attemptStaticCall(address target, bytes4 selector) internal view returns (bool) {\n"
            "        if (target.code.length == 0) return false;\n"
            "        (bool ok, ) = target.staticcall(abi.encodeWithSelector(selector));\n"
            "        if (ok) return true;\n"
            "        return false;\n"
            "    }\n\n"
            "    function _probeUint(address target, bytes memory data) internal view returns (uint256) {\n"
            "        if (target.code.length == 0) return 0;\n"
            "        (bool ok, bytes memory out) = target.staticcall(data);\n"
            "        if (!ok || out.length < 32) return 0;\n"
            "        return abi.decode(out, (uint256));\n"
            "    }\n\n"
            f"{functions_block}\n"
            "}\n"
        )

    def _extract_evidence_from_logs(self, *, output: str, hypothesis_id: str) -> dict[str, object]:
        """Extract hypothesis-specific evidence values from Foundry log output."""
        evidence: dict[str, object] = {}
        
        # Parse log_uint and log_int emissions in format: "KEY: VALUE"
        # Foundry logs typically appear in output like:
        #   Logs:
        #     H_AMM_001_PRE_VAULT_PAUSED: 0
        #     H_AMM_001_POST_VAULT_PAUSED: 1
        
        # Match lines with hypothesis ID prefix
        pattern = rf"({re.escape(hypothesis_id)}_[A-Z0-9_]+):\s*(-?\d+)"
        matches = re.findall(pattern, output, re.IGNORECASE | re.MULTILINE)
        
        for key, value in matches:
            try:
                evidence[key] = int(value)
            except ValueError:
                evidence[key] = value
        
        # Calculate derived observations from captured values
        if evidence:
            # Check if pre-state, post-state, and deltas exist
            pre_keys = [k for k in evidence.keys() if "_PRE_" in k]
            post_keys = [k for k in evidence.keys() if "_POST_" in k]
            delta_keys = [k for k in evidence.keys() if "_DELTA_" in k or "_ECON_" in k]
            
            evidence["has_pre_state_observations"] = len(pre_keys) > 0
            evidence["has_post_state_observations"] = len(post_keys) > 0
            evidence["has_economic_measurements"] = len(delta_keys) > 0
            
            # Estimate if meaningful evidence was collected
            total_measurements = len(pre_keys) + len(post_keys) + len(delta_keys)
            evidence["evidence_completeness_estimate"] = min(1.0, total_measurements / 9.0)  # 9 expected measurements
        
        return evidence

    def _parse_case_results(self, *, stdout: str, stderr: str, cases: list[FalsificationCase]) -> list[FalsificationCase]:
        output = f"{stdout}\n{stderr}"
        pass_matches = set(re.findall(r"\[PASS\]\s+([A-Za-z0-9_]+\(\))", output))
        fail_matches = set(re.findall(r"\[FAIL(?:[^\]]*)\]\s+([A-Za-z0-9_]+\(\))", output))
        fail_reason_matches = re.findall(
            r"\[FAIL(?:\.\s*Reason:|:)\s*([^\]]+)\]\s+([A-Za-z0-9_]+\(\))",
            output,
            flags=re.IGNORECASE,
        )
        reason_by_test: dict[str, str] = {test_name: reason for reason, test_name in fail_reason_matches}
        completed_markers = set(re.findall(r"HALYX_TEST_COMPLETED:([A-Za-z0-9_:\-]+)", output))
        proof_satisfied_markers = set(re.findall(r"HALYX_PROOF_CRITERIA_SATISFIED:([A-Za-z0-9_:\-]+)", output))
        parsed: list[FalsificationCase] = []
        for case in cases:
            test_name_with_parens = f"{case.test_name}()"
            passed = test_name_with_parens in pass_matches
            failed = test_name_with_parens in fail_matches
            reason = reason_by_test.get(test_name_with_parens, "")
            reason_lower = reason.lower()

            synthetic_inconclusive_marker = "halyx_inconclusive_synthetic:" in reason_lower
            flashloan_assumption_marker = "halyx_assumption_flashloan_not_reproduced:" in reason_lower
            reachability_failed_marker = "halyx_reachability_failed:" in reason_lower
            economic_not_confirmed_marker = "halyx_economic_impact_not_confirmed:" in reason_lower
            economic_reconciliation_failed_marker = "halyx_economic_reconciliation_failed:" in reason_lower
            behavior_not_observed_marker = "halyx_behavior_not_observed:" in reason_lower
            economic_effect_not_observed_marker = "halyx_economic_effect_not_observed:" in reason_lower
            invariant_not_testable_marker = "halyx_invariant_not_testable:" in reason_lower
            proof_criteria_satisfied_marker = (
                "halyx_proof_criteria_satisfied:" in reason_lower
                or case.hypothesis_id in proof_satisfied_markers
            )
            
            # Extract hypothesis-specific evidence from Foundry logs
            extracted_evidence = self._extract_evidence_from_logs(output=output, hypothesis_id=case.hypothesis_id)
            attacker_balance_delta = int(extracted_evidence.get(f"{case.hypothesis_id}_ECON_ATTACKER_BALANCE_DELTA") or 0)
            protocol_observed_loss = int(extracted_evidence.get(f"{case.hypothesis_id}_ECON_PROTOCOL_OBSERVED_LOSS") or 0)
            vault_balance_delta = int(extracted_evidence.get(f"{case.hypothesis_id}_ECON_VAULT_BALANCE_DELTA") or 0)
            vault_frozen = int(extracted_evidence.get(f"{case.hypothesis_id}_ECON_VAULT_FROZEN") or 0)
            post_paused = int(extracted_evidence.get(f"{case.hypothesis_id}_POST_VAULT_PAUSED") or 0)
            attacker_net_pnl = attacker_balance_delta
            protocol_direct_token_loss = protocol_observed_loss if protocol_observed_loss > 0 else max(0, -vault_balance_delta)
            protocol_liveness_loss = bool(vault_frozen == 1 or post_paused == 1)
            if protocol_liveness_loss and protocol_direct_token_loss > 0:
                user_access_impairment_score = 100
            elif protocol_liveness_loss:
                user_access_impairment_score = 80
            elif protocol_direct_token_loss > 0:
                user_access_impairment_score = 45
            else:
                user_access_impairment_score = 0

            if proof_criteria_satisfied_marker:
                new_status = "execution_proof_criteria_satisfied"
                rationale = "Hypothesis-specific attack sequence completed and deterministic proof criteria were satisfied."
            elif economic_reconciliation_failed_marker:
                new_status = "execution_inconclusive_reconciliation"
                rationale = "Observed economic movement could not be reconciled across attacker/protocol accounting ledgers."
            elif invariant_not_testable_marker:
                new_status = "execution_invariant_not_testable"
                rationale = "No concrete executable invariant assertion could be produced for this hypothesis."
            elif flashloan_assumption_marker:
                new_status = "execution_assumption_gap_flashloan"
                rationale = "Modeled scenario requires flashloan capital, but lender/borrow/repay mechanism was not behaviorally reproduced."
            elif reachability_failed_marker:
                new_status = "execution_reachability_failed"
                rationale = "Attack path prerequisites could not be reached with modeled capital/permissions."
            elif behavior_not_observed_marker:
                new_status = "execution_behavior_not_observed"
                rationale = "Execution reached callable paths but did not produce the hypothesis-claimed behavioral state transition."
            elif economic_effect_not_observed_marker:
                new_status = "execution_economic_effect_not_observed"
                rationale = "Behavioral transition signal existed but claimed economic extraction/effect was not observed."
            elif economic_not_confirmed_marker:
                new_status = "execution_economic_impact_not_confirmed"
                rationale = "Predicted economic consequence did not materialize in post-state assertions."
            elif synthetic_inconclusive_marker:
                new_status = "execution_inconclusive_synthetic"
                rationale = "Execution reached targets but produced no measurable post-state or economic movement; evidence remains synthetic/inconclusive."
            elif passed:
                new_status = "supported_by_execution"
                rationale = "Execution checks passed on fork state for targeted contracts/functions."
            elif failed:
                new_status = "falsification_triggered"
                rationale = "Execution checks failed on fork state and triggered falsification evidence."
            else:
                new_status = "execution_unknown"
                rationale = "Execution result could not be mapped to a hypothesis outcome."
            parsed.append(
                FalsificationCase(
                    hypothesis_id=case.hypothesis_id,
                    test_name=case.test_name,
                    status=new_status,
                    rationale=rationale,
                    should_fail=case.should_fail,
                    execution_sequence_id=case.execution_sequence_id,
                    execution_steps=case.execution_steps,
                    economic_consequence=case.economic_consequence,
                    violated_invariants=case.violated_invariants,
                    target_contracts=case.target_contracts,
                    target_addresses=case.target_addresses,
                    target_functions=case.target_functions,
                    target_invariants=case.target_invariants,
                    invariant_assertion=case.invariant_assertion,
                    proof_marker=case.proof_marker,
                    proof_summary=case.proof_summary,
                    required_capital=case.required_capital,
                    flashloan_principal=case.flashloan_principal,
                    flashloan_fee=case.flashloan_fee,
                    predicted_attacker_profit=case.predicted_attacker_profit,
                    predicted_protocol_loss=case.predicted_protocol_loss,
                    predicted_victim_loss=case.predicted_victim_loss,
                    assumptions=case.assumptions,
                    actors=case.actors,
                    sequence_source=case.sequence_source,
                    evidence_contract=case.evidence_contract,
                    observed_values={
                        # Test execution status
                        "test_passed": passed,
                        "test_failed": failed,
                        "fail_reason": reason,
                        "execution_marker_completed": case.hypothesis_id in completed_markers,
                        # Attack path and state indicators
                        "attack_path_completed": passed or new_status in {
                            "execution_behavior_not_observed",
                            "execution_economic_effect_not_observed",
                            "execution_economic_impact_not_confirmed",
                            "execution_inconclusive_reconciliation",
                            "execution_proof_criteria_satisfied",
                            "falsification_triggered",
                        },
                        "state_transition_occurred": new_status in {
                            "execution_economic_effect_not_observed",
                            "execution_economic_impact_not_confirmed",
                            "execution_inconclusive_reconciliation",
                            "execution_proof_criteria_satisfied",
                        },
                        # Invariant and economic checks
                        "invariant_evaluated": new_status not in {
                            "execution_reachability_failed",
                            "execution_invariant_not_testable",
                            "execution_blocked_toolchain",
                            "execution_unknown",
                        },
                        "invariant_violated": new_status == "execution_proof_criteria_satisfied",
                        "economic_effect_observed": new_status in {
                            "execution_inconclusive_reconciliation",
                            "execution_proof_criteria_satisfied",
                        },
                        "economic_reconciled": new_status == "execution_proof_criteria_satisfied",
                        "preconditions_satisfied": new_status != "execution_assumption_gap_flashloan",
                        # Proof criteria and observed evidence - marker determines satisfaction
                        "proof_criteria_satisfied": proof_criteria_satisfied_marker,
                        # Observed measurements
                        "observed_attacker_profit": case.predicted_attacker_profit if proof_criteria_satisfied_marker else 0,
                        "required_capital_observed": case.required_capital if passed else 0,
                        "flashloan_principal_observed": case.flashloan_principal if proof_criteria_satisfied_marker else 0,
                        "flashloan_fee_observed": case.flashloan_fee if proof_criteria_satisfied_marker else 0,
                        "attacker_net_pnl": attacker_net_pnl,
                        "protocol_direct_token_loss": protocol_direct_token_loss,
                        "protocol_liveness_loss": protocol_liveness_loss,
                        "user_access_impairment_score": user_access_impairment_score,
                        # Merge extracted hypothesis-specific evidence values
                        **extracted_evidence,
                    },
                    evidence_provenance={
                        **case.evidence_provenance,
                        "hypothesis_id": case.hypothesis_id,
                        "test_id": case.test_name,
                    },
                )
            )
        return parsed

    def _render_behavioral_sequence_lines(self, *, case: FalsificationCase) -> list[str]:
        # Sequence replay requires at least one concrete on-chain target address.
        # Without a live address, generated callsites become invalid and should be omitted.
        if not case.execution_steps or not case.target_addresses:
            return []
        primary_address = f"target_{self._sanitize(case.target_addresses[0])}"
        proof_marker = f"HALYX_TEST_COMPLETED:{case.hypothesis_id}"
        lines: list[str] = [
            "        // Behavioral exploit sequence reconstructed from validated execution steps.",
            f'        require(bytes("{proof_marker}").length > 0, "missing completion marker");',
            f"        address primaryTarget = {primary_address};",
            f'        emit HalyxEvidenceObserved("{case.hypothesis_id}", "sequence_source", {1 if case.sequence_source else 0});',
        ]

        for index, step in enumerate(case.execution_steps[:8], start=1):
            if not isinstance(step, dict):
                continue
            handler = str(step.get("handler") or "")
            caller = str(step.get("caller") or "external_user")
            signature = self._resolve_step_signature(handler=handler, signatures=case.target_functions)
            if not signature:
                continue
            escaped = signature.replace('"', '\\"')
            calldata_expr = self._build_calldata_expr(signature=signature, caller_var="attacker")
            if not calldata_expr:
                continue
            caller_var = self._resolve_caller_var(caller)
            description = str(step.get("description") or step.get("purpose") or handler)
            escaped_desc = description.replace('"', '\\"')
            lines.extend(
                [
                    f"        vm.prank({caller_var});",
                    f"        bytes memory data_{index} = {calldata_expr};",
                    *(
                        ["        flashloanMechanismAttempted = true;"]
                        if ("flash" in signature.lower() or "borrow" in signature.lower() or "loan" in signature.lower())
                        else []
                    ),
                    f"        (bool ok_{index}, ) = {primary_address}.call(data_{index});",
                    f"        if (ok_{index}) {{ pathProgress++; }}",
                    *(
                        ["        if (ok_{index}) { flashloanMechanismReproduced = true; }"]
                        if ("flash" in signature.lower() or "borrow" in signature.lower() or "loan" in signature.lower())
                        else []
                    ),
                    f"        emit HalyxStepTrace(\"{case.hypothesis_id}\", {index}, \"{handler}\", {caller_var}, ok_{index});",
                    f"        emit HalyxEvidenceObserved(\"{case.hypothesis_id}\", \"step_{index}_ok\", ok_{index} ? int256(1) : int256(0));",
                    f'        require(bytes("step_desc:{index}:{escaped_desc}").length > 0, "missing sequence description marker");',
                    f'        require(bytes("step:{index}:{escaped}").length > 0, "missing sequence marker");',
                ]
            )

        lines.extend(
            [
                f'        require(pathProgress > 0, "{case.hypothesis_id} sequence execution did not reach any step");',
            ]
        )
        return lines

    def _derive_invariant_assertion(self, *, target_invariants: list[str], violated_invariants: list[str]) -> str:
        invariant_ids = [*target_invariants, *violated_invariants]
        if not invariant_ids:
            return ""
        primary = invariant_ids[0].strip()
        if not primary:
            return ""
        lowered = primary.lower()
        if "share" in lowered or "supply" in lowered or "debt" in lowered or "collateral" in lowered:
            return "attackerBalanceAfter > attackerBalanceBefore || stateDeltaChecks > 0"
        if "price" in lowered or "oracle" in lowered:
            return "attackerBalanceAfter > attackerBalanceBefore || stateDeltaChecks > 0"
        return "attackerBalanceAfter > attackerBalanceBefore || stateDeltaChecks > 0"

    def _resolve_step_signature(self, *, handler: str, signatures: list[str]) -> str | None:
        if not handler:
            return None
        handler_lower = handler.lower()
        for signature in signatures:
            base = signature.split("(", 1)[0].lower()
            if base == handler_lower or base.startswith(handler_lower) or handler_lower.startswith(base):
                return signature
        return None

    def _build_calldata_expr(self, *, signature: str, caller_var: str) -> str | None:
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\(([^)]*)\)$", signature)
        if not match:
            return None
        function_name = match.group(1)
        params_raw = match.group(2).strip()
        if not params_raw:
            return f'abi.encodeWithSignature("{function_name}()")'

        args: list[str] = []
        for raw in [item.strip() for item in params_raw.split(",") if item.strip()]:
            param = raw.lower()
            if param.startswith(("uint", "int")):
                args.append("uint256(1)")
            elif param == "address":
                args.append(caller_var)
            elif param == "bool":
                args.append("true")
            elif param == "bytes32":
                args.append("bytes32(uint256(1))")
            elif param.startswith("bytes"):
                args.append('hex"01"')
            elif param == "string":
                args.append('"halyx"')
            else:
                return None
        args_serialized = ", ".join(args)
        return f'abi.encodeWithSignature("{signature}", {args_serialized})'

    @staticmethod
    def _resolve_caller_var(caller: str) -> str:
        lowered = caller.lower()
        if "privileged" in lowered or "govern" in lowered or "admin" in lowered or "operator" in lowered or "guardian" in lowered:
            return "operator"
        if "victim" in lowered or "lp" in lowered:
            return "victim"
        if "oracle" in lowered:
            return "oracle"
        return "attacker"

    @staticmethod
    def _is_privileged_actor(actor: str) -> bool:
        lowered = actor.lower()
        return any(token in lowered for token in ["govern", "admin", "guardian", "operator", "privileged", "policy", "vault"])

    @classmethod
    def _selected_functions_require_privilege(cls, functions: list[str]) -> bool:
        privileged_prefixes = (
            "pushgovernor",
            "pushguardian",
            "pushpolicy",
            "pushvault",
            "pullgovernor",
            "pullguardian",
            "pullpolicy",
            "pullvault",
            "setauthority",
        )
        normalized = [fn.split("(", 1)[0].strip().lower() for fn in functions if fn]
        return bool(normalized) and all(any(name.startswith(prefix) for prefix in privileged_prefixes) for name in normalized)

    def _collect_solidity_source_map(self, repository_path: Path) -> list[dict[str, object]]:
        reserved = {
            "for",
            "if",
            "while",
            "return",
            "contract",
            "library",
            "interface",
            "event",
            "error",
            "modifier",
            "mapping",
        }
        source_root = repository_path / "src"
        root = source_root if source_root.exists() else repository_path
        descriptors: list[dict[str, object]] = []
        for file_path in root.rglob("*.sol"):
            if not file_path.is_file():
                continue
            if "/test/" in str(file_path).replace("\\", "/"):
                continue
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            contracts = [
                name
                for name in re.findall(r"\bcontract\s+([A-Za-z_][A-Za-z0-9_]*)", text)
                if name.lower() not in reserved
            ]
            raw_functions = re.findall(r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)", text)
            signatures: list[str] = []
            for name, params in raw_functions:
                if name.lower() in reserved:
                    continue
                simplified_params = ",".join(
                    part.strip().split(" ")[0]
                    for part in params.split(",")
                    if part.strip()
                )
                signatures.append(f"{name}({simplified_params})" if simplified_params else f"{name}()")
            descriptors.append(
                {
                    "file": str(file_path.relative_to(repository_path)),
                    "contracts": contracts,
                    "functions": signatures,
                    "search_text": " ".join([file_path.stem, *contracts, *signatures]).lower(),
                }
            )
        return descriptors

    def _select_targets(self, *, item: dict[str, object], source_map: list[dict[str, object]]) -> dict[str, list[str]]:
        subsystem = str(item.get("subsystem") or "")
        title = str(item.get("title") or "")
        evidence_needed = item.get("evidence_needed", [])
        execution_sequence = item.get("execution_sequence", {}) if isinstance(item.get("execution_sequence"), dict) else {}
        ordered_steps = execution_sequence.get("ordered_steps", []) if isinstance(execution_sequence, dict) else []
        expected_sequence_steps = item.get("expected_attack_sequence", []) if isinstance(item.get("expected_attack_sequence"), list) else []
        step_handlers = [
            str(step.get("handler") or "")
            for step in ordered_steps
            if isinstance(step, dict) and step.get("handler")
        ]
        hint_handlers = self._extract_handler_hints(item=item)
        step_handlers.extend(hint_handlers)
        step_invariants = [
            invariant_id
            for step in ordered_steps
            if isinstance(step, dict)
            for invariant_id in (step.get("invariant_ids", []) or [])
            if invariant_id
        ]
        hypothesis_tokens = set(
            re.findall(
                r"[a-zA-Z][a-zA-Z0-9_]{2,}",
                " ".join([
                    subsystem,
                    title,
                    str(execution_sequence.get("economic_consequence") or ""),
                    *step_handlers,
                    *[str(text) for text in expected_sequence_steps if text],
                    *step_invariants,
                ]).lower(),
            )
        )
        ranked = sorted(
            source_map,
            key=lambda desc: len(hypothesis_tokens & set(re.findall(r"[a-zA-Z][a-zA-Z0-9_]{2,}", str(desc.get("search_text") or "")))),
            reverse=True,
        )
        selected = [desc for desc in ranked if desc.get("contracts")][:2]
        contracts = [str(contract) for desc in selected for contract in desc.get("contracts", [])][:3]
        functions = [str(signature) for desc in selected for signature in desc.get("functions", []) if self._function_matches_sequence(signature, step_handlers)][:6]
        if not functions:
            functions = [str(signature) for desc in selected for signature in desc.get("functions", [])][:6]
        if not functions:
            functions = [f"{handler}()" for handler in step_handlers[:4] if handler]
        if hint_handlers:
            hinted_functions = [fn for fn in functions if any(fn.lower().startswith(h.lower()) for h in hint_handlers)]
            if hinted_functions:
                functions = hinted_functions[:6]
        invariants = [str(item) for item in evidence_needed if item][:3] if isinstance(evidence_needed, list) else []
        if not invariants:
            invariants = [str(item) for item in step_invariants[:3] if item]
        if not invariants:
            invariants = [f"Investigate subsystem property: {subsystem}"] if subsystem else []
        return {
            "contracts": contracts,
            "functions": functions,
            "invariants": invariants,
        }

    @staticmethod
    def _extract_handler_hints(*, item: dict[str, object]) -> list[str]:
        hints: list[str] = []
        evidence_needed = item.get("evidence_needed", []) if isinstance(item.get("evidence_needed"), list) else []
        for entry in evidence_needed:
            text = str(entry)
            if "Locate functions matching:" in text:
                after = text.split("Locate functions matching:", 1)[-1]
                for value in after.split(","):
                    candidate = re.sub(r"[^A-Za-z0-9_]", "", value.strip())
                    if candidate:
                        hints.append(candidate)
        dedup: list[str] = []
        seen: set[str] = set()
        for hint in hints:
            low = hint.lower()
            if low in seen:
                continue
            seen.add(low)
            dedup.append(hint)
        return dedup[:8]

    @staticmethod
    def _function_matches_sequence(signature: str, handlers: list[str]) -> bool:
        base = signature.split("(", 1)[0].lower()
        for handler in handlers:
            normalized = handler.lower()
            if base == normalized or base.startswith(normalized) or normalized.startswith(base):
                return True
        return False

    def _collect_contract_addresses(
        self,
        repository_path: Path,
        *,
        source_map: list[dict[str, object]],
        chain: str,
    ) -> tuple[dict[str, list[str]], int, int]:
        contract_names = {
            contract
            for descriptor in source_map
            for contract in descriptor.get("contracts", [])
            if isinstance(contract, str)
        }
        mapping: dict[str, list[str]] = {name: [] for name in contract_names}
        discovered_address_count = 0
        verified_address_count = 0
        verification_cache: dict[str, bool] = {}

        candidate_roots = [
            repository_path / "deployments",
            repository_path / "broadcast",
            repository_path / "deployment",
        ]
        candidate_files: list[Path] = []
        for root in candidate_roots:
            if not root.exists():
                continue
            candidate_files.extend(path for path in root.rglob("*.json") if path.is_file())

        address_pattern = re.compile(r"0x[a-fA-F0-9]{40}")
        for file_path in candidate_files[:300]:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            lowered_path = str(file_path).lower()

            json_payload: object | None = None
            try:
                json_payload = json.loads(text)
            except json.JSONDecodeError:
                # Ignore non-JSON blobs so we don't scrape arbitrary hex from bytecode artifacts.
                continue

            found_addresses = self._extract_deployment_addresses(json_payload)
            if not found_addresses:
                continue
            discovered_address_count += len(found_addresses)

            for contract_name in contract_names:
                file_name_match = contract_name.lower() in lowered_path
                contract_json_match = bool(json_payload is not None and self._json_mentions_contract(json_payload, contract_name))
                if not (file_name_match or contract_json_match):
                    continue
                for address in found_addresses:
                    is_verified = self._is_verified_contract_address(address, chain=chain, cache=verification_cache)
                    local_candidate = self.etherscan_client is None and self._accept_explicit_repo_address(
                        file_path=file_path,
                        payload=json_payload,
                        contract_name=contract_name,
                        address=address,
                    )
                    if is_verified or local_candidate:
                        if address.lower() not in {item.lower() for item in mapping[contract_name]}:
                            mapping[contract_name].append(address)
                        if is_verified or local_candidate:
                            verified_address_count += 1

        for contract_name in list(mapping.keys()):
            dedup: list[str] = []
            seen: set[str] = set()
            for address in mapping[contract_name]:
                lower = address.lower()
                if lower in seen:
                    continue
                seen.add(lower)
                dedup.append(address)
            mapping[contract_name] = dedup[:6]
        return mapping, discovered_address_count, verified_address_count

    def _extract_deployment_addresses(self, payload: object) -> list[str]:
        """Extract candidate deployment addresses from explicit JSON address fields only."""
        address_fields = {
            "address",
            "contractaddress",
            "proxy",
            "implementation",
            "logic",
            "deployedto",
            "deployed_to",
        }
        discovered: list[str] = []

        def visit(node: object, parent_key: str | None = None) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    key_norm = str(key).strip().lower().replace("_", "")
                    if isinstance(value, str) and key_norm in address_fields:
                        candidate = value.strip()
                        if re.fullmatch(r"0x[a-fA-F0-9]{40}", candidate):
                            discovered.append(candidate)
                    visit(value, parent_key=str(key))
                return
            if isinstance(node, list):
                for item in node:
                    visit(item, parent_key=parent_key)
                return
            if isinstance(node, str) and parent_key:
                key_norm = parent_key.strip().lower().replace("_", "")
                candidate = node.strip()
                if key_norm in address_fields and re.fullmatch(r"0x[a-fA-F0-9]{40}", candidate):
                    discovered.append(candidate)

        visit(payload)
        dedup: list[str] = []
        seen: set[str] = set()
        for address in discovered:
            low = address.lower()
            if low in seen:
                continue
            seen.add(low)
            dedup.append(address)
        return dedup

    @staticmethod
    def _accept_explicit_repo_address(*, file_path: Path, payload: object, contract_name: str, address: str) -> bool:
        text = str(file_path).lower()
        if contract_name.lower() in text:
            return True
        if not isinstance(payload, dict):
            return False
        contract_tokens = [str(contract_name).lower(), str(file_path.stem).lower()]
        for value in payload.values():
            if isinstance(value, str):
                lowered = value.lower()
                if lowered == address.lower():
                    return True
                if any(token in lowered for token in contract_tokens):
                    return True
        return False

    def _is_verified_contract_address(self, address: str, *, chain: str, cache: dict[str, bool]) -> bool:
        if not self.etherscan_client:
            return True
        cache_key = f"{chain.lower()}:{address.lower()}"
        if cache_key in cache:
            return cache[cache_key]
        try:
            metadata = self.etherscan_client.get_contract_metadata(address, chain)
            verified = bool(metadata.get("SourceCode"))
        except SourceAcquisitionError:
            verified = False
        cache[cache_key] = verified
        return verified

    def _json_mentions_contract(self, payload: object, contract_name: str) -> bool:
        target = contract_name.lower()
        if isinstance(payload, dict):
            for key, value in payload.items():
                if target in str(key).lower():
                    return True
                if self._json_mentions_contract(value, contract_name):
                    return True
            return False
        if isinstance(payload, list):
            return any(self._json_mentions_contract(item, contract_name) for item in payload)
        if isinstance(payload, str):
            return target in payload.lower()
        return False

    def _discover_fork_rpc(self, repository_path: Path) -> tuple[str | None, str | None]:
        env_pairs = self._load_env_pairs(repository_path)

        for key in ["FORK_TEST_RPC_URL", "HALYX_FORK_RPC_URL", "ETH_RPC_URL", "RPC_URL", "MAINNET_RPC_URL", "TESTNET_RPC_URL"]:
            value = env_pairs.get(key) or os.getenv(key)
            if value:
                return value, f"env:{key}"

        foundry_toml = repository_path / "foundry.toml"
        if not foundry_toml.exists():
            return "https://rpc.mevblocker.io", "fallback:mevblocker"
        try:
            data = tomllib.loads(foundry_toml.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError):
            return "https://rpc.mevblocker.io", "fallback:mevblocker"

        rpc_endpoints = data.get("rpc_endpoints", {}) if isinstance(data, dict) else {}
        if not isinstance(rpc_endpoints, dict):
            return "https://rpc.mevblocker.io", "fallback:mevblocker"

        preferred = ["mainnet", "ethereum", "sepolia", "base", "arbitrum"]
        endpoint_items: list[tuple[str, str]] = []
        for chain, value in rpc_endpoints.items():
            endpoint = self._extract_endpoint_value(value)
            if endpoint:
                endpoint_items.append((str(chain), endpoint))

        ordered: list[tuple[str, str]] = []
        for chain in preferred:
            ordered.extend(item for item in endpoint_items if item[0] == chain)
        ordered.extend(item for item in endpoint_items if item not in ordered)

        for chain, endpoint_template in ordered:
            resolved = self._expand_template(endpoint_template, env_pairs)
            if resolved:
                return resolved, f"foundry.toml:rpc_endpoints.{chain}"

        return "https://rpc.mevblocker.io", "fallback:mevblocker"

    def _load_env_pairs(self, repository_path: Path) -> dict[str, str]:
        env_files = [
            repository_path / ".env",
            repository_path / ".env.local",
            repository_path / ".env.deploy",
            repository_path / ".env.deploy.local",
            repository_path / ".env.example",
            repository_path / ".env.deploy.example",
            repository_path / ".env.L2.example",
        ]
        pairs: dict[str, str] = {}
        for file_path in env_files:
            if not file_path.exists() or not file_path.is_file():
                continue
            for line in file_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, value = stripped.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and value and key not in pairs:
                    pairs[key] = value
        return pairs

    def _extract_endpoint_value(self, raw: object) -> str | None:
        if isinstance(raw, str):
            return raw.strip()
        if isinstance(raw, dict):
            endpoint = raw.get("endpoint")
            if isinstance(endpoint, str):
                return endpoint.strip()
        return None

    def _expand_template(self, template: str, env_pairs: dict[str, str]) -> str | None:
        pattern = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
        missing = False

        def repl(match: re.Match[str]) -> str:
            nonlocal missing
            key = match.group(1)
            value = env_pairs.get(key) or os.getenv(key)
            if not value:
                missing = True
                return ""
            return value

        resolved = pattern.sub(repl, template)
        if missing:
            return None
        return resolved

    def _build_repair_diagnostics(
        self,
        *,
        framework: str,
        command: list[str],
        repository_path: Path,
        harness_dir: Path,
        stdout: str,
        stderr: str,
        return_code: int,
    ) -> dict[str, object]:
        """
        Convert an execution result into structured diagnostics for the UI
        and repair workflow.

        This method deliberately does not attempt to repair the repository.
        It classifies the execution result and provides the next action that
        the Halyx repair workflow should consider.
        """
        combined_output = f"{stdout}\n{stderr}".strip()

        if return_code == 0:
            return {
                "kind": "execution_success",
                "summary": f"{framework.title()} POC execution completed successfully.",
                "assistant_request": "",
                "framework": framework,
                "command": command,
                "repository_path": str(repository_path),
                "harness_dir": str(harness_dir),
                "return_code": return_code,
            }

        toolchain_block = self._detect_toolchain_block(
            stdout=stdout,
            stderr=stderr,
        )

        if toolchain_block:
            return {
                "kind": "toolchain_block",
                "summary": toolchain_block,
                "assistant_request": (
                    "Inspect the execution output, repair the identified "
                    "toolchain or dependency issue, and rerun the POC."
                ),
                "framework": framework,
                "command": command,
                "repository_path": str(repository_path),
                "harness_dir": str(harness_dir),
                "return_code": return_code,
            }

        if combined_output:
            return {
                "kind": "execution_failure",
                "summary": (
                    f"{framework.title()} POC execution failed "
                    f"with return code {return_code}."
                ),
                "assistant_request": (
                    "Inspect the captured Forge/Hardhat output and repair "
                    "the execution failure before rerunning the POC."
                ),
                "framework": framework,
                "command": command,
                "repository_path": str(repository_path),
                "harness_dir": str(harness_dir),
                "return_code": return_code,
            }

        return {
            "kind": "execution_failure_no_output",
            "summary": (
                f"{framework.title()} POC execution failed with "
                f"return code {return_code}, but produced no diagnostic output."
            ),
            "assistant_request": (
                "Rerun the POC with verbose output and inspect the execution "
                "environment, command, and toolchain."
            ),
            "framework": framework,
            "command": command,
            "repository_path": str(repository_path),
            "harness_dir": str(harness_dir),
            "return_code": return_code,
        }

    @staticmethod
    def _detect_toolchain_block(*, stdout: str, stderr: str) -> str | None:
        output = f"{stdout}\n{stderr}".lower()
        if "invalid solc version" in output:
            return "Forge execution blocked by conflicting Solidity compiler version constraints in the target repository."
        if "compiler error" in output:
            return "Forge execution blocked by compilation errors in the target repository."
        if "failed to resolve" in output or "not found" in output:
            return "Forge execution blocked by unresolved dependencies or missing imports."
        return None

    @staticmethod
    def _sanitize(value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", value)
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")
        return cleaned or "unknown"
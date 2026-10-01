// ── Assistant ────────────────────────────────────────────────────────────────

function assistantAddMessage(role, text) {
  const container = document.getElementById("assistant-messages");
  if (!container) return;
  const row = document.createElement("div");
  row.className = `assistant-msg assistant-msg-${role}`;
  row.textContent = text;
  container.appendChild(row);
  container.scrollTop = container.scrollHeight;
}

async function assistantSend(message, context) {
  if (!message.trim()) return;
  assistantAddMessage("user", message);
  try {
    const body = { message, context: context || null, run_id: state.selectedRunId || null };
    const response = await fetch("/api/assistant/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    assistantAddMessage("assistant", data.reply || "No reply from assistant.");
  } catch (err) {
    assistantAddMessage("assistant", `Request failed: ${err.message}`);
  }
}

function assistantOpenWithError(errorText) {
  const panel = document.getElementById("assistant-panel");
  if (panel) panel.classList.add("assistant-open");
  assistantAddMessage("assistant", `An error occurred. Here is what I can tell you:\n${errorText}`);
  assistantSend(errorText, "automatic_error_escalation");
}

document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.getElementById("assistant-toggle");
  const panel = document.getElementById("assistant-panel");
  const closeBtn = document.getElementById("assistant-close");
  const form = document.getElementById("assistant-form");
  const input = document.getElementById("assistant-input");

  toggle?.addEventListener("click", () => panel?.classList.toggle("assistant-open"));
  closeBtn?.addEventListener("click", () => panel?.classList.remove("assistant-open"));

  form?.addEventListener("submit", (e) => {
    e.preventDefault();
    const msg = (input?.value || "").trim();
    if (!msg) return;
    if (input) input.value = "";
    assistantSend(msg, null);
  });

  // Drag support for the assistant panel.
  const handle = document.getElementById("assistant-drag-handle");
  if (handle && panel) {
    let dragging = false, ox = 0, oy = 0;
    handle.addEventListener("mousedown", (e) => {
      dragging = true;
      const rect = panel.getBoundingClientRect();
      ox = e.clientX - rect.left;
      oy = e.clientY - rect.top;
      e.preventDefault();
    });
    document.addEventListener("mousemove", (e) => {
      if (!dragging) return;
      panel.style.left = `${e.clientX - ox}px`;
      panel.style.top = `${e.clientY - oy}px`;
      panel.style.right = "auto";
      panel.style.bottom = "auto";
    });
    document.addEventListener("mouseup", () => { dragging = false; });
  }
});

const state = {
  dashboard: null,
  activeMainPanel: "summary",
  activeSidePanel: "inspect",
  selectedArtifact: null,
  selectedRunId: null,
  selectedFilePath: null,
  lastPocResult: null,
  runs: [],
};

const shorten = (value, max = 240) => {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1)}...`;
};

const formatPercent = (value) => `${Math.round((value || 0) * 100)}%`;

const formatNumber = (value, digits = 2) => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return Number(value).toFixed(digits);
};

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) {
    element.textContent = value;
  }
}

function selectMainPanel(name) {
  state.activeMainPanel = name;
  document.querySelectorAll("[data-main-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.mainTab === name);
  });
  document.querySelectorAll("[data-main-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.mainPanel === name);
  });
}

function selectSidePanel(name) {
  state.activeSidePanel = name;
  document.querySelectorAll("[data-side-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.sideTab === name);
  });
  document.querySelectorAll("[data-side-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.sidePanel === name);
  });
}

function renderStages(data) {
  const container = document.getElementById("stage-stream");
  if (!container) return;
  const phases = data?.methodology?.phases || [];
  container.innerHTML = phases.length
    ? phases.map((phase) => `
      <div class="stage-row">
        <strong>${phase.name}</strong>
        <div class="stage-state">${phase.status}</div>
        <div class="muted">${shorten(phase.summary, 260)}</div>
      </div>
    `).join("")
    : `<div class="stage-row"><strong>Pipeline idle</strong><div class="muted">No run artifact is available yet.</div></div>`;
}

function renderCoverage(data) {
  const container = document.getElementById("coverage-list");
  if (!container) return;
  const subsystems = data?.subsystems || [];
  container.innerHTML = subsystems.length
    ? subsystems.map((subsystem) => {
        const invariantCount = subsystem.invariants?.length || 0;
        const traceCount = subsystem.implementation_traces?.length || 0;
        const coverageScore = Math.min(1, 0.45 + 0.1 * invariantCount + 0.12 * traceCount + 0.15 * (subsystem.evidence_quality?.evidence_coverage || 0));
        return `
          <div class="coverage-row">
            <div>
              <strong>${subsystem.name}</strong>
              <div class="muted">Guarantees ${subsystem.guarantees?.length || 0} • Invariants ${invariantCount} • Traces ${traceCount}</div>
            </div>
            <div class="progress">${formatPercent(coverageScore)}</div>
          </div>
        `;
      }).join("")
    : `<div class="coverage-row"><strong>No subsystem dossier yet</strong><div class="progress">—</div></div>`;
}

function renderTutor(data) {
  const container = document.getElementById("tutor-stream");
  if (!container) return;
  const notes = data?.tutor_research || [];
  const verification = data?.verification_reports || [];
  const verificationBySubsystem = new Map(
    verification.map((item) => [String(item.subsystem || item.concept || "").toLowerCase(), item])
  );
  container.innerHTML = notes.length
    ? notes.map((note) => {
        const report = verificationBySubsystem.get(String(note.subsystem || note.concept || "").toLowerCase());
        return `
      <div class="list-item">
        <strong>${note.concept}</strong>
        <div class="muted">${note.summary}</div>
        <div class="muted">${note.verified ? "Verified" : "Pending verification"} • ${note.provider} • confidence ${formatPercent(note.confidence || 0)}</div>
        <div class="muted">Verification score: ${report ? formatPercent(report.verification_score || 0) : "n/a"}</div>
        <div class="muted">${report ? report.rationale : "No deterministic verification report yet."}</div>
      </div>
    `;
      }).join("")
    : `<div class="list-item"><strong>No tutor research yet</strong><div class="muted">The Tutor activates when the planner finds a knowledge gap.</div></div>`;
}

function renderHypotheses(data) {
  const container = document.getElementById("hypothesis-list");
  if (!container) return;
  const items = data?.research_hypotheses || [];
  container.innerHTML = items.length
    ? items.map((item) => `
      <div class="list-item">
        <strong>${item.title || item.hypothesis_id}</strong>
        <div class="muted">${item.missing_subsystem || "Unknown subsystem gap"}</div>
      </div>
    `).join("")
    : `<div class="list-item"><strong>No hypotheses</strong><div class="muted">Hypotheses appear after pattern recognition and planning.</div></div>`;
}

function renderHypothesisTrace(data) {
  const container = document.getElementById("hypothesis-trace-list");
  const summary = document.getElementById("falsification-execution-summary");
  if (!container) return;
  const execution = data?.falsification_execution || {};
  if (summary) {
    const commandText = (execution.command || []).join(" ") || "n/a";
    const hasGeneratedTest = Boolean(execution.generated_test_file);
    const cases = execution.cases || [];
    const supported = cases.filter((item) => item?.status === "supported_by_execution" || item?.status === "exploit_sequence_confirmed").length;
    const disproved = cases.filter((item) => item?.status === "falsification_triggered").length;
    const unknown = cases.filter((item) => item?.status !== "supported_by_execution" && item?.status !== "exploit_sequence_confirmed" && item?.status !== "falsification_triggered").length;
    const returnCode = execution.return_code;
    const harnessVerdict = returnCode === 0
      ? "Harness verdict: PASS (forge returned 0)."
      : `Harness verdict: FAIL (forge returned ${returnCode === null || returnCode === undefined ? "n/a" : returnCode}).`;
    const hypothesisOutcomes = data?.hypothesis_outcomes || {};
    const falsificationSummary = data?.falsification_summary || {};
    summary.innerHTML = `
      <strong>Execution Harness</strong>
      <p class="muted">Mode: ${execution.mode || "n/a"} • Executed: ${execution.executed ? "yes" : "no"} • Cases: ${(execution.cases || []).length}</p>
      <p class="muted">Fork RPC source: ${execution.fork_rpc_source || "n/a"}</p>
      <p class="muted">Harness path: ${execution.harness_dir || "n/a"}</p>
      <p class="muted">Generated test: ${execution.generated_test_file || "n/a"}</p>
      <p class="muted">Command: ${commandText}</p>
      <p class="muted">Return code: ${execution.return_code === null || execution.return_code === undefined ? "n/a" : execution.return_code} • Passed: ${execution.passed === null || execution.passed === undefined ? "n/a" : (execution.passed ? "yes" : "no")}</p>
      <p class="muted">${harnessVerdict}</p>
      <p class="muted">Case outcomes: supported ${supported}, falsified ${disproved}, unresolved ${unknown}.</p>
      <p class="muted">Hypothesis outcomes: supported ${hypothesisOutcomes.supported || 0}, disproved ${hypothesisOutcomes.disproved || 0}, unresolved ${hypothesisOutcomes.unresolved || 0}.</p>
      <p class="muted">Foundry summary: ${falsificationSummary.summary || "No Foundry summary recorded."}</p>
      <p class="muted">Reason: ${execution.reason || "none"}</p>
      <p class="muted">POC file access: ${hasGeneratedTest ? "Use File Tree -> Open Generated Foundry Test" : "No generated test was recorded for this run."}</p>
    `;
  }

  const trace = data?.hypothesis_trace || data?.hypothesis_evidence_ledger || [];
  container.innerHTML = trace.length
    ? trace.map((item) => {
        const sequence = item.execution_sequence || {};
        const steps = sequence.ordered_steps || [];
        const validation = sequence.validation || {};
        const coverage = sequence.coverage || {};
        const sequenceSummary = sequence.sequence_id
          ? `<div class="muted">Sequence: ${sequence.sequence_id} • Valid: ${validation.is_valid ? "yes" : "no"} • Step count: ${steps.length}</div>`
          : `<div class="muted">No execution sequence reconstructed.</div>`;
        const stepFlow = steps.length
          ? `<div class="muted">Flow: ${steps.map((step) => `${step.index}. ${step.handler || step.description}`).join(" -> ")}</div>`
          : "";
        const stateFlow = steps.length
          ? `<div class="muted">States: ${steps.map((step) => `${step.from_state || "?"}→${step.to_state || "?"}`).join(" | ")}</div>`
          : "";
        const coverageLine = sequence.sequence_id
          ? `<div class="muted">Coverage: ${formatPercent(coverage.coverage_ratio || 0)} • Handlers ${coverage.handlers_reconstructed || 0} • Variables ${coverage.state_variables_modeled || 0} • Reachable transitions ${coverage.reachable_transitions || 0}</div>`
          : "";
        const validationLine = validation.reasons?.length
          ? `<div class="muted">Validation: ${validation.reasons.join(" | ")}</div>`
          : `<div class="muted">Validation: simulator ${validation.simulator_success ? "succeeded" : "not run"} • completeness ${formatPercent(validation.completeness_ratio || 0)} • transition validity ${formatPercent(validation.transition_validity_ratio || 0)}</div>`;
        return `
      <div class="list-item">
        <strong>${item.title || item.hypothesis_id}</strong>
        <div class="muted">Subsystem: ${item.subsystem || "unknown"}</div>
        <div class="muted">State: ${item.status}</div>
        <div class="muted">Final confidence: ${formatPercent(item.final_confidence || 0)}</div>
        <div class="muted">Proof attempts: ${(item.proof_attempts || []).length} • Falsification attempts: ${(item.falsification_attempts || []).length}</div>
        <div class="muted">Trajectory: ${(item.confidence_trajectory || []).map((event) => `${event.stage}(${event.delta > 0 ? "+" : ""}${formatNumber(event.delta || 0, 2)})`).join(" -> ") || "none"}</div>
        <div class="muted">Execution case: ${item.execution_case?.status || "not executed"} ${item.execution_case?.test_name ? `(${item.execution_case.test_name})` : ""}</div>
        <div class="muted">Hypothesis result: ${item.status || "untested"}</div>
        <div class="muted">Execution rationale: ${item.execution_case?.rationale || "n/a"}</div>
        <div class="muted">Proof marker: ${item.execution_case?.proof_marker || "none"}</div>
        <div class="muted">Invariant assertion: ${item.execution_case?.invariant_assertion || "none"}</div>
        <div class="muted">Proof summary: ${item.execution_case?.proof_summary || "No replay proof emitted."}</div>
        <div class="muted">Execution steps exercised: ${(item.execution_case?.execution_steps || []).length}</div>
        <div class="muted">Target contracts: ${(item.execution_case?.target_contracts || []).join(", ") || "none"}</div>
        <div class="muted">Target addresses: ${(item.execution_case?.target_addresses || []).join(", ") || "none"}</div>
        <div class="muted">Target functions: ${(item.execution_case?.target_functions || []).join(", ") || "none"}</div>
        <div class="muted">Target invariants: ${(item.execution_case?.target_invariants || []).join(" | ") || "none"}</div>
        ${sequenceSummary}
        ${coverageLine}
        ${stepFlow}
        ${stateFlow}
        ${validationLine}
      </div>
    `;
      }).join("")
    : `<div class="list-item"><strong>No hypothesis trace yet</strong><div class="muted">Launch analysis to generate surfaced and tested hypotheses.</div></div>`;
}

function renderInvariants(data) {
  const container = document.getElementById("invariant-list");
  if (!container) return;
  const subsystems = data?.subsystems || [];
  const rows = subsystems.flatMap((subsystem) => (subsystem.invariants || []).map((invariant) => ({subsystem: subsystem.name, invariant})));
  container.innerHTML = rows.length
    ? rows.map(({subsystem, invariant}) => `
      <div class="list-item">
        <strong>${invariant.unique_id} • ${subsystem}</strong>
        <div class="muted">${invariant.formal_statement}</div>
        <div class="muted">Confidence ${formatPercent(invariant.confidence || 0)}</div>
      </div>
    `).join("")
    : `<div class="list-item"><strong>No invariants</strong><div class="muted">Generated invariants will appear here.</div></div>`;
}

function renderPlanning(data) {
  const planning = data?.planning || {};
  const next = planning.next_action || {};
  setText("planner-next-action", next.action ? `Next action: ${next.action}` : "Planning...");
  setText("next-action-title", next.action ? next.action.replaceAll("_", " ") : "Waiting for planner");
  setText("next-action-reason", next.rationale || "");
  setText("next-action-gain", next.expected_information_gain !== undefined ? formatNumber(next.expected_information_gain, 2) : "—");
  setText("next-action-reduction", next.uncertainty_reduction !== undefined ? formatNumber(next.uncertainty_reduction, 2) : "—");

  const matchRatio = data?.expected_vs_observed?.match_ratio;
  setText("summary-coverage", matchRatio !== undefined ? formatPercent(matchRatio) : "—");
  setText("coverage-value", matchRatio !== undefined ? formatPercent(matchRatio) : "—");
  setText("coverage-details", "Awaiting analysis");

  const missing = data?.expected_vs_observed?.missing_expected || [];
  if (missing.length) {
    setText("summary-coverage-details", `Missing expectations: ${missing.join(", ")}`);
    setText("coverage-details", `Missing expected subsystems: ${missing.join(", ")}`);
  } else {
    setText("summary-coverage-details", "All expected subsystems accounted for.");
    setText("coverage-details", "Expected subsystem model matched.");
  }

  const bar = document.getElementById("next-action-bar");
  if (bar) {
    bar.style.width = `${Math.round((next.expected_information_gain || 0) * 100)}%`;
  }

  const planningContainer = document.getElementById("planning-summary");
  if (planningContainer) {
    planningContainer.innerHTML = `
      <div class="summary-row"><strong>Uncertainty score</strong><div class="muted">${formatNumber(planning.uncertainty_score, 2)}</div></div>
      <div class="summary-row"><strong>Invoke Tutor</strong><div class="muted">${planning.should_invoke_tutor ? "Yes" : "No"}</div></div>
      <div class="summary-row"><strong>Continue reconstruction</strong><div class="muted">${planning.should_continue_reconstruction ? "Yes" : "No"}</div></div>
      <div class="summary-row"><strong>Stop</strong><div class="muted">${planning.should_stop ? "Yes" : "No"}</div></div>
    `;
  }
}

function renderInspector(data) {
  const mainInspector = document.getElementById("inspector-output");
  const sidebarInspector = document.getElementById("sidebar-inspector");
  const payload = state.selectedArtifact || data?.subsystems?.[0] || data || {};
  const text = JSON.stringify(payload, null, 2);
  if (mainInspector) {
    mainInspector.textContent = text;
  }
  if (sidebarInspector) {
    sidebarInspector.textContent = text;
  }
}

function renderArtifacts(data) {
  const container = document.getElementById("artifact-list");
  if (!container) return;
  const subsystems = data?.subsystems || [];
  const artifacts = [
    {label: "Protocol pattern", value: data?.protocol_pattern?.label || "Unknown", payload: data?.protocol_pattern || {}},
    {label: "Coverage", value: data?.expected_vs_observed?.match_ratio !== undefined ? formatPercent(data.expected_vs_observed.match_ratio) : "—", payload: data?.expected_vs_observed || {}},
    {label: "Planner action", value: data?.planning?.next_action?.action || "Planning", payload: data?.planning || {}},
    {label: "Tutor notes", value: `${data?.tutor_research?.length || 0}`, payload: data?.tutor_research || []},
    {label: "Execution harness", value: data?.falsification_execution?.mode || "n/a", payload: data?.falsification_execution || {}},
    {label: "Validated sequences", value: `${data?.execution_sequences?.length || 0}`, payload: data?.execution_sequences || []},
    {label: "Rejected sequences", value: `${data?.rejected_execution_sequences?.length || 0}`, payload: data?.rejected_execution_sequences || []},
    ...subsystems.map((subsystem) => ({label: subsystem.name, value: `${subsystem.guarantees?.length || 0} guarantees`, payload: subsystem})),
  ];

  container.innerHTML = artifacts.map((artifact, index) => `
    <button class="list-item artifact-item" data-artifact-index="${index}">
      <strong>${artifact.label}</strong>
      <div class="muted">${artifact.value}</div>
    </button>
  `).join("");

  container.querySelectorAll(".artifact-item").forEach((button) => {
    button.addEventListener("click", () => {
      const index = Number(button.dataset.artifactIndex || 0);
      state.selectedArtifact = artifacts[index]?.payload || null;
      renderInspector(data);
      selectMainPanel("inspector");
      selectSidePanel("inspect");
    });
  });
}

function renderTimeline(data) {
  const container = document.getElementById("timeline");
  if (!container) return;
  const phases = data?.methodology?.phases || [];
  const events = [];
  if (data?.repository_context?.repository_path) {
    events.push(`Repository analyzed: ${data.repository_context.repository_path}`);
  }
  phases.forEach((phase) => events.push(shorten(phase.summary, 220)));
  const planning = data?.planning?.next_action;
  if (planning?.action) {
    events.push(`Planner selected: ${planning.action}`);
  }
  if (data?.tutor_research?.length) {
    events.push(`Tutor research notes: ${data.tutor_research.length}`);
  }
  if (data?.execution_sequences?.length) {
    events.push(`Validated execution sequences: ${data.execution_sequences.length}`);
  }
  if (data?.rejected_execution_sequences?.length) {
    events.push(`Rejected execution sequences: ${data.rejected_execution_sequences.length}`);
  }
  container.innerHTML = events.length
    ? events.map((event) => `<div class="timeline-event"><strong>Event</strong><div class="muted">${event}</div></div>`).join("")
    : `<div class="timeline-event"><strong>No timeline yet</strong><div class="muted">Run an analysis to populate the audit mission timeline.</div></div>`;
}

function renderConsole(data) {
  const container = document.getElementById("console-log");
  if (!container) return;
  const lines = [];
  lines.push(["Research", shorten(data?.methodology?.phases?.[0]?.summary || "Loading documentation...", 220)]);
  lines.push(["Planner", data?.planning?.next_action?.rationale || "Choosing next best action..."]);
  lines.push(["Tutor", data?.tutor_research?.length ? `Research notes pending verification: ${data.tutor_research.length}` : "No tutor run yet."]);
  lines.push(["Verification", data?.planning?.should_invoke_tutor ? "Evidence awaits verification." : "Verification layer idle."]);
  lines.push(["Falsification", data?.investigation_reports?.length ? `${data.investigation_reports.length} investigation reports available.` : "No falsification reports yet."]);
  const falsificationExecution = data?.falsification_execution || {};
  if (falsificationExecution.mode) {
    const caseCount = (falsificationExecution.cases || []).length;
    const executed = falsificationExecution.executed ? "executed" : "not executed";
    lines.push(["Execution", `Falsification harness ${executed} in mode ${falsificationExecution.mode} with ${caseCount} cases.`]);
  }
  if (data?.execution_sequences?.length || data?.rejected_execution_sequences?.length) {
    lines.push([
      "Sequences",
      `Validated ${data?.execution_sequences?.length || 0}, rejected ${data?.rejected_execution_sequences?.length || 0}, threshold ${formatPercent(data?.execution_sequence_coverage?.minimum_threshold || 0)}.`,
    ]);
  }
  container.innerHTML = lines.map(([tag, text]) => `<div class="log-line"><span class="log-tag">[${tag}]</span>${text}</div>`).join("");
}

function renderHeader(data) {
  const protocolName = data?.repository_context?.repository_path?.split("/").pop() || "Protocol";
  setText("protocol-title", protocolName);
  setText("protocol-subtitle", data?.status === "ready"
    ? `Halyx is reconstructing ${protocolName} and supervising the result.`
    : "Halyx is awaiting the first analysis artifact.");
  setText("pattern-label", data?.protocol_pattern?.label || "Unknown");
  setText("pattern-confidence", data?.protocol_pattern?.confidence !== undefined ? `Confidence ${formatPercent(data.protocol_pattern.confidence)}` : "—");

  const uncertainty = data?.planning?.uncertainty_score;
  setText("uncertainty-score", uncertainty !== undefined ? formatPercent(uncertainty) : "—");
  setText("uncertainty-reason", data?.planning?.next_action?.rationale || "No planner output yet.");

  setText("consensus-label", data?.consensus?.classification || "—");
  setText("consensus-confidence", data?.consensus?.research_priority !== undefined ? `Research priority ${formatNumber(data.consensus.research_priority, 2)}` : "—");
  setText("consensus-explain", data?.consensus_explain?.explanation || "Awaiting consensus explanation.");

  const gaps = data?.consensus_explain?.missing_expected || [];
  const support = data?.consensus_explain?.supported_cases;
  const disproved = data?.consensus_explain?.disproved_cases;
  const unknown = data?.consensus_explain?.unknown_cases;
  const basis = (support !== undefined && disproved !== undefined && unknown !== undefined)
    ? `Execution basis: supported ${support}, disproved ${disproved}, unresolved ${unknown}.`
    : "";
  const gapText = gaps.length ? `Open knowledge gaps: ${gaps.join(", ")}.` : "No expected subsystem gaps detected.";
  setText("consensus-gaps", `${gapText} ${basis}`.trim());

  if (!state.lastPocResult) {
    setText("run-poc-status", "POC status: not run yet.");
  }
}

function renderPocResult(result) {
  const panel = document.getElementById("run-poc-result");
  if (!panel) return;

  if (!result) {
    panel.innerHTML = `
      <strong>POC Result</strong>
      <p class="muted">No POC execution has been triggered in this session.</p>
    `;
    setText("run-poc-status", "POC status: not run yet.");
    return;
  }

  const verdict = result.passed ? "PASS" : "FAIL";
  const code = result.return_code === null || result.return_code === undefined ? "n/a" : result.return_code;
  const source = result.fork_rpc_source || "n/a";
  const analysis = result.analysis || {};
  const implication = analysis.implication || "unknown";
  const explanation = analysis.explanation || "No interpretation available.";
  const passedTests = (analysis.passed_tests || []).length;
  const failedTests = (analysis.failed_tests || []).length;
  const validationMisses = (analysis.target_validation_miss_tests || []).length;
  const snippet = (result.stdout_tail || result.stderr_tail || "").split("\n").slice(-18).join("\n");
  panel.innerHTML = `
    <strong>POC Result</strong>
    <p class="muted">Run: ${result.run_id || "n/a"} • Verdict: ${verdict} • Return code: ${code}</p>
    <p class="muted">Fork RPC source: ${source}</p>
    <p class="muted">Implication: ${implication}</p>
    <p class="muted">Interpretation: ${explanation}</p>
    <p class="muted">Test counts: passed ${passedTests}, failed ${failedTests}, validation misses ${validationMisses}</p>
    <div class="poc-result-log">${snippet || "No output captured."}</div>
  `;
  setText("run-poc-status", `POC status: ${verdict} (run ${result.run_id || "n/a"}, code ${code}).`);
}

function renderRunSelector(data) {
  const selector = document.getElementById("run-selector");
  if (!selector) return;
  const runs = data?.runs || [];
  state.runs = runs;
  selector.innerHTML = runs.length
    ? runs.map((run) => `<option value="${run.run_id}">${run.run_id} • ${run.target || run.repository_path || "run"}</option>`).join("")
    : `<option value="">No runs yet</option>`;

  if (!runs.length) {
    state.selectedRunId = null;
    return;
  }

  const preferred = state.selectedRunId && runs.some((run) => run.run_id === state.selectedRunId)
    ? state.selectedRunId
    : (data?.latest_run_id || runs[0].run_id);
  state.selectedRunId = preferred;
  selector.value = preferred;
}

function renderTreeOutput(payload) {
  const output = document.getElementById("file-tree-output");
  if (!output) return;
  if (!payload?.entries?.length) {
    output.textContent = "No file tree entries available for this run.";
    return;
  }
  const rows = payload.entries.map((entry) => {
    const indent = `padding-left: ${Math.min(24, Number(entry.depth || 0)) * 14}px;`;
    const glyph = entry.type === "dir" ? "[D]" : "[F]";
    const size = entry.size === null || entry.size === undefined ? "" : `${entry.size} B`;
    const buttonAttrs = entry.type === "file"
      ? `class="file-tree-row file" data-file-path="${entry.path}"`
      : "class=\"file-tree-row dir\"";
    return `<button type="button" ${buttonAttrs} style="${indent}"><span class="file-tree-path">${glyph} ${entry.path}</span><span class="file-tree-size">${size}</span></button>`;
  }).join("");
  output.innerHTML = payload.truncated
    ? `${rows}<div class="muted">... file list truncated, increase max entries if needed ...</div>`
    : rows;

  output.querySelectorAll("[data-file-path]").forEach((button) => {
    button.addEventListener("click", async () => {
      const path = button.getAttribute("data-file-path");
      if (!path) return;
      await openRunFile(path);
    });
  });
}

function renderTerminalOutput(payload) {
  const output = document.getElementById("terminal-output");
  if (!output) return;
  output.textContent = payload?.text || "No terminal output available for this run.";
}

function toRepoRelativePath(absolutePath, repositoryPath) {
  const abs = String(absolutePath || "");
  const repo = String(repositoryPath || "");
  if (!abs || !repo) return null;
  const normalizedAbs = abs.replace(/\\/g, "/");
  const normalizedRepo = repo.replace(/\\/g, "/");
  if (!normalizedAbs.startsWith(normalizedRepo)) return null;
  let rel = normalizedAbs.slice(normalizedRepo.length);
  if (rel.startsWith("/")) rel = rel.slice(1);
  return rel || null;
}

async function openRunFile(path) {
  if (!state.selectedRunId || !path) return;
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(state.selectedRunId)}/file?path=${encodeURIComponent(path)}`, {cache: "no-store"});
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const payload = await response.json();
    state.selectedFilePath = payload.path;
    const pathLabel = document.getElementById("file-open-path");
    const editor = document.getElementById("file-editor");
    if (pathLabel) pathLabel.textContent = `Open file: ${payload.path}`;
    if (editor) editor.value = payload.content || "";
  } catch (error) {
    setText("protocol-subtitle", `Failed to open file: ${error.message}`);
  }
}

async function saveOpenFile() {
  if (!state.selectedRunId || !state.selectedFilePath) {
    setText("protocol-subtitle", "Open a file from the tree before saving.");
    return;
  }
  const editor = document.getElementById("file-editor");
  const saveButton = document.getElementById("save-file-button");
  if (!editor) return;

  if (saveButton) {
    saveButton.disabled = true;
    saveButton.textContent = "Saving...";
  }
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(state.selectedRunId)}/file`, {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({path: state.selectedFilePath, content: editor.value}),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const payload = await response.json();
    setText("protocol-subtitle", `Saved ${payload.path} (${payload.bytes_written} bytes).`);
  } catch (error) {
    setText("protocol-subtitle", `Failed to save file: ${error.message}`);
  } finally {
    if (saveButton) {
      saveButton.disabled = false;
      saveButton.textContent = "Save Open File";
    }
  }
}

async function openGeneratedFoundryTest() {
  const selectedRun = (state.runs || []).find((run) => run?.run_id === state.selectedRunId) || null;
  const repositoryPath = selectedRun?.repository_path || state.dashboard?.repository_context?.repository_path;
  const execution = state.dashboard?.falsification_execution || {};
  const candidatePaths = [];
  if (execution.generated_test_file) {
    candidatePaths.push(execution.generated_test_file);
  }
  if (state.lastPocResult?.run_id === state.selectedRunId && state.lastPocResult?.harness_dir) {
    candidatePaths.push(`${state.lastPocResult.harness_dir}/test/HalyxHypothesisEvidence.t.sol`);
  }
  if (repositoryPath) {
    candidatePaths.push(`${repositoryPath}/.halyx/falsification_harness/test/HalyxHypothesisEvidence.t.sol`);
  }

  const relative = candidatePaths
    .map((path) => toRepoRelativePath(path, repositoryPath))
    .find((path) => Boolean(path));
  if (!relative) {
    setText("protocol-subtitle", "Generated test path is not available for this run.");
    return;
  }
  selectMainPanel("files");
  await openRunFile(relative);
}

async function loadRunViews(runId) {
  if (!runId) {
    state.selectedFilePath = null;
    const pathLabel = document.getElementById("file-open-path");
    const editor = document.getElementById("file-editor");
    if (pathLabel) pathLabel.textContent = "Select a file to open.";
    if (editor) editor.value = "";
    renderTreeOutput({entries: []});
    renderTerminalOutput({text: "No run selected."});
    return;
  }

  try {
    const [treeResponse, terminalResponse] = await Promise.all([
      fetch(`/api/runs/${encodeURIComponent(runId)}/tree`, {cache: "no-store"}),
      fetch(`/api/runs/${encodeURIComponent(runId)}/terminal`, {cache: "no-store"}),
    ]);

    if (!treeResponse.ok) {
      throw new Error(await treeResponse.text());
    }
    if (!terminalResponse.ok) {
      throw new Error(await terminalResponse.text());
    }

    const treePayload = await treeResponse.json();
    const terminalPayload = await terminalResponse.json();
    renderTreeOutput(treePayload);
    renderTerminalOutput(terminalPayload);
  } catch (error) {
    renderTreeOutput({entries: []});
    renderTerminalOutput({text: `Failed to load run views: ${error.message}`});
  }
}

async function deleteSelectedRun() {
  const runId = state.selectedRunId;
  if (!runId) {
    setText("protocol-subtitle", "Select a run before attempting deletion.");
    return;
  }

  const deleteSourceTree = Boolean(document.getElementById("delete-source-tree")?.checked);
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(runId)}?delete_source_tree=${deleteSourceTree ? "true" : "false"}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    await refreshDashboard();
    setText("protocol-subtitle", `Run ${runId} deleted.`);
  } catch (error) {
    setText("protocol-subtitle", `Failed to delete run: ${error.message}`);
  }
}

async function runPocNow() {
  const runId = state.selectedRunId;
  if (!runId) {
    setText("protocol-subtitle", "Select a run before executing the POC harness.");
    return;
  }

  const buttons = [
    document.getElementById("run-poc-button"),
    document.getElementById("run-poc-button-header"),
  ].filter(Boolean);
  buttons.forEach((button) => {
    button.disabled = true;
    button.textContent = "Running POC...";
  });
  setText("run-poc-status", `POC status: running for ${runId}...`);
  renderPocResult({run_id: runId, passed: false, return_code: "running", fork_rpc_source: "pending", stdout_tail: "Executing forge test..."});
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/poc-run`, {
      method: "POST",
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const payload = await response.json();
    state.lastPocResult = payload;
    renderPocResult(payload);
    renderTerminalOutput({text: payload.terminal_text || "No POC terminal output returned."});
    selectMainPanel("terminal");
    const verdict = payload.passed ? "PASS" : "FAIL";
    setText("protocol-subtitle", `POC run completed for ${runId}: ${verdict} (return code ${payload.return_code}).`);
    await refreshDashboard();
  } catch (error) {
    setText("protocol-subtitle", `POC run failed to execute: ${error.message}`);
  } finally {
    buttons.forEach((button) => {
      button.disabled = false;
      button.textContent = "Run POC Now";
    });
  }
}

function bindTabs() {
  document.querySelectorAll("[data-main-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      selectMainPanel(button.dataset.mainTab || "summary");
    });
  });

  document.querySelectorAll("[data-side-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      selectSidePanel(button.dataset.sideTab || "inspect");
    });
  });

  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      const view = button.dataset.view || "";
      state.selectedArtifact = {selected_view: view, dashboard: state.dashboard?.status || "idle"};
      renderInspector(state.dashboard || {});
      selectMainPanel("inspector");
      selectSidePanel("inspect");
    });
  });

  const selector = document.getElementById("run-selector");
  if (selector) {
    selector.addEventListener("change", async (event) => {
      const value = event.target?.value || null;
      state.selectedRunId = value;
      state._runViewsLoaded = false;
      state.selectedFilePath = null;
      const pathLabel = document.getElementById("file-open-path");
      const editor = document.getElementById("file-editor");
      if (pathLabel) pathLabel.textContent = "Select a file to open.";
      if (editor) editor.value = "";
      await loadRunViews(value);
    });
  }

  document.getElementById("refresh-tree-button")?.addEventListener("click", async () => {
    await loadRunViews(state.selectedRunId);
  });

  document.getElementById("delete-run-button")?.addEventListener("click", async () => {
    await deleteSelectedRun();
  });

  document.getElementById("save-file-button")?.addEventListener("click", async () => {
    await saveOpenFile();
  });

  document.getElementById("open-generated-test-button")?.addEventListener("click", async () => {
    await openGeneratedFoundryTest();
  });

  document.getElementById("run-poc-button")?.addEventListener("click", async () => {
    await runPocNow();
  });

  document.getElementById("run-poc-button-header")?.addEventListener("click", async () => {
    await runPocNow();
  });
}

async function launchProtocol(event) {
  event.preventDefault();
  const launchButton = document.getElementById("launch-button");
  const target = document.getElementById("launch-target");
  const scope = document.getElementById("launch-scope");
  const chain = document.getElementById("launch-chain");
  const etherscanApiKey = document.getElementById("launch-etherscan-api-key")?.value?.trim() || "";
  const etherscanApiKeyAlt = document.getElementById("launch-etherscan-api-key-alt")?.value?.trim() || "";
  if (!target || !launchButton) return;

  const protocolTarget = target.value.trim();
  if (!protocolTarget) {
    setText("protocol-subtitle", "Enter a protocol name, repository reference, or contract address first.");
    return;
  }

  launchButton.textContent = "Launching...";
  launchButton.disabled = true;
  try {
    const response = await fetch("/api/launch", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        target: protocolTarget,
        scope: scope?.value.trim() || null,
        chain: chain?.value.trim() || "ethereum",
        etherscan_api_key: etherscanApiKey || null,
        etherscan_api_key_alt: etherscanApiKeyAlt || null,
      }),
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `Launch failed with status ${response.status}`);
    }
    const payload = await response.json();
    state.selectedRunId = payload?.run_id || null;
    await refreshDashboard();
    selectMainPanel("summary");
  } catch (error) {
    setText("protocol-subtitle", `Failed to launch: ${error.message}`);
    // Automatically surface the assistant so the user gets actionable guidance.
    assistantOpenWithError(error.message);
  } finally {
    launchButton.textContent = "Launch protocol";
    launchButton.disabled = false;
  }
}

async function saveEnvFile(event) {
  event.preventDefault();
  const runId = state.selectedRunId;
  if (!runId) {
    setText("protocol-subtitle", "Select a run first so Halyx knows where to write the env file.");
    return;
  }

  const saveButton = document.getElementById("env-save-button");
  const fileName = document.getElementById("env-file-name")?.value || ".env";
  const forkTestRpcUrl = document.getElementById("env-fork-test-rpc-url")?.value?.trim() || "";
  const rpcUrl = document.getElementById("env-rpc-url")?.value?.trim() || "";
  const alchemyApiKey = document.getElementById("env-alchemy-api-key")?.value?.trim() || "";
  const etherscanApiKey = document.getElementById("env-etherscan-api-key")?.value?.trim() || "";
  const etherscanApiKeyAlt = document.getElementById("env-etherscan-api-key-alt")?.value?.trim() || "";

  if (!forkTestRpcUrl && !rpcUrl && !alchemyApiKey && !etherscanApiKey && !etherscanApiKeyAlt) {
    setText("protocol-subtitle", "Provide at least one env value before saving.");
    return;
  }

  if (saveButton) {
    saveButton.textContent = "Saving...";
    saveButton.disabled = true;
  }

  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/env`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        file_name: fileName,
        fork_test_rpc_url: forkTestRpcUrl || null,
        rpc_url: rpcUrl || null,
        alchemy_api_key: alchemyApiKey || null,
        etherscan_api_key: etherscanApiKey || null,
        etherscan_api_key_alt: etherscanApiKeyAlt || null,
      }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const payload = await response.json();
    const keys = (payload.updated_keys || []).join(", ") || "none";
    setText("protocol-subtitle", `Saved ${keys} to ${payload.env_path}.`);
  } catch (error) {
    setText("protocol-subtitle", `Failed to save env file: ${error.message}`);
  } finally {
    if (saveButton) {
      saveButton.textContent = "Save env for selected run";
      saveButton.disabled = false;
    }
  }
}

async function refreshDashboard() {
  try {
    const response = await fetch("/api/dashboard", {cache: "no-store"});
    const dashboard = await response.json();

    // Skip full re-render if payload hasn't changed.
    const fingerprint = JSON.stringify({
      consensus: dashboard?.consensus,
      latest_run_id: dashboard?.latest_run_id,
      hypothesis_count: (dashboard?.hypothesis_evidence_ledger || []).length,
      falsification_mode: dashboard?.falsification_execution?.mode,
      falsification_cases: (dashboard?.falsification_execution?.cases || []).length,
    });
    if (fingerprint === state._lastFingerprint) return;
    state._lastFingerprint = fingerprint;

    state.dashboard = dashboard;
    renderHeader(dashboard);
    renderPocResult(state.lastPocResult);
    renderStages(dashboard);
    renderCoverage(dashboard);
    renderTutor(dashboard);
    renderHypotheses(dashboard);
    renderHypothesisTrace(dashboard);
    renderInvariants(dashboard);
    renderPlanning(dashboard);
    renderInspector(dashboard);
    renderArtifacts(dashboard);
    renderTimeline(dashboard);
    renderConsole(dashboard);
    renderRunSelector(dashboard);
    // Only load run views on explicit selection, not on every poll tick.
    if (state.selectedRunId && !state._runViewsLoaded) {
      await loadRunViews(state.selectedRunId);
      state._runViewsLoaded = true;
    }
  } catch (error) {
    setText("protocol-title", "Halyx Mission Control");
    setText("protocol-subtitle", `Failed to load dashboard: ${error.message}`);
  }
}

bindTabs();
document.getElementById("launch-form")?.addEventListener("submit", launchProtocol);
document.getElementById("env-save-form")?.addEventListener("submit", saveEnvFile);
selectMainPanel("summary");
selectSidePanel("inspect");
refreshDashboard();
setInterval(refreshDashboard, 30000);
// ── Report panel ──────────────────────────────────────────────────────────────

let _reportContent = "";

async function generateReport() {
  const runId = state.selectedRunId || "latest_artifact";
  const statusEl = document.getElementById("report-status");
  const outputEl = document.getElementById("report-output");
  if (statusEl) statusEl.textContent = "Generating report…";
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/report/regenerate`, {method: "POST"});
    if (!response.ok) throw new Error(await response.text());
    const data = await response.json();
    _reportContent = data.content || "";
    if (outputEl) outputEl.textContent = _reportContent;
    if (statusEl) statusEl.textContent = `Report generated: ${data.report_path}`;
  } catch (err) {
    if (statusEl) statusEl.textContent = `Failed: ${err.message}`;
    assistantOpenWithError(`Report generation failed: ${err.message}`);
  }
}

function downloadReport() {
  if (!_reportContent) { alert("Generate a report first."); return; }
  const blob = new Blob([_reportContent], {type: "text/markdown"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `halyx-report-${(state.selectedRunId || "latest")}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

document.getElementById("report-generate-button")?.addEventListener("click", generateReport);
document.getElementById("report-download-button")?.addEventListener("click", downloadReport);

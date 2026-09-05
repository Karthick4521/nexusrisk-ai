// NexusRisk AI - Dashboard logic (vanilla JS, no build step)

let currentInvestigationId = null;
let timelineChartInstance = null;
let compareChartInstance = null;

const el = (id) => document.getElementById(id);

function showLoading(show) {
  el("loadingOverlay").classList.toggle("hidden", !show);
}

function fmtCurrency(amount) {
  if (amount === null || amount === undefined) return "-";
  return "\u20b9" + Number(amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

async function analyzeFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("customer_id", "CUST-UPLOAD-" + Date.now());
  showLoading(true);
  try {
    const resp = await fetch("/api/analyze", { method: "POST", body: formData });
    const data = await resp.json();
    handleAnalysisResponse(data);
  } catch (err) {
    alert("Analysis failed: " + err.message);
  } finally {
    showLoading(false);
  }
}

async function analyzeDemo(caseName) {
  const formData = new FormData();
  formData.append("case", caseName);
  showLoading(true);
  try {
    const resp = await fetch("/api/analyze-demo", { method: "POST", body: formData });
    const data = await resp.json();
    handleAnalysisResponse(data);
  } catch (err) {
    alert("Analysis failed: " + err.message);
  } finally {
    showLoading(false);
  }
}

function handleAnalysisResponse(data) {
  if (!data.ok) {
    el("emptyState").classList.remove("hidden");
    el("resultsState").classList.add("hidden");
    alert("Validation failed:\n" + (data.messages || []).join("\n"));
    return;
  }
  currentInvestigationId = data.investigation_id;
  renderResults(data);
}

function renderResults(data) {
  el("emptyState").classList.add("hidden");
  el("resultsState").classList.remove("hidden");
  el("reportCard").classList.add("hidden");

  // Case summary
  el("customerId").textContent = data.customer_id;
  el("investigationId").textContent = data.investigation_id;
  el("txnCount").textContent = data.transactions_analyzed;
  el("riskSignalCount").textContent = data.risk_findings.length;
  const priorityBadge = el("priorityBadge");
  priorityBadge.textContent = `${data.score.category.replace(/_/g, " ")} (${data.score.review_priority_score})`;
  priorityBadge.className = "badge " + data.score.category;

  const validationBox = el("validationMessages");
  if (data.validation_messages && data.validation_messages.length) {
    validationBox.innerHTML = "<strong>Validation notes:</strong><ul>" +
      data.validation_messages.map(m => `<li>${escapeHtml(m)}</li>`).join("") + "</ul>";
    validationBox.classList.remove("hidden");
  } else {
    validationBox.classList.add("hidden");
  }

  // Baseline
  const b = data.baseline;
  el("baseMedian").textContent = fmtCurrency(b.median_amount);
  el("baseRange").textContent = `${fmtCurrency(b.typical_range_low)} \u2013 ${fmtCurrency(b.typical_range_high)}`;
  el("baseHours").textContent = (b.typical_hour_start !== null && b.typical_hour_end !== null)
    ? `${String(b.typical_hour_start).padStart(2,"0")}:00 \u2013 ${String(b.typical_hour_end).padStart(2,"0")}:00`
    : "-";
  el("baseChannel").textContent = (b.common_channels && b.common_channels.length) ? b.common_channels[0] : "-";
  el("baseBeneficiaries").textContent = b.known_beneficiaries_count ?? "-";
  el("baseDaily").textContent = b.avg_daily_transactions ? b.avg_daily_transactions.toFixed(1) : "-";

  // Risk signals
  renderRiskSignals(data.risk_findings);

  // Evidence chain
  renderEvidenceChain(data.evidence_chain);
  el("evidenceViewer").innerHTML = '<div class="evidence-viewer-empty">Select a transaction ID in the Evidence Chain to inspect it.</div>';

  // AI summary
  const ai = data.ai_result;
  const aiBadge = el("aiBadge");
  if (ai.ai_generated) {
    aiBadge.textContent = "Gemini-generated";
    aiBadge.className = "ai-badge live";
  } else {
    aiBadge.textContent = "Deterministic fallback";
    aiBadge.className = "ai-badge fallback";
  }
  el("aiSummary").textContent = ai.summary || "-";
  el("investigatorFocus").innerHTML = (ai.investigator_focus || []).map(i => `<li>${escapeHtml(i)}</li>`).join("") || "<li>None</li>";
  el("uncertaintiesList").innerHTML = (ai.uncertainties || []).map(i => `<li>${escapeHtml(i)}</li>`).join("") || "<li>None</li>";

  // Charts
  renderTimelineChart(data.timeline);
  renderCompareChart(data.baseline, data.timeline);
}

function renderRiskSignals(findings) {
  const container = el("riskSignalsList");
  if (!findings.length) {
    container.innerHTML = '<div class="no-signals">No significant risk signals identified in the supplied transaction history.</div>';
    return;
  }
  container.innerHTML = findings.map(f => `
    <div class="risk-signal-item">
      <div class="rs-head">
        <span class="rs-id">${f.rule_id}</span>
        <span class="rs-title">${escapeHtml(f.title)}</span>
        <span class="badge ${severityToCategory(f.severity)}">${f.severity}</span>
      </div>
      <div class="rs-explain">${escapeHtml(f.explanation)}</div>
      <div class="rs-evidence">
        ${f.evidence_ids.map(id => `<span onclick="viewEvidence('${id}')">${id}</span>`).join("")}
      </div>
    </div>
  `).join("");
}

function severityToCategory(sev) {
  if (sev === "HIGH") return "HIGH";
  if (sev === "MEDIUM") return "MEDIUM";
  return "LOW";
}

function renderEvidenceChain(tree) {
  const container = el("evidenceChainTree");
  if (!tree.children || !tree.children.length) {
    container.innerHTML = '<div class="no-signals">No evidence to display - no risk signals were triggered.</div>';
    return;
  }
  let html = `<div class="et-root">${escapeHtml(tree.label.replace(/_/g," "))}</div>`;
  for (const rule of tree.children) {
    html += `<div class="et-rule">${escapeHtml(rule.label)}</div>`;
    for (const txn of rule.children) {
      html += `<div class="et-txn" onclick="viewEvidence('${txn.transaction_id}')">${txn.transaction_id}</div>`;
    }
  }
  container.innerHTML = html;
}

async function viewEvidence(transactionId) {
  if (!currentInvestigationId) return;
  const viewer = el("evidenceViewer");
  viewer.innerHTML = '<div class="evidence-viewer-empty">Loading...</div>';
  try {
    const resp = await fetch(`/api/evidence/${currentInvestigationId}/${transactionId}`);
    if (!resp.ok) {
      viewer.innerHTML = '<div class="evidence-viewer-empty">Transaction not found.</div>';
      return;
    }
    const ev = await resp.json();
    viewer.innerHTML = `
      <div class="evidence-viewer-grid">
        <div><div class="ev-k">Transaction ID</div><div class="ev-v">${ev.transaction_id}</div></div>
        <div><div class="ev-k">Date</div><div class="ev-v">${new Date(ev.date).toLocaleString()}</div></div>
        <div><div class="ev-k">Amount</div><div class="ev-v">${fmtCurrency(ev.amount)}</div></div>
        <div><div class="ev-k">Channel</div><div class="ev-v">${escapeHtml(ev.channel || "-")}</div></div>
        <div><div class="ev-k">Payee</div><div class="ev-v">${escapeHtml(ev.payee || "-")}</div></div>
        <div><div class="ev-k">Beneficiary</div><div class="ev-v">${escapeHtml(ev.beneficiary_id || "-")}</div></div>
        <div><div class="ev-k">Triggered Rules</div><div class="ev-v">${ev.triggered_rules.join(", ") || "-"}</div></div>
      </div>
      <div class="why-selected">
        <div class="ev-k">Why Selected</div>
        <ul>${ev.why_selected.map(r => `<li>${escapeHtml(r)}</li>`).join("") || "<li>Not directly flagged</li>"}</ul>
      </div>
      <div class="baseline-compare">
        <div class="ev-k">Customer Baseline Comparison</div>
        <div style="margin-top:6px;">Typical transfer: ${fmtCurrency(ev.baseline_comparison.typical_range_low)} \u2013 ${fmtCurrency(ev.baseline_comparison.typical_range_high)}</div>
        <div>Median: ${fmtCurrency(ev.baseline_comparison.median_amount)}</div>
        <div>Observed: <strong>${fmtCurrency(ev.baseline_comparison.observed_amount)}</strong></div>
      </div>
    `;
  } catch (err) {
    viewer.innerHTML = `<div class="evidence-viewer-empty">Error loading evidence: ${err.message}</div>`;
  }
}

function renderTimelineChart(timeline) {
  const ctx = document.getElementById("timelineChart");
  if (timelineChartInstance) timelineChartInstance.destroy();
  const labels = timeline.map(t => new Date(t.date).toLocaleDateString());
  const values = timeline.map(t => t.amount);
  const colors = timeline.map(t => t.flagged ? "#f2545b" : "#3f8cff");
  timelineChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: "Transaction Amount",
        data: values,
        borderColor: "#3f8cff",
        backgroundColor: "rgba(63,140,255,0.08)",
        pointBackgroundColor: colors,
        pointRadius: timeline.map(t => t.flagged ? 5 : 2),
        tension: 0.15,
        fill: true,
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#9aabc0", maxTicksLimit: 10 }, grid: { color: "#22314544" } },
        y: { ticks: { color: "#9aabc0" }, grid: { color: "#22314544" } },
      }
    }
  });
}

function renderCompareChart(baseline, timeline) {
  const ctx = document.getElementById("compareChart");
  if (compareChartInstance) compareChartInstance.destroy();
  const flaggedAmounts = timeline.filter(t => t.flagged).map(t => t.amount);
  const maxFlagged = flaggedAmounts.length ? Math.max(...flaggedAmounts) : 0;

  compareChartInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels: ["Typical Low", "Typical High", "Median", "Max Flagged"],
      datasets: [{
        label: "Amount",
        data: [baseline.typical_range_low || 0, baseline.typical_range_high || 0, baseline.median_amount || 0, maxFlagged],
        backgroundColor: ["#3f8cff", "#3f8cff", "#2fd6c4", "#f2545b"],
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#9aabc0" }, grid: { display: false } },
        y: { ticks: { color: "#9aabc0" }, grid: { color: "#22314544" } },
      }
    }
  });
}

async function generateReport() {
  if (!currentInvestigationId) return;
  showLoading(true);
  try {
    const formData = new FormData();
    formData.append("investigation_id", currentInvestigationId);
    const resp = await fetch("/api/generate-report", { method: "POST", body: formData });
    const text = await resp.text();
    el("reportText").textContent = text;
    el("reportCard").classList.remove("hidden");
    el("reportCard").scrollIntoView({ behavior: "smooth" });
  } catch (err) {
    alert("Report generation failed: " + err.message);
  } finally {
    showLoading(false);
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// --- Event wiring ---
document.getElementById("csvUpload").addEventListener("change", (e) => {
  if (e.target.files && e.target.files[0]) analyzeFile(e.target.files[0]);
});
document.getElementById("loadNormalBtn").addEventListener("click", () => analyzeDemo("normal_case"));
document.getElementById("loadDifficultBtn").addEventListener("click", () => analyzeDemo("difficult_case"));
document.getElementById("generateReportBtn").addEventListener("click", generateReport);

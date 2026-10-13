/**
 * CertifyFlow Studio - Frontend Application Logic
 * Pure Vanilla JavaScript (Zero external runtime dependencies)
 */

document.addEventListener("DOMContentLoaded", () => {
  // --- DOM Elements ---
  const healthPill = document.getElementById("health-pill");
  const healthText = document.getElementById("health-text");
  const pulseDot = document.getElementById("pulse-dot");

  const apiKeyInput = document.getElementById("api-key-input");
  const toggleKeyVisibilityBtn = document.getElementById("toggle-key-visibility");

  const jobForm = document.getElementById("job-form");
  const courseNameInput = document.getElementById("course-name");
  const issueDateInput = document.getElementById("issue-date");

  const tabBuilderBtn = document.getElementById("tab-builder-btn");
  const tabCsvBtn = document.getElementById("tab-csv-btn");
  const viewBuilder = document.getElementById("view-builder");
  const viewCsv = document.getElementById("view-csv");

  const btnAddRow = document.getElementById("btn-add-row");
  const btnLoadSamples = document.getElementById("btn-load-samples");
  const btnClearRoster = document.getElementById("btn-clear-roster");
  const rosterTbody = document.getElementById("roster-tbody");
  const recipientCountBadge = document.getElementById("recipient-count-badge");

  const csvDropzone = document.getElementById("csv-dropzone");
  const csvFileInput = document.getElementById("csv-file-input");
  const csvTextarea = document.getElementById("csv-textarea");
  const btnParseCsv = document.getElementById("btn-parse-csv");

  const btnSubmitJob = document.getElementById("btn-submit-job");
  const submitSpinner = document.getElementById("submit-spinner");
  const submitBtnText = document.getElementById("submit-btn-text");
  const submitErrorBanner = document.getElementById("submit-error-banner");

  const monitorIdleState = document.getElementById("monitor-idle-state");
  const monitorActiveState = document.getElementById("monitor-active-state");
  const monitorStatusBadge = document.getElementById("monitor-status-badge");
  const activeJobIdEl = document.getElementById("active-job-id");
  const btnCopyJobId = document.getElementById("btn-copy-job-id");

  const progressBarFill = document.getElementById("progress-bar-fill");
  const progressPercentLabel = document.getElementById("progress-percent-label");
  const metricTotal = document.getElementById("metric-total");
  const metricSuccess = document.getElementById("metric-success");
  const metricFailed = document.getElementById("metric-failed");
  const btnDownloadZip = document.getElementById("btn-download-zip");

  const resultsTableWrapper = document.getElementById("results-tbody");
  const resultsFilterSelect = document.getElementById("results-status-filter");

  const historyToggle = document.getElementById("history-toggle");
  const historyList = document.getElementById("history-list");
  const historyCount = document.getElementById("history-count");
  const historyChevron = document.getElementById("history-chevron");

  // --- State ---
  let activeJobId = null;
  let pollIntervalId = null;
  let cachedCertificates = [];
  const STORAGE_KEY_API = "certifyflow_api_key";
  const STORAGE_KEY_JOBS = "certifyflow_recent_jobs";

  // Pre-fill today's date
  const today = new Date().toISOString().split("T")[0];
  issueDateInput.value = today;

  // Restore API Key from localStorage
  const savedApiKey = localStorage.getItem(STORAGE_KEY_API);
  if (savedApiKey) {
    apiKeyInput.value = savedApiKey;
  }
  apiKeyInput.addEventListener("input", () => {
    localStorage.setItem(STORAGE_KEY_API, apiKeyInput.value.trim());
  });

  // Toggle API key password masking
  toggleKeyVisibilityBtn.addEventListener("click", () => {
    if (apiKeyInput.type === "password") {
      apiKeyInput.type = "text";
      toggleKeyVisibilityBtn.textContent = "🔒";
    } else {
      apiKeyInput.type = "password";
      toggleKeyVisibilityBtn.textContent = "👁️";
    }
  });

  // --- Health Probe Polling ---
  async function checkServerHealth() {
    try {
      const res = await fetch("/healthz");
      const data = await res.json();
      if (res.ok && data.status === "healthy") {
        pulseDot.className = "pulse-indicator healthy";
        healthText.textContent = `All Systems Operational (${data.checks.storage.backend.toUpperCase()})`;
      } else {
        pulseDot.className = "pulse-indicator unhealthy";
        healthText.textContent = "Cluster Degraded";
      }
    } catch (err) {
      pulseDot.className = "pulse-indicator unhealthy";
      healthText.textContent = "API Offline";
    }
  }
  checkServerHealth();
  setInterval(checkServerHealth, 20000);

  // --- Tab Navigation ---
  tabBuilderBtn.addEventListener("click", () => {
    tabBuilderBtn.classList.add("active");
    tabCsvBtn.classList.remove("active");
    viewBuilder.classList.add("active");
    viewCsv.classList.remove("active");
  });

  tabCsvBtn.addEventListener("click", () => {
    tabCsvBtn.classList.add("active");
    tabBuilderBtn.classList.remove("active");
    viewCsv.classList.add("active");
    viewBuilder.classList.remove("active");
  });

  // --- Recipient Roster Management ---
  function updateRecipientCount() {
    const rows = rosterTbody.querySelectorAll("tr");
    recipientCountBadge.textContent = `${rows.length} recipient${rows.length === 1 ? "" : "s"}`;
  }

  function createRecipientRow(name = "", email = "") {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>
        <input type="text" class="table-input row-name" placeholder="Recipient Full Name" value="${escapeHtml(name)}" required />
      </td>
      <td>
        <input type="text" class="table-input row-email" placeholder="recipient@example.com" value="${escapeHtml(email)}" required />
      </td>
      <td style="text-align: center;">
        <button type="button" class="btn-delete-row" title="Remove Recipient">✕</button>
      </td>
    `;

    tr.querySelector(".btn-delete-row").addEventListener("click", () => {
      tr.remove();
      updateRecipientCount();
    });

    return tr;
  }

  btnAddRow.addEventListener("click", () => {
    rosterTbody.appendChild(createRecipientRow());
    updateRecipientCount();
  });

  btnClearRoster.addEventListener("click", () => {
    rosterTbody.innerHTML = "";
    updateRecipientCount();
  });

  btnLoadSamples.addEventListener("click", () => {
    const samples = [
      { name: "Alice Smith", email: "alice.smith@cloudenterprise.io" },
      { name: "Bob Jones", email: "bob.jones@architecture.dev" },
      { name: "Charlie Brown", email: "charlie.brown@devops.org" },
      { name: "Diana Prince", email: "diana.prince@engineering.net" },
      { name: "Evan Wright", email: "evan.wright@scalabletech.com" }
    ];
    rosterTbody.innerHTML = "";
    samples.forEach(s => rosterTbody.appendChild(createRecipientRow(s.name, s.email)));
    updateRecipientCount();
    courseNameInput.value = "Advanced Cloud & Distributed Systems Certification";
  });

  // --- CSV Ingestion & Parsing ---
  csvDropzone.addEventListener("click", () => csvFileInput.click());
  csvDropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    csvDropzone.classList.add("dragover");
  });
  csvDropzone.addEventListener("dragleave", () => csvDropzone.classList.remove("dragover"));
  csvDropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    csvDropzone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleCsvFile(e.dataTransfer.files[0]);
    }
  });

  csvFileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      handleCsvFile(e.target.files[0]);
    }
  });

  function handleCsvFile(file) {
    const reader = new FileReader();
    reader.onload = (event) => {
      csvTextarea.value = event.target.result;
      parseCsvData(event.target.result);
    };
    reader.readAsText(file);
  }

  btnParseCsv.addEventListener("click", () => {
    parseCsvData(csvTextarea.value);
  });

  function parseCsvData(rawText) {
    if (!rawText.trim()) return;
    const lines = rawText.split(/\r?\n/).filter(line => line.trim().length > 0);
    let parsedCount = 0;

    lines.forEach(line => {
      // Split by comma or semicolon
      const parts = line.split(/[,;\t]/).map(p => p.trim().replace(/^["']|["']$/g, ""));
      if (parts.length >= 2) {
        const name = parts[0];
        const email = parts[1];
        if (name && email && email.includes("@")) {
          rosterTbody.appendChild(createRecipientRow(name, email));
          parsedCount++;
        }
      }
    });

    if (parsedCount > 0) {
      updateRecipientCount();
      tabBuilderBtn.click();
      showErrorBanner(`Successfully imported ${parsedCount} recipients from CSV!`, false);
    } else {
      showErrorBanner("Could not parse records. Please check the CSV format: Name, Email per line.");
    }
  }

  // Initial demo rows
  btnLoadSamples.click();

  // --- Error Banner Helper ---
  function showErrorBanner(msg, isError = true) {
    submitErrorBanner.textContent = msg;
    submitErrorBanner.className = isError ? "error-banner" : "error-banner text-success";
    submitErrorBanner.style.borderColor = isError ? "var(--danger)" : "var(--success)";
    submitErrorBanner.style.backgroundColor = isError ? "var(--danger-bg)" : "var(--success-bg)";
    submitErrorBanner.classList.remove("hidden");
  }

  function hideErrorBanner() {
    submitErrorBanner.classList.add("hidden");
  }

  // --- Form Submission (POST /api/v1/jobs/) ---
  jobForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    hideErrorBanner();

    const courseName = courseNameInput.value.trim();
    const issueDate = issueDateInput.value.trim();
    const apiKey = apiKeyInput.value.trim();

    if (!courseName || !issueDate) {
      showErrorBanner("Course title and issue date are required.");
      return;
    }

    const rows = rosterTbody.querySelectorAll("tr");
    const recipients = [];
    rows.forEach(tr => {
      const name = tr.querySelector(".row-name").value.trim();
      const email = tr.querySelector(".row-email").value.trim();
      if (name && email) {
        recipients.push({ name, email });
      }
    });

    if (recipients.length === 0) {
      showErrorBanner("Please provide at least one recipient with both name and email.");
      return;
    }

    // Set Loading State
    btnSubmitJob.disabled = true;
    submitSpinner.classList.remove("hidden");
    submitBtnText.textContent = "Dispatching Job...";

    try {
      const res = await fetch("/api/v1/jobs/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": apiKey
        },
        body: JSON.stringify({
          course_name: courseName,
          issue_date: issueDate,
          recipients: recipients
        })
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        if (res.status === 429) {
          throw new Error("Rate limit exceeded (Maximum 5 requests per minute). Please wait a moment.");
        } else if (res.status === 401) {
          throw new Error("Authentication failed: Invalid or missing API Key.");
        } else {
          throw new Error(errorData.detail || errorData.error || `Server responded with status ${res.status}`);
        }
      }

      const jobData = await res.json();
      saveJobToHistory(jobData.job_id, courseName, recipients.length);
      startJobMonitoring(jobData.job_id);

    } catch (err) {
      showErrorBanner(err.message);
    } finally {
      btnSubmitJob.disabled = false;
      submitSpinner.classList.add("hidden");
      submitBtnText.textContent = "🚀 Dispatch Certificate Job";
    }
  });

  // --- Live Job Monitoring ---
  function startJobMonitoring(jobId) {
    activeJobId = jobId;
    if (pollIntervalId) clearInterval(pollIntervalId);

    // Switch Monitor Panel from Idle to Active
    monitorIdleState.classList.add("hidden");
    monitorActiveState.classList.remove("hidden");

    activeJobIdEl.textContent = jobId;
    progressBarFill.style.width = "0%";
    progressPercentLabel.textContent = "0%";
    metricTotal.textContent = "0";
    metricSuccess.textContent = "0";
    metricFailed.textContent = "0";
    btnDownloadZip.classList.add("disabled");
    btnDownloadZip.disabled = true;
    updateMonitorBadge("PENDING");

    // Immediate poll, then set interval
    pollJobStatus();
    pollIntervalId = setInterval(pollJobStatus, 1200);
  }

  async function pollJobStatus() {
    if (!activeJobId) return;
    const apiKey = apiKeyInput.value.trim();

    try {
      const res = await fetch(`/api/v1/jobs/${activeJobId}`, {
        headers: { "X-API-Key": apiKey }
      });

      if (!res.ok) {
        if (res.status === 404) {
          stopJobMonitoring();
          showErrorBanner("Monitored job was not found on the server.");
        }
        return;
      }

      const job = await res.json();
      updateMonitorUI(job);
      fetchJobCertificates(activeJobId);

      // Stop polling when reached a terminal state
      if (["COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED"].includes(job.status)) {
        stopJobMonitoring();
      }
    } catch (err) {
      console.error("Status polling failed:", err);
    }
  }

  function stopJobMonitoring() {
    if (pollIntervalId) {
      clearInterval(pollIntervalId);
      pollIntervalId = null;
    }
  }

  function updateMonitorUI(job) {
    updateMonitorBadge(job.status);
    progressBarFill.style.width = `${job.progress_percent}%`;
    progressPercentLabel.textContent = `${job.progress_percent}%`;

    metricTotal.textContent = job.total;
    metricSuccess.textContent = job.succeeded;
    metricFailed.textContent = job.failed;

    if (job.succeeded > 0) {
      btnDownloadZip.classList.remove("disabled");
      btnDownloadZip.disabled = false;
    }
  }

  function updateMonitorBadge(status) {
    let cls = "badge-idle";
    let text = status;

    switch (status) {
      case "PENDING":
        cls = "badge-pending";
        break;
      case "PROCESSING":
        cls = "badge-processing";
        break;
      case "COMPLETED":
        cls = "badge-completed";
        text = "COMPLETED";
        break;
      case "COMPLETED_WITH_ERRORS":
        cls = "badge-completed-errors";
        text = "PARTIAL ERRORS";
        break;
      case "FAILED":
        cls = "badge-failed";
        break;
    }

    monitorStatusBadge.innerHTML = `<span class="badge ${cls}">${text}</span>`;
  }

  // --- Fetch Certificates Roster ---
  async function fetchJobCertificates(jobId) {
    const apiKey = apiKeyInput.value.trim();
    try {
      const res = await fetch(`/api/v1/jobs/${jobId}/certificates?page=1&page_size=100`, {
        headers: { "X-API-Key": apiKey }
      });
      if (res.ok) {
        const data = await res.json();
        cachedCertificates = data.items || [];
        renderCertificatesTable();
      }
    } catch (err) {
      console.error("Failed fetching certificates:", err);
    }
  }

  resultsFilterSelect.addEventListener("change", renderCertificatesTable);

  function renderCertificatesTable() {
    const filter = resultsFilterSelect.value;
    resultsTableWrapper.innerHTML = "";

    const items = cachedCertificates.filter(c => {
      if (filter === "ALL") return true;
      return c.status === filter;
    });

    if (items.length === 0) {
      resultsTableWrapper.innerHTML = `
        <tr>
          <td colspan="4" style="text-align: center; color: var(--text-dim); padding: 1.5rem;">
            No records matching the filter.
          </td>
        </tr>
      `;
      return;
    }

    items.forEach(c => {
      const tr = document.createElement("tr");

      let statusBadge = `<span class="badge badge-pending">PENDING</span>`;
      if (c.status === "SUCCESS") {
        statusBadge = `<span class="badge badge-completed">SUCCESS</span>`;
      } else if (c.status === "FAILED") {
        statusBadge = `<span class="badge badge-failed">FAILED</span>`;
      }

      let actionCell = `<span style="color: var(--text-dim); font-size: 0.75rem;">Generating...</span>`;
      if (c.status === "SUCCESS") {
        actionCell = `
          <button type="button" class="btn-download-cert" data-cert-id="${c.id}" title="Download PDF">
            ⬇️ Download PDF
          </button>
        `;
      } else if (c.status === "FAILED") {
        actionCell = `<span class="cert-error-pill" title="${escapeHtml(c.error_message || 'Rendering failed')}">${escapeHtml(c.error_message || 'Failed')}</span>`;
      }

      tr.innerHTML = `
        <td><strong>${escapeHtml(c.recipient_name)}</strong></td>
        <td><span class="font-mono" style="font-size: 0.78rem;">${escapeHtml(c.recipient_email)}</span></td>
        <td>${statusBadge}</td>
        <td>${actionCell}</td>
      `;

      // Handle PDF download button click
      const downloadBtn = tr.querySelector(".btn-download-cert");
      if (downloadBtn) {
        downloadBtn.addEventListener("click", () => downloadCertificatePdf(c.id, c.recipient_name));
      }

      resultsTableWrapper.appendChild(tr);
    });
  }

  // --- Secure File Downloads (Passing API Key via Fetch Blob) ---
  async function downloadCertificatePdf(certId, recipientName) {
    const apiKey = apiKeyInput.value.trim();
    try {
      const res = await fetch(`/api/v1/certificates/${certId}/download`, {
        headers: { "X-API-Key": apiKey }
      });

      if (!res.ok) {
        throw new Error(`Failed to download certificate: Status ${res.status}`);
      }

      const blob = await res.blob();
      const safeName = recipientName.replace(/[^a-zA-Z0-9]/g, "_");
      saveBlobToFile(blob, `${safeName}_certificate.pdf`);
    } catch (err) {
      alert(`Download Error: ${err.message}`);
    }
  }

  btnDownloadZip.addEventListener("click", async () => {
    if (!activeJobId || btnDownloadZip.disabled) return;
    const apiKey = apiKeyInput.value.trim();
    const originalText = btnDownloadZip.innerHTML;
    btnDownloadZip.innerHTML = `<span>⏳</span> Generating Archive...`;
    btnDownloadZip.disabled = true;

    try {
      const res = await fetch(`/api/v1/jobs/${activeJobId}/download`, {
        headers: { "X-API-Key": apiKey }
      });

      if (!res.ok) {
        throw new Error(`ZIP Archive download failed: Status ${res.status}`);
      }

      const blob = await res.blob();
      saveBlobToFile(blob, `job_${activeJobId}.zip`);
    } catch (err) {
      alert(`Download Error: ${err.message}`);
    } finally {
      btnDownloadZip.innerHTML = originalText;
      btnDownloadZip.disabled = false;
    }
  });

  function saveBlobToFile(blob, filename) {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    a.remove();
  }

  // Copy Job ID
  btnCopyJobId.addEventListener("click", () => {
    if (!activeJobId) return;
    navigator.clipboard.writeText(activeJobId).then(() => {
      btnCopyJobId.textContent = "✅";
      setTimeout(() => { btnCopyJobId.textContent = "📋"; }, 1500);
    });
  });

  // --- Recent Jobs History (localStorage) ---
  function getRecentJobs() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY_JOBS)) || [];
    } catch {
      return [];
    }
  }

  function saveJobToHistory(id, course, total) {
    const jobs = getRecentJobs().filter(j => j.id !== id);
    jobs.unshift({
      id,
      course,
      total,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    });
    localStorage.setItem(STORAGE_KEY_JOBS, JSON.stringify(jobs.slice(0, 10)));
    renderJobHistory();
  }

  function renderJobHistory() {
    const jobs = getRecentJobs();
    historyCount.textContent = jobs.length;
    historyList.innerHTML = "";

    if (jobs.length === 0) {
      historyList.innerHTML = `<div style="color: var(--text-dim); font-size: 0.75rem;">No historical jobs recorded.</div>`;
      return;
    }

    jobs.forEach(j => {
      const item = document.createElement("div");
      item.className = "history-item";
      item.innerHTML = `
        <div>
          <div class="history-course">${escapeHtml(j.course)}</div>
          <div class="history-time font-mono">${j.id.slice(0, 8)}... • ${j.total} recipients</div>
        </div>
        <div class="history-time">${j.time}</div>
      `;
      item.addEventListener("click", () => {
        startJobMonitoring(j.id);
      });
      historyList.appendChild(item);
    });
  }

  historyToggle.addEventListener("click", () => {
    historyList.classList.toggle("hidden");
    historyChevron.classList.toggle("open");
  });

  renderJobHistory();

  // Helper Escape HTML
  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
});

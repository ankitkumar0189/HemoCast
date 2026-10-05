let bloodRisks = [];
let actions = [];

function riskLevel(risk) {
  if (risk >= 85) {
    return {
      name: "Critical",
      reserveClass: "critical-text",
      pillClass: "critical-pill"
    };
  }
  if (risk >= 50) {
    return {
      name: "Elevated",
      reserveClass: "elevated-text",
      pillClass: "elevated-pill"
    };
  }
  return {
    name: "Surplus",
    reserveClass: "stable-text",
    pillClass: "stable-pill"
  };
}

function getScenarioRisk(item) {
  const surgeEl = document.getElementById("surgeSlider");
  const dropEl = document.getElementById("donationSlider");
  const yieldEl = document.getElementById("yieldSlider");

  const surge = surgeEl ? Number(surgeEl.value) : 46;
  const donationDrop = dropEl ? Number(dropEl.value) : 22;
  const donorYield = yieldEl ? Number(yieldEl.value) : 4;

  const adjustment = Math.round(
    surge * 0.18 + donationDrop * 0.15 - donorYield * 0.1
  );

  return Math.max(0, Math.min(99, (Number(item.risk) || 0) + adjustment));
}

function renderRiskTable() {
  const table = document.getElementById("riskRows");
  if (!table) return;

  const rows = bloodRisks
    .slice()
    .sort((a, b) => (b.risk || 0) - (a.risk || 0))
    .map((item) => {
      const adjustedRisk = getScenarioRisk(item);
      const level = riskLevel(adjustedRisk);

      return `
        <tr>
          <td class="facility-name">
            <b>⌖ ${item.hospital || "Unknown"}</b>
            <small>${item.location || ""}</small>
          </td>
          <td><span class="blood-type">${item.group || ""}</span></td>
          <td>
            <span class="reserve ${level.reserveClass}">
              ${Number(item.reserve || 0).toFixed(1)}h
              <small class="units">${item.units || 0} units</small>
            </span>
          </td>
          <td>${item.demand || 0}</td>
          <td>
            <span class="risk-pill ${level.pillClass}">
              ${adjustedRisk}% · ${level.name}
            </span>
          </td>
        </tr>
      `;
    });

  table.innerHTML = rows.join("") || `<tr><td colspan="5">No stock data received.</td></tr>`;
  updateSummary();
}

async function loadInventory() {
  const table = document.getElementById("riskRows");
  try {
    const response = await fetch("/api/inventory");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    bloodRisks = await response.json();
    renderRiskTable();
  } catch (error) {
    console.error("Could not load inventory:", error);
    if (table) {
      table.innerHTML = `<tr><td colspan="5" style="color:var(--pink);">Failed to connect to /api/inventory. Verify server.py is running.</td></tr>`;
    }
  }
}

async function loadCoordinationQueue() {
  try {
    const res = await fetch("/api/coordination");
    if (res.ok) {
      actions = await res.json();
      renderQueue();
    }
  } catch (err) {
    console.warn("Could not load /api/coordination:", err);
  }
}

function updateSummary() {
  const highRiskHospitals = new Set(
    bloodRisks
      .filter((item) => getScenarioRisk(item) >= 50)
      .map((item) => item.hospital)
  );

  const criticalGroups = new Set(
    bloodRisks
      .filter((item) => Number(item.reserve) < 18)
      .map((item) => item.group)
  );

  const pending = actions.filter((a) => a.status === "Dispatch").length;

  const hrEl = document.getElementById("highRiskCenters");
  const cgEl = document.getElementById("criticalGroups");
  const ptEl = document.getElementById("pendingTransfers");

  if (hrEl) hrEl.textContent = String(highRiskHospitals.size).padStart(2, "0");
  if (cgEl) cgEl.textContent = String(criticalGroups.size).padStart(2, "0");
  if (ptEl) ptEl.textContent = String(pending).padStart(2, "0");
}

function renderQueue() {
  const queue = document.getElementById("queueList");
  if (!queue) return;

  if (!actions || !actions.length) {
    queue.innerHTML = `
      <div class="queue-copy">
        <small style="padding: 16px; display: block; color: var(--muted);">
          All hospital nodes within safety margins. No transfers recommended.
        </small>
      </div>`;
    updateSummary();
    return;
  }

  queue.innerHTML = actions.map((action, index) => `
    <div class="queue-item">
      <i class="queue-dot ${action.priority || ''}"></i>
      <div class="queue-copy">
        <b>${action.title || 'Buffer Transfer'}</b>
        <small>${action.fromHospital} → ${action.toHospital} · ${action.eta || 'ASAP'}</small>
      </div>
      <span class="units-tag">${action.group} · ${action.units} units</span>
      <button class="dispatch-button" data-action="${index}" ${action.status !== 'Dispatch' ? 'disabled' : ''}>
        ${action.status}
      </button>
    </div>
  `).join("");

  queue.querySelectorAll(".dispatch-button").forEach((button) => {
    button.addEventListener("click", () => sendTransfer(button));
  });

  updateSummary();
}

async function sendTransfer(button) {
  const actionIdx = Number(button.dataset.action);
  const action = actions[actionIdx];

  if (!action) return;

  button.disabled = true;
  button.textContent = "Sending...";

  const apiGroup = String(action.group).replace(/[−–—]/g, "-").trim();

  try {
    const response = await fetch("/api/transfer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        group: apiGroup,
        fromHospital: action.fromHospital,
        toHospital: action.toHospital,
        units: Number(action.units)
      })
    });

    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || "Transfer failed.");
    }

    action.status = "In transit";
    renderQueue();
    await loadInventory();
    await loadCoordinationQueue();
  } catch (error) {
    console.error("Transfer error:", error);
    button.disabled = false;
    button.textContent = "Retry";
    alert("Transfer failed: " + error.message);
  }
}

function drawChart(surge, donationDrop, donorYield) {
  const demandLine = document.getElementById("demandLine");
  const supplyLine = document.getElementById("supplyLine");
  const bufferLine = document.getElementById("bufferLine");
  const demandArea = document.getElementById("demandArea");

  if (!demandLine || !supplyLine) return;

  const demandBase = [670, 705, 742, 780, 818, 850, 880];
  const supplyBase = [455, 450, 441, 430, 420, 412, 400];

  const demand = demandBase.map((val) => Math.min(980, val + surge * 2.1));
  const supply = supplyBase.map((val) => Math.max(180, val - donationDrop * 1.25 + donorYield * 0.8));

  function makePoints(values) {
    return values.map((val, idx) => ({
      x: 10 + idx * 96,
      y: 250 - (val / 1000) * 235
    }));
  }

  function pointsToString(points) {
    return points.map((p) => `${p.x},${p.y}`).join(" ");
  }

  const demandPoints = makePoints(demand);
  const supplyPoints = makePoints(supply);

  demandLine.setAttribute("points", pointsToString(demandPoints));
  supplyLine.setAttribute("points", pointsToString(supplyPoints));
  if (bufferLine) bufferLine.setAttribute("points", "0,140 600,140");

  if (demandArea && demandPoints.length > 0) {
    const first = demandPoints[0];
    const last = demandPoints[demandPoints.length - 1];
    const areaPath = [
      `M ${first.x},${first.y}`,
      ...demandPoints.slice(1).map((p) => `L ${p.x},${p.y}`),
      `L ${last.x},260`,
      `L ${first.x},260`,
      "Z"
    ].join(" ");
    demandArea.setAttribute("d", areaPath);
  }
}

function recalculate() {
  const surgeEl = document.getElementById("surgeSlider");
  const dropEl = document.getElementById("donationSlider");
  const yieldEl = document.getElementById("yieldSlider");

  const surge = surgeEl ? Number(surgeEl.value) : 46;
  const donationDrop = dropEl ? Number(dropEl.value) : 22;
  const donorYield = yieldEl ? Number(yieldEl.value) : 4;

  const sv = document.getElementById("surgeValue");
  const dv = document.getElementById("donationValue");
  const yv = document.getElementById("yieldValue");

  if (sv) sv.textContent = `${surge}%`;
  if (dv) dv.textContent = `${donationDrop}%`;
  if (yv) yv.textContent = `${donorYield}%`;

  const probability = Math.min(
    99,
    Math.max(8, 38 + surge * 0.58 + donationDrop * 0.42 - donorYield * 0.35)
  );

  const sp = document.getElementById("shortageProbability");
  const wt = document.getElementById("warningText");

  if (sp) sp.textContent = `${probability.toFixed(1)}%`;
  if (wt) wt.textContent = `The model sees a ${probability.toFixed(1)}% chance of at least one blood group reaching critical reserve within 48 hours.`;

  drawChart(surge, donationDrop, donorYield);

  if (bloodRisks.length > 0) {
    renderRiskTable();
  }
}

// -------------------------------------------------------------
// Interactive Control Listeners
// -------------------------------------------------------------
const recalcBtn = document.getElementById("recalculateButton");
if (recalcBtn) {
  recalcBtn.onclick = () => {
    recalculate();
    const wt = document.getElementById("warningTitle");
    if (wt) wt.textContent = "Scenario recalculated: review recommended actions";
  };
}

const refreshBtn = document.getElementById("refreshButton");
if (refreshBtn) {
  refreshBtn.onclick = async () => {
    refreshBtn.textContent = "⟳ Refreshing...";
    await loadInventory();
    await loadCoordinationQueue();
    recalculate();
    refreshBtn.textContent = "⟳ Refresh";
  };
}

const queueRef = document.getElementById("queueRefresh");
if (queueRef) {
  queueRef.onclick = loadCoordinationQueue;
}

document.querySelectorAll("input[type='range']").forEach((slider) => {
  slider.oninput = recalculate;
});

document.querySelectorAll("[data-scenario]").forEach((button) => {
  button.onclick = () => {
    document.querySelectorAll("[data-scenario]").forEach((item) => item.classList.remove("selected"));
    button.classList.add("selected");

    const presets = {
      baseline: [10, 8, 22],
      mass: [85, 15, 5],
      holiday: [28, 65, 10],
      storm: [46, 22, 4]
    };

    const [surge, donation, donor] = presets[button.dataset.scenario] || [46, 22, 4];
    const s = document.getElementById("surgeSlider");
    const d = document.getElementById("donationSlider");
    const y = document.getElementById("yieldSlider");

    if (s) s.value = surge;
    if (d) d.value = donation;
    if (y) y.value = donor;

    recalculate();
  };
});

// Diagnostic plot tab navigation
const plotImg = document.getElementById("modelPlotImage");
const btnConfusion = document.getElementById("btnConfusion");
const btnRoc = document.getElementById("btnRoc");
const btnFeatures = document.getElementById("btnFeatures");
const chartTitle = document.getElementById("activeChartTitle");

function selectPlotTab(activeBtn, imgPath, title) {
  [btnConfusion, btnRoc, btnFeatures].forEach((b) => b && b.classList.remove("selected"));
  if (activeBtn) activeBtn.classList.add("selected");
  if (plotImg) plotImg.src = `${imgPath}?t=${Date.now()}`;
  if (chartTitle) chartTitle.textContent = title;
}

if (btnConfusion) {
  btnConfusion.onclick = () => selectPlotTab(btnConfusion, "/outputs/confusion_matrix.png", "Confusion Matrix");
}
if (btnRoc) {
  btnRoc.onclick = () => selectPlotTab(btnRoc, "/outputs/roc_curves.png", "Multiclass ROC Curves");
}
if (btnFeatures) {
  btnFeatures.onclick = () => selectPlotTab(btnFeatures, "/outputs/feature_importance.png", "Feature Importance Ranking");
}

// -------------------------------------------------------------
// Registration Modal & Submission Logic
// -------------------------------------------------------------
const regModal = document.getElementById("registerModal");
const openModalBtn = document.getElementById("openRegisterModal");
const closeModalBtn = document.getElementById("closeRegisterModal");

const tabHosp = document.getElementById("tabHospitalBtn");
const tabDonor = document.getElementById("tabDonorBtn");
const hospForm = document.getElementById("hospitalForm");
const donorForm = document.getElementById("donorForm");
const modalTitle = document.getElementById("modalTitle");

if (openModalBtn && regModal) {
  openModalBtn.onclick = () => { regModal.style.display = "flex"; };
}

if (closeModalBtn && regModal) {
  closeModalBtn.onclick = () => { regModal.style.display = "none"; };
}

window.addEventListener("click", (e) => {
  if (e.target === regModal) regModal.style.display = "none";
});

if (tabHosp && tabDonor) {
  tabHosp.onclick = () => {
    tabHosp.classList.add("selected");
    tabDonor.classList.remove("selected");
    if (hospForm) hospForm.style.display = "flex";
    if (donorForm) donorForm.style.display = "none";
    if (modalTitle) modalTitle.textContent = "Register Hospital / Blood Center";
  };

  tabDonor.onclick = () => {
    tabDonor.classList.add("selected");
    tabHosp.classList.remove("selected");
    if (donorForm) donorForm.style.display = "flex";
    if (hospForm) hospForm.style.display = "none";
    if (modalTitle) modalTitle.textContent = "Register Voluntary Blood Donor";
  };
}

// 1. Submit Hospital Registration
if (hospForm) {
  hospForm.onsubmit = async (e) => {
    e.preventDefault();
    const nameEl = document.getElementById("regHospName");
    const locEl = document.getElementById("regHospLocation");
    const emEl = document.getElementById("regHospEmergencies");
    const surEl = document.getElementById("regHospSurgeries");
    const omEl = document.getElementById("regHospOminus");

    if (!nameEl || !nameEl.value.trim()) {
      alert("Please enter a facility name.");
      return;
    }

    const payload = {
      name: nameEl.value.trim(),
      location: locEl ? locEl.value.trim() : "Ranchi Network",
      emergencies_24h: emEl ? Number(emEl.value) : 8,
      surgeries_48h: surEl ? Number(surEl.value) : 12,
      o_minus_units: omEl ? Number(omEl.value) : 4
    };

    try {
      const res = await fetch("/api/register/hospital", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);

      alert(data.message || "Registration successful!");
      hospForm.reset();
      if (regModal) regModal.style.display = "none";

      await loadInventory();
      await loadCoordinationQueue();
      recalculate();
    } catch (err) {
      alert("Registration failed: " + err.message);
    }
  };
}

// 2. Submit Donor Registration
if (donorForm) {
  donorForm.onsubmit = async (e) => {
    e.preventDefault();
    const nameEl = document.getElementById("regDonorName");
    const grpEl = document.getElementById("regDonorGroup");
    const phoneEl = document.getElementById("regDonorPhone");
    const locEl = document.getElementById("regDonorLocality");

    if (!nameEl || !nameEl.value.trim()) {
      alert("Please enter donor name.");
      return;
    }

    const payload = {
      name: nameEl.value.trim(),
      group: grpEl ? grpEl.value : "O-",
      phone: phoneEl ? phoneEl.value.trim() : "",
      locality: locEl ? locEl.value.trim() : "Ranchi"
    };

    try {
      const res = await fetch("/api/register/donor", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);

      alert(data.message || "Donor registered successfully!");
      donorForm.reset();
      if (regModal) regModal.style.display = "none";
    } catch (err) {
      alert("Donor registration failed: " + err.message);
    }
  };
}

// -------------------------------------------------------------
// Database Linking Hub Handlers
// -------------------------------------------------------------
const dbModal = document.getElementById("dbModal");
const openDbModalBtn = document.getElementById("openDbModal");
const closeDbModalBtn = document.getElementById("closeDbModal");

const btnPg = document.getElementById("dbTypePostgres");
const btnSqlite = document.getElementById("dbTypeSqlite");
const btnFhir = document.getElementById("dbTypeFhir");

const sqlSec = document.getElementById("sqlFieldsSection");
const sqliteSec = document.getElementById("sqliteFieldsSection");
const fhirSec = document.getElementById("fhirFieldsSection");

const hospSelect = document.getElementById("dbHospName");
const customHospDiv = document.getElementById("customHospDiv");
const btnTestConn = document.getElementById("btnTestDbConn");
const dbForm = document.getElementById("dbLinkForm");
const dbStatusAlert = document.getElementById("dbStatusAlert");

let activeProtocol = "sql";

if (openDbModalBtn && dbModal) {
  openDbModalBtn.onclick = () => { dbModal.style.display = "flex"; };
}

if (closeDbModalBtn && dbModal) {
  closeDbModalBtn.onclick = () => { dbModal.style.display = "none"; };
}

window.addEventListener("click", (e) => {
  if (e.target === dbModal) dbModal.style.display = "none";
});

if (hospSelect) {
  hospSelect.onchange = () => {
    if (customHospDiv) {
      customHospDiv.style.display = hospSelect.value === "Custom" ? "block" : "none";
    }
  };
}

function setDbTab(btn, protocol, secToShow) {
  [btnPg, btnSqlite, btnFhir].forEach(b => b && b.classList.remove("selected"));
  btn.classList.add("selected");
  activeProtocol = protocol;

  if (sqlSec) sqlSec.style.display = "none";
  if (sqliteSec) sqliteSec.style.display = "none";
  if (fhirSec) fhirSec.style.display = "none";

  if (secToShow) secToShow.style.display = "flex";
  if (dbStatusAlert) dbStatusAlert.style.display = "none";
}

if (btnPg) btnPg.onclick = () => setDbTab(btnPg, "sql", sqlSec);
if (btnSqlite) btnSqlite.onclick = () => setDbTab(btnSqlite, "sqlite", sqliteSec);
if (btnFhir) btnFhir.onclick = () => setDbTab(btnFhir, "fhir", fhirSec);

function getDbConfig() {
  if (activeProtocol === "sql") {
    return {
      uri: document.getElementById("dbConnUri").value,
      table: document.getElementById("dbTableName").value
    };
  } else if (activeProtocol === "sqlite") {
    return {
      path: document.getElementById("dbSqlitePath").value
    };
  } else if (activeProtocol === "fhir") {
    return {
      url: document.getElementById("dbFhirUrl").value,
      token: document.getElementById("dbFhirToken").value
    };
  }
  return {};
}

if (btnTestConn) {
  btnTestConn.onclick = async () => {
    btnTestConn.textContent = "⚡ Testing...";
    btnTestConn.disabled = true;

    try {
      const res = await fetch("/api/database/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          protocol: activeProtocol,
          config: getDbConfig()
        })
      });
      const result = await res.json();

      if (dbStatusAlert) {
        dbStatusAlert.style.display = "block";
        dbStatusAlert.style.background = result.success ? "rgba(16, 201, 154, 0.15)" : "rgba(255, 98, 118, 0.15)";
        dbStatusAlert.style.color = result.success ? "var(--green)" : "var(--pink)";
        dbStatusAlert.style.border = `1px solid ${result.success ? "var(--green)" : "var(--pink)"}`;
        dbStatusAlert.textContent = (result.success ? "✓ " : "✕ ") + result.message;
      }
    } catch (err) {
      alert("Test connection failed: " + err.message);
    } finally {
      btnTestConn.textContent = "⚡ Test Connection";
      btnTestConn.disabled = false;
    }
  };
}

if (dbForm) {
  dbForm.onsubmit = async (e) => {
    e.preventDefault();

    let targetHosp = hospSelect.value;
    if (targetHosp === "Custom") {
      const customName = document.getElementById("dbCustomName").value.trim();
      if (!customName) {
        alert("Please enter a custom hospital name.");
        return;
      }
      targetHosp = customName;
    }

    const payload = {
      hospital: targetHosp,
      protocol: activeProtocol,
      config: getDbConfig(),
      interval: document.getElementById("dbSyncInterval").value
    };

    try {
      const res = await fetch("/api/database/link", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to link database");

      alert(data.message);
      dbModal.style.display = "none";
      dbForm.reset();

      await loadInventory();
      await loadCoordinationQueue();
      recalculate();
    } catch (err) {
      alert("Error: " + err.message);
    }
  };
}

// Initial bootstrap
recalculate();
loadInventory();
loadCoordinationQueue();
// Stock data backend se aayega: GET /api/inventory
let bloodRisks = [];

// Demo transfer recommendations
const actions = [
  {
    priority: "red",
    title: "Priority O− replenishment",
    group: "O−",
    units: 4,
    fromHospital: "Hospital B",
    toHospital: "Hospital A",
    eta: "ETA 02h 15m",
    status: "Dispatch"
  },
  {
    priority: "",
    title: "A+ buffer transfer",
    group: "A+",
    units: 4,
    fromHospital: "Hospital B",
    toHospital: "Hospital C",
    eta: "ETA 04h 40m",
    status: "Dispatch"
  },
  {
    priority: "cyan",
    title: "AB− buffer transfer",
    group: "AB−",
    units: 4,
    fromHospital: "Hospital B",
    toHospital: "Hospital C",
    eta: "ETA Tomorrow",
    status: "Dispatch"
  }
];

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
  const surge = Number(document.getElementById("surgeSlider").value);
  const donationDrop = Number(document.getElementById("donationSlider").value);
  const donorYield = Number(document.getElementById("yieldSlider").value);

  const adjustment = Math.round(
    surge * 0.18 + donationDrop * 0.15 - donorYield * 0.1
  );

  return Math.max(0, Math.min(99, item.risk + adjustment));
}

function renderRiskTable() {
  const rows = bloodRisks
    .slice()
    .sort((a, b) => b.risk - a.risk)
    .map((item) => {
      const adjustedRisk = getScenarioRisk(item);
      const level = riskLevel(adjustedRisk);

      return `
        <tr>
          <td class="facility-name">
            <b>⌖ ${item.hospital}</b>
            <small>${item.location}</small>
          </td>
          <td><span class="blood-type">${item.group}</span></td>
          <td>
            <span class="reserve ${level.reserveClass}">
              ${Number(item.reserve).toFixed(1)}h
              <small class="units">${item.units} units</small>
            </span>
          </td>
          <td>${item.demand}</td>
          <td>
            <span class="risk-pill ${level.pillClass}">
              ${adjustedRisk}% · ${level.name}
            </span>
          </td>
        </tr>
      `;
    });

  document.getElementById("riskRows").innerHTML =
    rows.join("") || `<tr><td colspan="5">No stock data received.</td></tr>`;

  updateSummary();
}

async function loadInventory() {
  const table = document.getElementById("riskRows");

  try {
    const response = await fetch("/api/inventory");

    if (!response.ok) {
      throw new Error("Backend returned an error.");
    }

    bloodRisks = await response.json();
    renderRiskTable();
  } catch (error) {
    console.error("Could not load inventory:", error);
    table.innerHTML = `
      <tr>
        <td colspan="5">
          Backend se connect nahi hua. Check karo ki server.py chal raha hai.
        </td>
      </tr>
    `;
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

  const pending = actions.filter(
    (action) => action.status === "Dispatch"
  ).length;

  document.getElementById("highRiskCenters").textContent =
    String(highRiskHospitals.size).padStart(2, "0");

  document.getElementById("criticalGroups").textContent =
    String(criticalGroups.size).padStart(2, "0");

  document.getElementById("pendingTransfers").textContent =
    String(pending).padStart(2, "0");
}

function renderQueue() {
  const queue = document.getElementById("queueList");

  queue.innerHTML = actions.map((action, index) => `
    <div class="queue-item">
      <i class="queue-dot ${action.priority}"></i>

      <div class="queue-copy">
        <b>${action.title}</b>
        <small>
          ${action.fromHospital} → ${action.toHospital}
          · ${action.eta}
        </small>
      </div>

      <span class="units-tag">
        ${action.group} · ${action.units} units
      </span>

      <button class="dispatch-button" data-action="${index}">
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
  const action = actions[Number(button.dataset.action)];

  if (!action || action.status !== "Dispatch") {
    return;
  }

  button.disabled = true;
  button.textContent = "Sending...";

  // Backend blood-group names use a normal hyphen, e.g. O-
  const apiGroup = action.group.replace("−", "-");

  try {
    const response = await fetch("/api/transfer", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        group: apiGroup,
        fromHospital: action.fromHospital,
        toHospital: action.toHospital,
        units: action.units
      })
    });

    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.error || "Transfer failed.");
    }

    action.status = "In transit";
    renderQueue();
    await loadInventory();
  } catch (error) {
    console.error("Transfer error:", error);
    button.disabled = false;
    button.textContent = "Retry";
    alert(error.message);
  }
}

function drawChart(surge, donationDrop, donorYield) {
  const demandBase = [670, 705, 742, 780, 818, 850, 880];
  const supplyBase = [455, 450, 441, 430, 420, 412, 400];

  const demand = demandBase.map((value) =>
    Math.min(980, value + surge * 2.1)
  );

  const supply = supplyBase.map((value) =>
    Math.max(180, value - donationDrop * 1.25 + donorYield * 0.8)
  );

  function makePoints(values) {
    return values.map((value, index) => {
      const x = 10 + index * 96;
      const y = 250 - (value / 1000) * 235;
      return { x, y };
    });
  }

  function pointsToString(points) {
    return points.map((point) => `${point.x},${point.y}`).join(" ");
  }

  const demandPoints = makePoints(demand);
  const supplyPoints = makePoints(supply);

  document.getElementById("demandLine").setAttribute(
    "points",
    pointsToString(demandPoints)
  );

  document.getElementById("supplyLine").setAttribute(
    "points",
    pointsToString(supplyPoints)
  );

  document.getElementById("bufferLine").setAttribute(
    "points",
    "0,140 600,140"
  );

  const firstPoint = demandPoints[0];
  const lastPoint = demandPoints[demandPoints.length - 1];

  const areaPath = [
    `M ${firstPoint.x},${firstPoint.y}`,
    ...demandPoints.slice(1).map((point) => `L ${point.x},${point.y}`),
    `L ${lastPoint.x},260`,
    `L ${firstPoint.x},260`,
    "Z"
  ].join(" ");

  document.getElementById("demandArea").setAttribute("d", areaPath);
}

function recalculate() {
  const surge = Number(document.getElementById("surgeSlider").value);
  const donationDrop = Number(document.getElementById("donationSlider").value);
  const donorYield = Number(document.getElementById("yieldSlider").value);

  document.getElementById("surgeValue").textContent = `${surge}%`;
  document.getElementById("donationValue").textContent =
    `${donationDrop}%`;
  document.getElementById("yieldValue").textContent = `${donorYield}%`;

  const probability = Math.min(
    99,
    Math.max(
      8,
      38 + surge * 0.58 + donationDrop * 0.42 - donorYield * 0.35
    )
  );

  document.getElementById("shortageProbability").textContent =
    `${probability.toFixed(1)}%`;

  document.getElementById("warningText").textContent =
    `The model sees a ${probability.toFixed(1)}% chance of at least one blood group reaching critical reserve within 48 hours.`;

  drawChart(surge, donationDrop, donorYield);

  if (bloodRisks.length > 0) {
    renderRiskTable();
  }
}

document.querySelectorAll("[data-scenario]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-scenario]").forEach((item) => {
      item.classList.remove("selected");
    });

    button.classList.add("selected");

    const presets = {
      baseline: [10, 8, 22],
      mass: [85, 15, 5],
      holiday: [28, 65, 10],
      storm: [46, 22, 4]
    };

    const values = presets[button.dataset.scenario];
    const [surge, donation, donor] = values;

    document.getElementById("surgeSlider").value = surge;
    document.getElementById("donationSlider").value = donation;
    document.getElementById("yieldSlider").value = donor;

    recalculate();
  });
});

document.querySelectorAll("input[type='range']").forEach((slider) => {
  slider.addEventListener("input", recalculate);
});

document.getElementById("recalculateButton").addEventListener("click", () => {
  recalculate();
  document.getElementById("warningTitle").textContent =
    "Scenario recalculated: review recommended actions";
});

document.getElementById("refreshButton").addEventListener("click", async () => {
  await loadInventory();
  renderQueue();
  recalculate();
});

document.getElementById("queueRefresh").addEventListener("click", renderQueue);

// First page load
renderQueue();
recalculate();
loadInventory();
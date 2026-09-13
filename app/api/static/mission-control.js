/* MealMesh Mission Control — Phase 6 (vanilla JS).
   Renders coalition dependencies, failure impact, and recovery decisions. */
"use strict";

const KIND_COLOR = {
  driver: "#3987e5", food: "#199e70", keyholder: "#9085e9",
  van: "#c98500", site: "#e6e6e6",
};
const KIND_ICON = {
  driver: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2"/><path d="M5 11h14M12 14v5"/></svg>',
  food: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 9h14l-1 10H6L5 9zM8 9V6h8v3"/><path d="M9 13h6"/></svg>',
  keyholder: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="8" cy="10" r="3"/><path d="M10.5 12.5L18 20M15 17l2-2M17 19l2-2"/></svg>',
  van: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 15V8h12v7M15 10h3l3 3v2h-6"/><circle cx="7" cy="16.5" r="1.5"/><circle cx="17" cy="16.5" r="1.5"/></svg>',
  site: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 20V10l8-5 8 5v10"/><path d="M9 20v-6h6v6"/></svg>',
};
const KIND_LABEL = {
  driver: "Van driver", food: "Food handler", keyholder: "Site keyholder",
  van: "Food-bank van", site: "Meal site",
};
const CAP_TO_KIND = {
  van_certified_driver: "driver",
  food_handler: "food",
  site_keyholder: "keyholder",
};

// ---------------------------------------------------------------- state
const mc = {
  payload: null,         // MissionControlPayload
  fixtureData: null,     // raw fixture for re-simulation
  map: null,
  routeLayer: null,
  markerLayer: null,
  markers: {},           // volunteer_id -> L.marker
  destMarker: null,
  simSelected: new Set(),
  simulating: false,
  approvalPending: false,
  timeline: [],
};

const $ = (sel) => document.querySelector(sel);
const api = async (path, body) => {
  const res = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
};

// ---------------------------------------------------------------- init
async function init() {
  try {
    mc.fixtureData = await api("/api/mission-control/fixture");
    mc.payload = mc.fixtureData;
  } catch (e) {
    $("#mcVerdictValue").textContent = "LOAD ERROR";
    console.error("Mission control load failed:", e);
    return;
  }

  buildMap();
  buildLegend();
  render(mc.payload);
  wireEvents();
  addTimelineEvent("plan", "Initial plan loaded — SIMULATED");
}

// ---------------------------------------------------------------- map
function buildMap() {
  const map = L.map("mcMap", {
    center: [38.5816, -121.4944],
    zoom: 13,
    zoomControl: false,
    attributionControl: true,
    fadeAnimation: true,
  });
  mc.map = map;
  L.control.zoom({ position: "topright" }).addTo(map);

  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    className: "rq-basemap",
    attribution: "© OpenStreetMap contributors · positions simulated",
  }).addTo(map);

  mc.routeLayer = L.layerGroup().addTo(map);
  mc.markerLayer = L.layerGroup().addTo(map);

  const hud = $("#mcMapRegion");
  if (hud) {
    hud.innerHTML =
      '<span class="hud-k">Mission</span><span class="hud-v">Meal program</span>' +
      '<span class="hud-sep">·</span><span class="hud-v">All positions simulated</span>';
  }
}

function buildLegend() {
  const box = $("#mcMapLegend");
  if (!box) return;
  box.innerHTML = "";
  const items = [
    { k: "driver", l: "Van driver" },
    { k: "food", l: "Food handler" },
    { k: "keyholder", l: "Keyholder" },
    { k: "site", l: "Meal site" },
  ];
  items.forEach(({ k, l }) => {
    const d = document.createElement("div");
    d.className = "leg";
    d.innerHTML =
      `<span class="leg-ico" style="border-color:${KIND_COLOR[k]};color:${KIND_COLOR[k]}">${KIND_ICON[k]}</span>${l}`;
    box.appendChild(d);
  });
  // Add legend entries for confirmed/proposed
  const extra = [
    { label: "Confirmed", style: "border: 2px solid var(--good); width:10px; height:10px; border-radius:50%; background: transparent;" },
    { label: "Proposed", style: "border: 2px dashed var(--warning); width:10px; height:10px; border-radius:50%; background: transparent;" },
    { label: "SPOF", style: "border: 2px solid var(--critical); width:10px; height:10px; border-radius:50%; background: var(--critical); animation: mc-spof-pulse 2s ease-in-out infinite;" },
  ];
  extra.forEach(({ label, style }) => {
    const d = document.createElement("div");
    d.className = "leg";
    d.innerHTML = `<span style="${style}; display: inline-block;"></span>${label}`;
    box.appendChild(d);
  });
}

// ---------------------------------------------------------------- render
function render(data) {
  mc.payload = data;
  renderHeader(data);
  renderTasks(data);
  renderSimControls(data);
  renderMap(data);
  renderCounterfactual(data);
  renderSpofs(data);
  renderRecovery(data);
}

function renderHeader(data) {
  $("#mcDeadline").textContent = data.deadline_label;
  $("#mcPlanStatus").textContent = data.plan_status.toUpperCase();
  $("#mcRoles").textContent = `${data.roles_covered} / ${data.roles_required}`;

  const atRiskEl = $("#mcAtRisk");
  atRiskEl.textContent = data.tasks_at_risk;
  atRiskEl.style.color = data.tasks_at_risk > 0 ? "var(--critical)" : "var(--good)";

  $("#mcRecovery").textContent = data.recovery_summary;
  $("#mcMissionLabel").textContent = data.mission_label;

  // Verdict
  const verdict = $("#mcVerdict");
  const vv = $("#mcVerdictValue");
  if (data.risk_status === "blocked") {
    verdict.dataset.state = "critical";
    vv.textContent = "BLOCKED";
  } else if (data.risk_status === "at_risk") {
    verdict.dataset.state = "warning";
    vv.textContent = "AT RISK";
  } else if (data.tasks_at_risk > 0) {
    verdict.dataset.state = "serious";
    vv.textContent = "INCOMPLETE";
  } else {
    verdict.dataset.state = "good";
    vv.textContent = "NOMINAL";
  }

  // Map status
  const chip = $("#mcMapChip");
  const meta = $("#mcMapMeta");
  const dest = $("#mcMapDest");
  dest.textContent = data.destination_label;
  chip.dataset.state = verdict.dataset.state;
  chip.textContent = vv.textContent;
  const assigned = data.volunteers.filter(v => v.is_assigned).length;
  meta.textContent = `${assigned} assigned · ${data.tasks.length} tasks`;
}

function renderTasks(data) {
  const box = $("#mcTasks");
  box.innerHTML = "";
  data.tasks.forEach(t => {
    const status = t.is_proposed ? "proposed" : t.qualification_status;
    const el = document.createElement("div");
    el.className = "mc-task";
    el.dataset.status = status;
    el.setAttribute("role", "listitem");
    el.setAttribute("aria-label", `${t.label}: ${t.volunteer_name || "unassigned"}`);

    let volHtml = '<span class="mc-task-vol">Unassigned</span>';
    if (t.volunteer_name) {
      const icon = t.is_proposed ? "◌ " : "● ";
      volHtml = `<span class="mc-task-vol">${icon}${esc(t.volunteer_name)}${t.is_proposed ? " (proposed)" : ""}</span>`;
    }

    let depHtml = "";
    if (t.depends_on.length) {
      depHtml = `<div class="mc-task-dep">depends on: ${t.depends_on.join(", ")}</div>`;
    }

    const confirmCls = t.confirmation_status === "confirmed" ? "confirmed" : "pending";

    el.innerHTML = `
      <div class="mc-task-rail" aria-hidden="true"></div>
      <div class="mc-task-body">
        <div class="mc-task-label">${esc(t.label)}</div>
        <div class="mc-task-cap">${esc(t.required_capability)}</div>
        ${volHtml}
        ${depHtml}
      </div>
      <div class="mc-task-meta">
        <div class="mc-task-time">${t.time_window_label || ""}</div>
        ${t.volunteer_id ? `<span class="mc-task-confirm ${confirmCls}">${confirmCls}</span>` : ""}
      </div>`;
    box.appendChild(el);
  });
}

function renderSimControls(data) {
  const box = $("#mcSimControls");
  box.innerHTML = "";
  const assignedVols = data.volunteers.filter(v => v.is_assigned && v.opted_in);
  assignedVols.forEach(v => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "mc-sim-chip";
    chip.textContent = v.name.replace(" (SIMULATED)", "");
    chip.dataset.id = v.id;
    chip.dataset.spof = v.is_spof ? "true" : "false";
    chip.title = v.is_spof
      ? `⚠ Single point of failure — removing ${v.name.replace(" (SIMULATED)", "")} may block the mission`
      : `Simulate removing ${v.name.replace(" (SIMULATED)", "")}`;
    if (mc.simSelected.has(v.id)) chip.classList.add("selected");
    chip.addEventListener("click", () => toggleSimSelection(v.id));
    box.appendChild(chip);
  });
  updateSimButton();
}

function renderMap(data) {
  mc.routeLayer.clearLayers();
  mc.markerLayer.clearLayers();
  mc.markers = {};

  // Destination marker
  if (data.destination_coords) {
    const destIcon = L.divIcon({
      className: "rq-icon",
      html: `<div class="rq-marker site primary" data-kind="site"><div class="rq-dot">${KIND_ICON.site}</div><div class="rq-label">${esc(data.destination_label)}</div></div>`,
      iconSize: [36, 36], iconAnchor: [18, 18],
    });
    mc.destMarker = L.marker(data.destination_coords, {
      icon: destIcon, zIndexOffset: 100,
    }).addTo(mc.markerLayer);

    // Destination halo
    L.circle(data.destination_coords, {
      radius: 700, color: "#ec835a", weight: 1.5, opacity: 0.55,
      fillColor: "#ec835a", fillOpacity: 0.08,
      className: "rq-halo primary", interactive: false,
    }).addTo(mc.routeLayer);
  }

  // Volunteer markers
  const dest = data.destination_coords;
  data.volunteers.forEach(v => {
    if (!v.location_coords) return;
    const kind = CAP_TO_KIND[v.capability_codes[0]] || "driver";
    const classes = ["rq-marker"];
    if (v.is_assigned) classes.push("selected");
    if (v.is_proposed) classes.push("mc-marker-proposed");
    else if (v.is_assigned) classes.push("mc-marker-confirmed");
    if (v.is_spof) classes.push("mc-marker-spof");
    if (v.location_stale) classes.push("mc-marker-stale");
    if (mc.simSelected.has(v.id)) classes.push("failed");

    const shortName = v.name.replace(" (SIMULATED)", "");
    const icon = L.divIcon({
      className: "rq-icon",
      html: `<div class="${classes.join(" ")}" data-kind="${kind}"><div class="rq-dot">${KIND_ICON[kind]}</div><div class="rq-label">${esc(shortName)}</div></div>`,
      iconSize: [32, 32], iconAnchor: [16, 16],
    });

    const m = L.marker(v.location_coords, {
      icon, interactive: true, zIndexOffset: v.is_spof ? 400 : 200,
    }).addTo(mc.markerLayer);

    // Tooltip with privacy-aware info
    let tip = `<b>${esc(shortName)}</b><br>`;
    tip += `${v.capability_codes.join(", ")}<br>`;
    if (v.travel_label) tip += `ETA: ${v.travel_label}<br>`;
    if (v.is_spof) tip += `<span style="color:#ffb4b4">⚠ Single point of failure</span><br>`;
    if (v.is_proposed) tip += `<i>Proposed assignment — not yet approved</i><br>`;
    tip += `<i>Location: ${esc(v.location_label)}${v.location_stale ? " (stale)" : ""}</i>`;
    m.bindTooltip(tip, { direction: "top", className: "rq-tip" });

    mc.markers[v.id] = m;

    // Routes to destination
    if (dest && v.is_assigned) {
      const color = KIND_COLOR[kind] || "#3987e5";
      if (v.is_proposed) {
        // Dashed route for proposed assignments
        L.polyline([v.location_coords, dest], {
          color, weight: 2.5, opacity: 0.45, dashArray: "6 10",
          className: "mc-route-proposed", interactive: false, lineCap: "round",
        }).addTo(mc.routeLayer);
      } else {
        // Solid glow + animated dash for confirmed
        L.polyline([v.location_coords, dest], {
          color, weight: 10, opacity: 0.12, interactive: false, lineCap: "round",
        }).addTo(mc.routeLayer);
        L.polyline([v.location_coords, dest], {
          color, weight: 2.75, opacity: 0.95, dashArray: "8 12",
          className: "rq-route-flow", interactive: false, lineCap: "round",
        }).addTo(mc.routeLayer);
      }
    }
  });

  // Fit bounds
  const pts = data.volunteers
    .filter(v => v.location_coords)
    .map(v => v.location_coords);
  if (data.destination_coords) pts.push(data.destination_coords);
  if (pts.length > 1) mc.map.fitBounds(pts, { padding: [48, 48], maxZoom: 14 });
}

function renderCounterfactual(data) {
  const box = $("#mcCounterfactual");
  box.innerHTML = "";
  if (!data.counterfactual_scenarios || data.counterfactual_scenarios.length === 0) {
    box.innerHTML = '<div class="mc-tl-empty">No counterfactual data</div>';
    return;
  }
  data.counterfactual_scenarios.forEach(s => {
    const el = document.createElement("div");
    el.className = "mc-cf-item";
    el.dataset.status = s.recovery_status;
    el.setAttribute("role", "listitem");
    el.setAttribute("aria-label",
      `${s.removed_resource_name}: ${s.recovery_status}`);

    const shortName = s.removed_resource_name.replace(" (SIMULATED)", "");
    el.innerHTML = `
      <div class="mc-cf-dot" aria-hidden="true"></div>
      <div>
        <div class="mc-cf-name">${esc(shortName)}</div>
        <div class="mc-cf-impact">${esc(s.mission_impact)}</div>
      </div>
      <span class="mc-cf-tag">${s.recovery_status}</span>`;
    box.appendChild(el);
  });
}

function renderSpofs(data) {
  const box = $("#mcSpofs");
  box.innerHTML = "";
  if (!data.single_points_of_failure.length) {
    box.innerHTML = '<div class="mc-tl-empty" style="color:var(--good)">No single points of failure identified</div>';
    return;
  }
  data.single_points_of_failure.forEach(id => {
    const vol = data.volunteers.find(v => v.id === id);
    const name = vol ? vol.name.replace(" (SIMULATED)", "") : id;
    const caps = vol ? vol.capability_codes.join(", ") : "";
    const el = document.createElement("div");
    el.className = "mc-spof-item";
    el.setAttribute("role", "alert");
    el.setAttribute("aria-label", `${name} is a single point of failure`);
    el.innerHTML = `
      <div class="mc-spof-icon" aria-hidden="true">!</div>
      <span class="mc-spof-name">${esc(name)}</span>
      <span class="mc-spof-detail">${esc(caps)}</span>`;
    box.appendChild(el);
  });
}

function renderRecovery(data) {
  const card = $("#mcRecoveryCard");
  const content = $("#mcRecoveryContent");
  const actions = $("#mcRecoveryActions");
  const status = $("#mcRecoveryStatus");

  if (!data.recovery) {
    card.hidden = true;
    return;
  }
  card.hidden = false;
  const r = data.recovery;

  status.textContent = r.is_feasible ? "FEASIBLE" : "INFEASIBLE";
  status.className = "sub mc-recovery-status " + (r.is_feasible ? "feasible" : "infeasible");

  let html = "";

  // What changed
  html += `<div class="mc-recovery-section">
    <div class="mc-recovery-section-label">What Changed</div>
    <div>${esc(r.what_changed)}</div>
  </div>`;

  // Assignment diff
  if (r.changes.length) {
    html += '<div class="mc-recovery-section"><div class="mc-recovery-section-label">Assignment Changes</div>';
    r.changes.forEach(c => {
      const icons = { replaced: "↻", unchanged: "=", removed: "−", added: "+" };
      const before = c.before_volunteer_name ? c.before_volunteer_name.replace(" (SIMULATED)", "") : "—";
      const after = c.after_volunteer_name ? c.after_volunteer_name.replace(" (SIMULATED)", "") : "—";
      let detail = "";
      if (c.change_type === "replaced") detail = `${before} → ${after}`;
      else if (c.change_type === "unchanged") detail = before;
      else if (c.change_type === "removed") detail = `${before} removed`;
      else if (c.change_type === "added") detail = `${after} added`;

      html += `<div class="mc-change-row" data-type="${c.change_type}">
        <span class="mc-change-icon">${icons[c.change_type] || "?"}</span>
        <span class="mc-change-task">${esc(c.task_label)}</span>
        <span class="mc-change-detail">${esc(detail)}</span>
      </div>`;
    });
    html += "</div>";
  }

  // Capability gaps
  if (r.capability_gaps.length) {
    html += '<div class="mc-recovery-section"><div class="mc-recovery-section-label">Capability Gaps</div>';
    html += '<ul class="mc-gap-list">';
    r.capability_gaps.forEach(g => { html += `<li>${esc(g)}</li>`; });
    html += "</ul></div>";
  }

  // Safe actions
  if (r.safe_actions.length) {
    html += '<div class="mc-recovery-section"><div class="mc-recovery-section-label">Safe Actions</div>';
    r.safe_actions.forEach(a => { html += `<div style="font-size:11px;color:var(--ink-2);padding:2px 0">${esc(a)}</div>`; });
    html += "</div>";
  }

  // Pending confirmations
  if (r.pending_confirmations.length) {
    html += `<div class="mc-recovery-section">
      <div class="mc-recovery-section-label">Pending Confirmations</div>
      <div style="font-size:11px;color:var(--warning)">${r.pending_confirmations.length} volunteer(s) need to accept</div>
    </div>`;
  }

  // Targeted request
  if (r.targeted_request) {
    html += `<div class="mc-recovery-section">
      <div class="mc-recovery-section-label">Targeted Request</div>
      <div style="font-size:11px;color:var(--ink-2)">${esc(r.targeted_request)}</div>
    </div>`;
  }

  // Expiration
  if (r.expires_label) {
    html += `<div style="font-size:10px;color:var(--muted);margin-top:4px">Expires: ${esc(r.expires_label)}</div>`;
  }

  content.innerHTML = html;

  // Show actions only for feasible proposals
  actions.hidden = !r.is_feasible;
}

// ---------------------------------------------------------------- simulation
function toggleSimSelection(id) {
  if (mc.simSelected.has(id)) mc.simSelected.delete(id);
  else mc.simSelected.add(id);

  // Update chip visuals
  document.querySelectorAll(".mc-sim-chip").forEach(chip => {
    chip.classList.toggle("selected", mc.simSelected.has(chip.dataset.id));
  });
  updateSimButton();

  // Update marker visuals immediately
  if (mc.markers[id]) {
    const el = mc.markers[id].getElement();
    if (el) {
      const marker = el.querySelector(".rq-marker");
      if (marker) marker.classList.toggle("failed", mc.simSelected.has(id));
    }
  }
}

function updateSimButton() {
  const btn = $("#mcSimBtn");
  btn.disabled = mc.simSelected.size === 0 || mc.simulating;
  btn.textContent = mc.simSelected.size
    ? `Simulate Removal (${mc.simSelected.size})`
    : "Simulate Removal";
}

async function runSimulation() {
  if (mc.simSelected.size === 0 || mc.simulating) return;
  mc.simulating = true;
  updateSimButton();

  const resultEl = $("#mcSimResult");
  resultEl.hidden = false;
  resultEl.dataset.status = "evaluating";
  resultEl.textContent = "Evaluating impact and searching for recovery…";

  const removedNames = [...mc.simSelected].map(id => {
    const v = mc.payload.volunteers.find(x => x.id === id);
    return v ? v.name.replace(" (SIMULATED)", "") : id;
  });
  addTimelineEvent("removal", `SIMULATION: removed ${removedNames.join(", ")}`);

  try {
    // Use cached fixture raw data for simulation
    const raw = mc.fixtureData;
    const simPayload = await api("/api/mission-control/simulate-removal", {
      mission: raw._raw_mission,
      volunteers: raw._raw_volunteers,
      vehicles: raw._raw_vehicles,
      plan: raw._raw_plan,
      removed_resource_ids: [...mc.simSelected],
    });

    // If the API returned a direct payload (which it does), render it
    if (simPayload.mission_id) {
      render(simPayload);

      if (simPayload.risk_status === "blocked") {
        resultEl.dataset.status = "infeasible";
        resultEl.textContent = "⛔ No recovery possible — " + (simPayload.risk_reason || "mission blocked");
        addTimelineEvent("recovery", "Recovery: INFEASIBLE — mission blocked");
      } else {
        resultEl.dataset.status = "recovered";
        resultEl.textContent = "Recovery proposal generated — review in the right panel";
        addTimelineEvent("recovery", "Recovery: FEASIBLE — proposal generated");
      }
    } else {
      resultEl.dataset.status = "infeasible";
      resultEl.textContent = simPayload.error || "Simulation failed";
    }
  } catch (e) {
    resultEl.dataset.status = "infeasible";
    resultEl.textContent = "Simulation error: " + e.message;
  } finally {
    mc.simulating = false;
    updateSimButton();
  }
}

function resetSimulation() {
  mc.simSelected.clear();
  mc.simulating = false;
  mc.approvalPending = false;
  $("#mcSimResult").hidden = true;

  addTimelineEvent("plan", "Simulation reset — original plan restored");

  // Reload original fixture
  api("/api/mission-control/fixture")
    .then(data => render(data))
    .catch(e => console.error("Reset failed:", e));
}

// ---------------------------------------------------------------- approval (demo)
function handleApprove() {
  if (mc.approvalPending) return;
  mc.approvalPending = true;
  $("#mcApproveBtn").disabled = true;
  $("#mcRejectBtn").disabled = true;

  addTimelineEvent("approval", "Recovery proposal APPROVED by coordinator (SIMULATED)");

  // Update visuals: proposed -> confirmed
  if (mc.payload) {
    mc.payload.volunteers.forEach(v => {
      if (v.is_proposed) {
        v.is_proposed = false;
        v.is_assigned = true;
      }
    });
    mc.payload.tasks.forEach(t => {
      if (t.is_proposed) t.is_proposed = false;
    });
    mc.payload.risk_status = "nominal";
    mc.payload.plan_status = "approved";
    render(mc.payload);
  }

  const resultEl = $("#mcSimResult");
  resultEl.dataset.status = "recovered";
  resultEl.textContent = "✓ Recovery activated — plan is now APPROVED";
  $("#mcRecoveryActions").hidden = true;

  setTimeout(() => {
    mc.approvalPending = false;
    $("#mcApproveBtn").disabled = false;
    $("#mcRejectBtn").disabled = false;
  }, 1000);
}

function handleReject() {
  addTimelineEvent("rejected", "Recovery proposal REJECTED by coordinator");
  $("#mcRecoveryCard").hidden = true;
  const resultEl = $("#mcSimResult");
  resultEl.dataset.status = "infeasible";
  resultEl.textContent = "Recovery proposal rejected — awaiting new proposal or manual intervention";
}

function handleCompare() {
  // Show the changes side-by-side in an alert (simple demo)
  if (!mc.payload || !mc.payload.recovery) return;
  const r = mc.payload.recovery;
  const lines = r.changes.map(c => {
    const before = c.before_volunteer_name || "—";
    const after = c.after_volunteer_name || "—";
    return `${c.task_label}: ${c.change_type} (${before} → ${after})`;
  });
  alert("Assignment Comparison:\n\n" + lines.join("\n"));
}

// ---------------------------------------------------------------- timeline
function addTimelineEvent(kind, text) {
  const now = new Date();
  mc.timeline.push({ kind, text, time: now });
  renderTimeline();
}

function renderTimeline() {
  const box = $("#mcTimeline");
  box.innerHTML = "";
  mc.timeline.forEach((evt, i) => {
    const row = document.createElement("div");
    row.className = "mc-tl-row";
    row.dataset.kind = evt.kind;
    row.innerHTML = `
      <div class="mc-tl-dot" aria-hidden="true"></div>
      <div>
        <div class="mc-tl-text">${esc(evt.text)}</div>
        <div class="mc-tl-time">${evt.time.toLocaleTimeString()}</div>
      </div>`;
    box.appendChild(row);
    if (i < mc.timeline.length - 1) {
      const line = document.createElement("div");
      line.className = "mc-tl-line";
      box.appendChild(line);
    }
  });
  box.scrollTop = box.scrollHeight;
}

// ---------------------------------------------------------------- events
function wireEvents() {
  $("#mcSimBtn").addEventListener("click", runSimulation);
  $("#mcSimReset").addEventListener("click", resetSimulation);

  const approveBtn = $("#mcApproveBtn");
  const rejectBtn = $("#mcRejectBtn");
  const compareBtn = $("#mcCompareBtn");
  if (approveBtn) approveBtn.addEventListener("click", handleApprove);
  if (rejectBtn) rejectBtn.addEventListener("click", handleReject);
  if (compareBtn) compareBtn.addEventListener("click", handleCompare);
}

// ---------------------------------------------------------------- utils
function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// ---------------------------------------------------------------- boot
init();

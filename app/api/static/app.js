/* MealMesh dashboard logic (vanilla JS). */
"use strict";

const KIND_COLOR = {
  driver: "#3987e5", food: "#199e70", keyholder: "#9085e9",
  van: "#c98500", site: "#e6e6e6",
};
// Crisp SVG glyphs (no emoji) — reads cleaner on a judge-facing ops map.
const KIND_ICON = {
  driver: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2"/><path d="M5 11h14M12 14v5"/></svg>',
  food: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 9h14l-1 10H6L5 9zM8 9V6h8v3"/><path d="M9 13h6"/></svg>',
  keyholder: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="8" cy="10" r="3"/><path d="M10.5 12.5L18 20M15 17l2-2M17 19l2-2"/></svg>',
  van: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 15V8h12v7M15 10h3l3 3v2h-6"/><circle cx="7" cy="16.5" r="1.5"/><circle cx="17" cy="16.5" r="1.5"/></svg>',
  site: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 20V10l8-5 8 5v10"/><path d="M9 20v-6h6v6"/></svg>',
  target: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="3"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2"/></svg>',
};
const KIND_LABEL = {
  driver: "Van driver", food: "Food handler", keyholder: "Site keyholder",
  van: "Food-bank van", site: "Meal site",
};

const state = {
  scenario: null,
  mission: null,      // mission dict currently being planned
  minCapacity: 8,
  failed: new Set(),
  markers: {},        // resourceId -> L.marker
  resourcesById: {},  // resourceId -> resource payload (with coords)
  map: null,
  routeLayer: null,
  cy: null,
  destMarkers: [],
  activeDestMarker: null,
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
    state.scenario = await api("/api/scenario");
  } catch (e) {
    $("#msg").textContent = "Could not load scenario: " + e.message;
    return;
  }
  state.scenario.resources.forEach((r) => (state.resourcesById[r.id] = r));

  buildPresets();
  buildLegend();
  buildMap();
  buildHypergraph();
  wireEvents();

  // start on the first preset
  const first = state.scenario.presets[0];
  applyPreset(first);
}

function buildPresets() {
  const sel = $("#presetSelect");
  sel.innerHTML = "";
  state.scenario.presets.forEach((p) => {
    const o = document.createElement("option");
    o.value = p.id;
    o.textContent = p.label;
    sel.appendChild(o);
  });
}

function buildLegend() {
  const box = $("#legend");
  box.innerHTML = "";
  ["driver", "food", "keyholder", "van", "site"].forEach((k) => {
    const d = document.createElement("div");
    d.className = "leg";
    d.innerHTML =
      `<span class="leg-ico" style="border-color:${KIND_COLOR[k]};color:${KIND_COLOR[k]}">${KIND_ICON[k]}</span>` +
      `${KIND_LABEL[k]}`;
    box.appendChild(d);
  });
}

// Keyless fallback basemap. Carto's CDN now watermarks unauthenticated tiles,
// so the default must be a provider that needs no key. Never append api_key here.
const DEFAULT_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

// ---------------------------------------------------------------- map
function buildMap() {
  const region = state.scenario.region;
  const map = L.map("map", {
    center: region.center,
    zoom: region.zoom,
    zoomControl: false,
    attributionControl: true,
    fadeAnimation: true,
  });
  state.map = map;
  L.control.zoom({ position: "topright" }).addTo(map);

  const mapCfg = state.scenario.map || {};
  // Strip accidental auth query params client-side too (cached / old configs).
  const tileUrl = sanitizeTileUrl(mapCfg.tileUrl || DEFAULT_TILE_URL);
  L.tileLayer(tileUrl, {
    subdomains: "abcd",
    maxZoom: 19,
    className: "rq-basemap",
    attribution: mapCfg.attribution || "© OpenStreetMap contributors · positions simulated",
  }).addTo(map);

  state.routeLayer = L.layerGroup().addTo(map);
  state.haloLayer = L.layerGroup().addTo(map);
  const markerLayer = L.layerGroup().addTo(map);

  const hud = $("#mapRegion");
  if (hud) {
    hud.innerHTML =
      `<span class="hud-k">Sites</span><span class="hud-v">${region.label || "Meal program"}</span>` +
      `<span class="hud-sep">·</span><span class="hud-v">All positions simulated</span>`;
  }

  // destinations + soft pulse rings (ops-console feel)
  state.scenario.destinations.forEach((d) => {
    L.circle(d.coords, {
      radius: d.primary ? 900 : 550,
      color: d.primary ? "#ec835a" : "#898781",
      weight: 1.5,
      opacity: 0.55,
      fillColor: d.primary ? "#ec835a" : "#898781",
      fillOpacity: 0.08,
      className: d.primary ? "rq-halo primary" : "rq-halo",
      interactive: false,
    }).addTo(state.haloLayer);

    const m = L.marker(d.coords, {
      icon: divIcon("site", { site: true, primary: d.primary, label: d.name }),
      interactive: true, zIndexOffset: 100,
    }).addTo(markerLayer);
    m.bindTooltip(`<b>${d.name}</b><br>${d.population} meals · ${d.note}`, {
      direction: "top", className: "rq-tip",
    });
    state.destMarkers.push(m);
  });

  // resources
  state.scenario.resources.forEach((r) => {
    const m = L.marker([r.lat, r.lng], {
      icon: divIcon(r.kind, { label: markerLabel(r) }), interactive: true, zIndexOffset: 200,
    }).addTo(markerLayer);
    m.bindTooltip(tooltipFor(r), { direction: "top", className: "rq-tip" });
    m.on("click", () => toggleFailure(r.id));
    state.markers[r.id] = m;
  });

  const all = [
    ...state.scenario.resources.map((r) => [r.lat, r.lng]),
    ...state.scenario.destinations.map((d) => d.coords),
  ];
  map.fitBounds(all, { padding: [48, 48], maxZoom: 14 });
}

/** Free Carto CDN tiles break if api_key / JWT is appended — strip those params. */
function sanitizeTileUrl(url) {
  try {
    // Leaflet templates use {s}/{z}/{x}/{y}{r} — only scrub the query string.
    const q = url.indexOf("?");
    if (q < 0) return url;
    const base = url.slice(0, q);
    const params = new URLSearchParams(url.slice(q + 1));
    ["api_key", "apiKey", "apikey", "access_token", "token", "key"].forEach((k) => params.delete(k));
    const rest = params.toString();
    return rest ? `${base}?${rest}` : base;
  } catch (_) {
    return url;
  }
}

function tooltipFor(r) {
  const consent = r.opted_in ? "opted-in — may be auto-assigned" : "recruit only — a human must ask";
  const sites = (r.sites || []).length === state.scenario.destinations.length
    ? "on every site's roster"
    : `roster: ${(r.sites || []).join(", ") || "—"}`;
  return `<b>${r.name}</b><br>${KIND_LABEL[r.kind]} · ${r.org || "MealMesh"}<br>${consent}<br>${sites}` +
    `<br><i>click to toggle availability</i>`;
}

function divIcon(kind, opts) {
  const cls = ["rq-marker"];
  if (opts.site) cls.push("site");
  if (opts.primary) cls.push("primary");
  if (opts.selected) cls.push("selected");
  if (opts.failed) cls.push("failed");
  if (opts.offRoster) cls.push("off-roster");
  const glyph = KIND_ICON[kind] || KIND_ICON.site;
  const label = opts.label ? `<div class="rq-label">${opts.label}</div>` : "";
  const size = opts.site || kind === "target" ? 36 : 32;
  return L.divIcon({
    className: "rq-icon",
    html: `<div class="${cls.join(" ")}" data-kind="${kind}"><div class="rq-dot">${glyph}</div>${label}</div>`,
    iconSize: [size, size], iconAnchor: [size / 2, size / 2],
  });
}

function markerLabel(r) {
  return r.name;
}

function toggleFailure(id) {
  if (state.failed.has(id)) state.failed.delete(id);
  else state.failed.add(id);
  plan();
}

// ---------------------------------------------------------------- hypergraph
function buildHypergraph() {
  const elements = [];
  state.scenario.resources.forEach((r) => {
    elements.push({ data: { id: r.id, label: shortName(r.name), kind: r.kind, color: KIND_COLOR[r.kind] } });
  });
  state.scenario.hyperedges.forEach((h) => {
    elements.push({ data: { id: "he:" + h.id, label: h.emergent_capability_label, he: "1" } });
    h.resource_ids.forEach((rid) => {
      elements.push({ data: { id: `edge:${h.id}:${rid}`, source: "he:" + h.id, target: rid } });
    });
  });

  state.cy = cytoscape({
    container: $("#hypergraph"),
    elements,
    style: [
      { selector: "node", style: {
        "background-color": "data(color)", label: "data(label)", color: "#c3c2b7",
        "font-size": 8, "text-valign": "bottom", "text-margin-y": 3, width: 20, height: 20,
        "border-width": 2, "border-color": "#00000000",
      }},
      { selector: 'node[he="1"]', style: {
        shape: "round-diamond", "background-color": "#4a3aa7", width: 16, height: 16,
        color: "#9085e9", "font-size": 8,
      }},
      { selector: "edge", style: { width: 1.5, "line-color": "#2c2c2a", "curve-style": "haystack" }},
      { selector: "node.selected", style: { "border-color": "#3987e5", "border-width": 3 }},
      { selector: 'node.unit[he="1"]', style: { "background-color": "#199e70", color: "#8fe7c4" }},
      { selector: "node.failed", style: { "background-color": "#d03b3b", "border-color": "#d03b3b", opacity: 0.6 }},
      { selector: "edge.active", style: { "line-color": "#3987e5", width: 2 }},
      { selector: "edge.dead", style: { "line-color": "#3a1d1d", "line-style": "dashed" }},
    ],
    layout: { name: "cose", animate: false, padding: 12, nodeRepulsion: 6000, idealEdgeLength: 42 },
    userZoomingEnabled: false, userPanningEnabled: false, autoungrabify: true,
  });
  setTimeout(() => { state.cy.resize(); state.cy.fit(undefined, 16); }, 60);
}

function shortName(n) { return n.replace("Food Bank ", "FB "); }

// ---------------------------------------------------------------- plan
async function plan() {
  if (!state.mission) return;
  setBusy(true);
  try {
    const data = await api("/api/plan", {
      mission: state.mission,
      failed_resource_ids: [...state.failed],
      min_capacity: state.minCapacity,
    });
    render(data);
  } catch (e) {
    $("#msg").textContent = "Plan failed: " + e.message;
  } finally {
    setBusy(false);
  }
}

function setBusy(b) {
  $("#extractBtn").disabled = b;
}

function applyPreset(preset) {
  state.mission = { ...preset.mission };
  state.minCapacity = preset.min_capacity;
  state.failed.clear();
  $("#capSlider").value = preset.min_capacity;
  $("#capVal").textContent = preset.min_capacity;
  $("#msg").textContent = "";
  $("#msg").className = "msg";
  plan();
}

// ---------------------------------------------------------------- render
function render(data) {
  const r = data.result;
  renderMissionLine(r.mission);
  renderVerdict(r.verdict);
  renderBanner(r);
  renderAnswers(r);
  renderRoster(r);
  renderDestination(data.destination);
  renderMarkers(r, data.destination);
  renderFlow(r);
  renderResilience(r);
  renderHypergraph(r);
}

function renderBanner(r) {
  const banner = $("#reviewBanner");
  if (r.coalition) { banner.hidden = true; return; }
  banner.hidden = false;
  const reasons = [];
  if (r.review.missing_critical_facts.length)
    reasons.push("Missing facts: " + r.review.missing_critical_facts.join(", "));
  (r.capability_assessment.review_reasons || []).forEach((x) => reasons.push(x));
  $("#bannerTitle").textContent =
    r.review.status !== "ready" ? "⚠ Need more facts to plan" : "⚠ Human review required";
  $("#bannerList").innerHTML =
    reasons.map((x) => `<li>${x}</li>`).join("") || "<li>Not enough information to plan safely.</li>";
  $("#bannerHint").textContent =
    "Name the site and coverage window, or pick a Thursday preset.";
}

function renderDestination(destination) {
  if (state.activeDestMarker) { state.map.removeLayer(state.activeDestMarker); state.activeDestMarker = null; }
  if (!destination || !destination.coords) return;
  const approx = destination.approx;
  if (approx) {
    const cls = "rq-marker approx primary";
    const icon = L.divIcon({
      className: "rq-icon",
      html: `<div class="${cls}" data-kind="target"><div class="rq-dot">${KIND_ICON.target}</div><div class="rq-label">${destination.name} · sim</div></div>`,
      iconSize: [34, 34], iconAnchor: [17, 17],
    });
    const m = L.marker(destination.coords, { icon, zIndexOffset: 500 }).addTo(state.map);
    m.bindTooltip(`<b>${destination.name}</b><br><i>location simulated — outside the demo region</i>`, { direction: "top" });
    state.activeDestMarker = m;
  }
  state.map.panTo(destination.coords, { animate: true, duration: 0.6 });
}

function renderMissionLine(m) {
  const reqs = (m.requirements || []).join(", ") || "none";
  $("#missionLine").innerHTML =
    `<b>${m.destination || "unknown"}</b> · ${m.incident_type || "unknown"} · needs: ${reqs}`;
}

function renderVerdict(v) {
  $("#verdictValue").textContent = v;
  $("#verdict").dataset.state = verdictState(v);
}
function verdictState(v) {
  if (v === "ready to deploy") return "good";
  if (v === "ready but fragile") return "warning";
  if (v === "no feasible coalition") return "critical";
  return "serious";
}

function setAnswer(id, text, st) {
  const node = $(id);
  node.querySelector(".a-a").textContent = text;
  node.dataset.state = st;
}
function renderAnswers(r) {
  const a = r.answers;
  const canState = a.CAN.startsWith("Yes") ? "good" : a.CAN.startsWith("No") ? "critical" : "warning";
  setAnswer("#ans-can", a.CAN, canState);
  setAnswer("#ans-how", a.HOW, "info");

  let ifState = "info";
  if (r.resilience) ifState = r.resilience.overall_classification === "recoverable" ? "good" : "critical";
  setAnswer("#ans-whatif", a["WHAT IF"], ifState);

  let missState = "info";
  if (r.missing_capabilities && r.missing_capabilities.length) missState = "critical";
  else if (a["WHAT IS MISSING"].startsWith("Nothing")) missState = "good";
  else if (a["WHAT IS MISSING"].startsWith("Facts") || a["WHAT IS MISSING"].startsWith("Review")) missState = "warning";
  setAnswer("#ans-missing", a["WHAT IS MISSING"], missState);
}

const ROSTER_STATUS = {
  scheduled: { label: "scheduled", cls: "ok" },
  bench:     { label: "opted-in bench", cls: "bench" },
  recruit:   { label: "recruit only", cls: "recruit" },
  out:       { label: "cancelled", cls: "out" },
};

function rosterStatus(res, selected) {
  if (state.failed.has(res.id)) return "out";
  if (selected.has(res.id)) return "scheduled";
  return res.opted_in ? "bench" : "recruit";
}

function siteIdFor(destinationName) {
  if (!destinationName) return null;
  const match = state.scenario.destinations.find(
    (d) => d.name.toLowerCase() === String(destinationName).trim().toLowerCase()
  );
  return match ? match.id : null;
}

function renderRoster(r) {
  const box = $("#roster");
  if (!box) return;
  const selected = new Set(r && r.coalition ? r.coalition.selected_resource_ids : []);
  // Only people signed up for this site can be assigned to it, so the roster
  // shows the same pool the solver was given.
  const siteId = siteIdFor(r && r.mission ? r.mission.destination : null);
  const onRoster = (res) => !siteId || !res.sites || res.sites.includes(siteId);
  box.innerHTML = "";

  const count = state.scenario.resources.filter((res) => res.kind !== "van" && onRoster(res)).length;
  const scope = $("#rosterScope");
  if (scope) scope.textContent = `${count} signed up for this site`;

  ["driver", "food", "keyholder"].forEach((kind) => {
    const people = state.scenario.resources.filter((res) => res.kind === kind && onRoster(res));
    if (!people.length) return;
    const order = { scheduled: 0, bench: 1, recruit: 2, out: 3 };
    people.sort((a, b) => order[rosterStatus(a, selected)] - order[rosterStatus(b, selected)]);

    const group = document.createElement("div");
    group.className = "r-group";
    group.innerHTML =
      `<div class="r-head"><span class="r-ico" style="border-color:${KIND_COLOR[kind]};color:${KIND_COLOR[kind]}">` +
      `${KIND_ICON[kind]}</span>${KIND_LABEL[kind]}</div>`;

    people.forEach((res) => {
      const status = ROSTER_STATUS[rosterStatus(res, selected)];
      const row = document.createElement("button");
      row.className = `r-row ${status.cls}`;
      row.type = "button";
      row.title = "Click to toggle this volunteer's availability";
      row.innerHTML =
        `<span class="r-name">${res.name}</span>` +
        `<span class="r-org">${res.org || "MealMesh"}</span>` +
        `<span class="r-chip">${status.label}</span>`;
      row.addEventListener("click", () => toggleFailure(res.id));
      group.appendChild(row);
    });
    box.appendChild(group);
  });
}

function renderMarkers(r, destination) {
  const selected = new Set(r.coalition ? r.coalition.selected_resource_ids : []);
  const siteId = siteIdFor(r.mission ? r.mission.destination : null);
  Object.entries(state.markers).forEach(([id, m]) => {
    const res = state.resourcesById[id];
    m.setIcon(divIcon(res.kind, {
      selected: selected.has(id),
      failed: state.failed.has(id),
      offRoster: siteId && res.sites && !res.sites.includes(siteId),
      label: markerLabel(res),
    }));
  });

  // Kind-colored convoy routes → destination (glow + animated dash)
  state.routeLayer.clearLayers();
  const dest = destination && destination.coords;
  if (dest && r.coalition && r.coalition.feasible) {
    L.circle(dest, {
      radius: 380,
      color: "#ec835a",
      weight: 2,
      opacity: 0.75,
      fillColor: "#ec835a",
      fillOpacity: 0.14,
      className: "rq-halo target",
      interactive: false,
    }).addTo(state.routeLayer);

    selected.forEach((id) => {
      const res = state.resourcesById[id];
      if (!res) return;
      const color = KIND_COLOR[res.kind] || "#3987e5";
      L.polyline([[res.lat, res.lng], dest], {
        color, weight: 10, opacity: 0.14, interactive: false, lineCap: "round",
      }).addTo(state.routeLayer);
      L.polyline([[res.lat, res.lng], dest], {
        color, weight: 2.75, opacity: 0.95, dashArray: "8 12",
        className: "rq-route-flow", interactive: false, lineCap: "round",
      }).addTo(state.routeLayer);
    });
  }

  updateMapStatus(r, destination);
}

function updateMapStatus(r, destination) {
  const destEl = $("#msDest");
  const chip = $("#msChip");
  const meta = $("#msMeta");
  if (!destEl || !chip || !meta) return;

  const name = (destination && destination.name) || (r.mission && r.mission.destination) || "—";
  destEl.textContent = name;

  const verdict = r.verdict || "";
  let stateKey = "muted";
  let label = "STANDBY";
  if (verdict === "ready to deploy") { stateKey = "good"; label = "READY"; }
  else if (verdict === "ready but fragile") { stateKey = "warning"; label = "FRAGILE"; }
  else if (verdict === "no feasible coalition") { stateKey = "critical"; label = "BLOCKED"; }
  else if (verdict) { stateKey = "serious"; label = "REVIEW"; }

  chip.dataset.state = stateKey;
  chip.textContent = label;

  const n = r.coalition && r.coalition.feasible
    ? (r.coalition.selected_resource_ids || []).length
    : 0;
  const failed = state.failed.size;
  if (n) meta.textContent = `${n} volunteer${n === 1 ? "" : "s"} scheduled` + (failed ? ` · ${failed} unavailable` : "");
  else if (failed) meta.textContent = `${failed} unavailable · site uncovered`;
  else meta.textContent = "Awaiting feasible coverage";
}

function renderFlow(r) {
  const steps = [];
  steps.push({
    name: "Mission (facts)",
    val: `${r.mission.destination || "?"} · review: ${r.review.status}`,
    state: r.review.status === "ready" ? "good" : "serious",
  });
  const capsList = r.capability_assessment.required_capabilities;
  const caps = capsList.map((c) => c.code);
  const anyInferred = capsList.some((c) => c.inferred);
  steps.push({
    name: "Capabilities (rules)",
    val: (caps.length ? caps.join(", ") : "none derived") + (anyInferred ? " · inferred from incident" : ""),
    state: r.capability_assessment.needs_human_review ? "serious" : caps.length ? "good" : "muted",
  });
  if (!r.coalition) {
    steps.push({ name: "Coalition (CP-SAT)", val: "skipped — needs review/facts", state: "muted" });
  } else if (r.coalition.feasible) {
    steps.push({
      name: "Coalition (CP-SAT)",
      val: `${r.coalition.selected_resource_ids.join(", ")} · cap ${r.coalition.total_capacity} · ${r.coalition.solver_status}`,
      state: "good",
    });
  } else {
    steps.push({ name: "Coalition (CP-SAT)", val: "INFEASIBLE", state: "critical" });
  }
  if (r.resilience) {
    steps.push({
      name: "Resilience (re-solve)",
      val: `overall ${r.resilience.overall_classification}`,
      state: r.resilience.overall_classification === "recoverable" ? "good" : "critical",
    });
  } else {
    steps.push({ name: "Resilience (re-solve)", val: "not run", state: "muted" });
  }
  if (r.hypergraph) {
    const em = r.hypergraph.emergent_capabilities.map((c) => c.code);
    steps.push({ name: "Hypergraph (represent)", val: em.length ? "emergent: " + em.join(", ") : "structural view", state: "good" });
  } else {
    steps.push({ name: "Hypergraph (represent)", val: "not built", state: "muted" });
  }

  $("#flow").innerHTML = steps.map((s) => `
    <div class="step" data-state="${s.state}">
      <div class="rail"><div class="node"></div><div class="line"></div></div>
      <div class="body"><div class="s-name">${s.name}</div><div class="s-val">${s.val}</div></div>
    </div>`).join("");
}

function renderResilience(r) {
  const box = $("#resilience");
  if (!r.resilience || !r.resilience.scenarios.length) {
    box.innerHTML = `<div class="empty">No feasible baseline to stress-test.</div>`;
    return;
  }
  box.innerHTML = r.resilience.scenarios.map((s) => {
    const good = s.classification === "recoverable";
    const added = s.added_resource_ids && s.added_resource_ids.length ? ` → +${s.added_resource_ids.join(", ")}` : "";
    return `<div class="chip" data-state="${good ? "good" : "critical"}">
      <span class="ic">${good ? "🛟" : "⛔"}</span>
      <span class="nm">${s.failed_resource_name}</span>
      <span class="arrow">${good ? added : "no replacement"}</span>
      <span class="tag">${good ? "recoverable" : "breaks mission"}</span>
    </div>`;
  }).join("");
}

function renderHypergraph(r) {
  const cy = state.cy;
  if (!cy) return;
  cy.batch(() => {
    cy.elements().removeClass("selected unit failed active dead");
    state.failed.forEach((id) => cy.getElementById(id).addClass("failed"));
    const selected = new Set(r.coalition ? r.coalition.selected_resource_ids : []);
    selected.forEach((id) => cy.getElementById(id).addClass("selected"));

    state.scenario.hyperedges.forEach((h) => {
      const alive = h.resource_ids.every((rid) => !state.failed.has(rid));
      const heNode = cy.getElementById("he:" + h.id);
      if (alive) heNode.addClass("unit");
      h.resource_ids.forEach((rid) => {
        const edge = cy.getElementById(`edge:${h.id}:${rid}`);
        edge.addClass(alive ? "active" : "dead");
      });
    });
  });
}

// ---------------------------------------------------------------- events
function wireEvents() {
  $("#presetSelect").addEventListener("change", (e) => {
    const p = state.scenario.presets.find((x) => x.id === e.target.value);
    if (p) applyPreset(p);
  });

  let capTimer = null;
  $("#capSlider").addEventListener("input", (e) => {
    state.minCapacity = Number(e.target.value);
    $("#capVal").textContent = e.target.value;
    clearTimeout(capTimer);
    capTimer = setTimeout(plan, 180);
  });

  $("#resetBtn").addEventListener("click", () => { state.failed.clear(); plan(); });

  $("#extractBtn").addEventListener("click", async () => {
    const q = $("#nlQuery").value.trim();
    if (!q) { $("#msg").textContent = "Describe a cancellation first."; return; }
    setBusy(true);
    $("#msg").textContent = "Asking Bedrock…";
    $("#msg").className = "msg";
    try {
      const resp = await api("/api/extract", { query: q });
      state.mission = resp.mission;
      state.failed.clear();
      $("#msg").textContent = resp.message;
      $("#msg").className = "msg " + (resp.used_llm ? "llm" : "fallback");
      await plan();
    } catch (e) {
      $("#msg").textContent = "Extract failed: " + e.message;
    } finally {
      setBusy(false);
    }
  });

  const advisorBtn = $("#advisorBtn");
  if (advisorBtn) {
    advisorBtn.addEventListener("click", async () => {
      const q = $("#advisorQ").value.trim();
      if (!q) { $("#advisorA").textContent = "Type a question first."; return; }
      advisorBtn.disabled = true;
      $("#advisorA").textContent = "Asking the Advisor…";
      $("#advisorTools").textContent = "";
      try {
        const resp = await api("/api/advisor", { question: q });
        $("#advisorA").textContent = resp.answer;
        $("#advisorA").className = "advisor-answer " + (resp.used_llm ? "ok" : "warn");
        $("#advisorTools").textContent = resp.tools && resp.tools.length
          ? "tools called: " + resp.tools.join(", ") : "";
      } catch (e) {
        $("#advisorA").textContent = "Advisor failed: " + e.message;
        $("#advisorA").className = "advisor-answer warn";
      } finally {
        advisorBtn.disabled = false;
      }
    });
  }

  window.addEventListener("resize", () => { if (state.cy) state.cy.resize(); });
}

// ---------------------------------------------------------------- sentinel
const sentinel = {
  data: null,     // { mission, observations, summary }
  idx: 0,         // how many observations have been revealed
  timer: null,    // play interval handle
  auto: 0,
  esc: 0,
};

const ACTION_META = {
  silent:          { tag: "watching", glyph: "●", cls: "silent" },
  auto_recomposed: { tag: "auto-recomposed", glyph: "⟳", cls: "auto" },
  improved:        { tag: "improved", glyph: "↑", cls: "improved" },
  resolved:        { tag: "resolved", glyph: "✓", cls: "resolved" },
  escalated:       { tag: "DECISION NEEDED", glyph: "⚠", cls: "escalated" },
};

// Delivery outcome of an escalation (see app/notifications.py). Only escalations
// ever carry one - silent/auto/improved/resolved deliberately send nothing.
const NOTIFY_META = {
  sent:                    { glyph: "✓", cls: "ok",      text: (t) => `Alert delivered to ${t}` },
  dry_run:                 { glyph: "◌", cls: "pending", text: (t) => `Alert rendered for ${t} — not sent (dry run)` },
  skipped_unconfigured:    { glyph: "◌", cls: "pending", text: () => "No channel configured — this is the alert a human would receive" },
  skipped_below_threshold: { glyph: "◌", cls: "pending", text: () => "Below the configured severity threshold — not sent" },
  failed:                  { glyph: "✕", cls: "fail",    text: (t) => `Delivery to ${t} failed — monitoring continues` },
};

function htmlEscape(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
  ));
}

async function loadSentinel() {
  if (sentinel.data) return sentinel.data;
  sentinel.data = await api("/api/sentinel");
  return sentinel.data;
}

function renderSentinelMission(m) {
  const reqs = (m.requirements || []).join(", ") || "none";
  $("#sentinelMission").innerHTML =
    `<span class="sm-k">Monitoring</span> <b>${m.destination}</b> · ${m.incident_type} ` +
    `· needs: ${reqs} · <i>SIMULATED</i>`;
}

// Where escalations are routed. The server never sends the webhook URL - only a
// channel label - so there is nothing sensitive to render here.
function renderSentinelRoute(summary) {
  const node = $("#sentinelRoute");
  if (!node) return;
  const n = (summary && summary.notifications) || {};
  if (!n.configured) {
    node.innerHTML =
      `<i class="pd route-off"></i>escalations: no channel configured ` +
      `<span class="route-hint">(set RESQ_NOTIFY_SLACK_WEBHOOK_URL)</span>`;
    return;
  }
  const dry = n.dry_run ? ` <span class="route-hint">(dry run)</span>` : "";
  node.innerHTML =
    `<i class="pd route-on"></i>escalations → <b>${htmlEscape(n.target)}</b> ` +
    `<span class="route-hint">${htmlEscape(n.channel)}</span>${dry}`;
}

function resetSentinel() {
  stopSentinelPlay();
  sentinel.idx = 0;
  sentinel.auto = 0;
  sentinel.esc = 0;
  $("#sentinelTimeline").innerHTML = "";
  $("#tAuto").textContent = "0";
  $("#tEsc").textContent = "0";
  $("#sentinelPlay").disabled = false;
  $("#sentinelStep").disabled = false;
}

function stopSentinelPlay() {
  if (sentinel.timer) { clearInterval(sentinel.timer); sentinel.timer = null; }
  $("#sentinelPlay").textContent = "▶ Play timeline";
}

// `meta.text` templates are hard-coded literals; only the channel label comes
// from config, so escaping (and bolding) it here is the whole sanitisation step.
function notificationHtml(notification) {
  if (!notification) return "";
  const meta = NOTIFY_META[notification.status];
  if (!meta) return "";
  const target = `<b>${htmlEscape(notification.target || "the configured channel")}</b>`;
  return `<div class="esc-notify ${meta.cls}">` +
         `<span class="en-glyph" aria-hidden="true">${meta.glyph}</span>${meta.text(target)}</div>`;
}

function revealNextObservation() {
  const obs = sentinel.data && sentinel.data.observations;
  if (!obs || sentinel.idx >= obs.length) { stopSentinelPlay(); return false; }

  const o = obs[sentinel.idx];
  sentinel.idx += 1;
  const meta = ACTION_META[o.action] || ACTION_META.silent;
  const isBaseline = o.event.kind === "baseline";
  const header = isBaseline ? "Baseline assessment" : (o.event.note || o.event.kind);
  const plan = (o.selected_resource_ids || []).join(", ") || "none";

  if (o.escalation) sentinel.esc += 1; else sentinel.auto += 1;
  $("#tAuto").textContent = String(sentinel.auto);
  $("#tEsc").textContent = String(sentinel.esc);

  let escHtml = "";
  if (o.escalation) {
    const e = o.escalation;
    const miss = (e.missing_capabilities || []).length
      ? `<div class="esc-missing">Missing capability: ${e.missing_capabilities.join(", ")}</div>` : "";
    escHtml = `
      <div class="esc-card" data-sev="${e.severity}">
        <div class="esc-top"><span class="esc-badge">⚠ Human decision needed</span>
          <span class="esc-sev">${e.severity}</span></div>
        <div class="esc-text">${e.decision_required}</div>
        ${miss}
        ${notificationHtml(o.notification)}
      </div>`;
  }

  const row = document.createElement("div");
  row.className = "s-row " + meta.cls;
  row.innerHTML = `
    <div class="s-rail"><span class="s-node">${meta.glyph}</span><span class="s-line"></span></div>
    <div class="s-body">
      <div class="s-top">
        <span class="s-tag ${meta.cls}">${meta.glyph} ${meta.tag}</span>
        <span class="s-verdict" data-v="${verdictState(o.verdict)}">${o.verdict}</span>
      </div>
      <div class="s-note">${header}</div>
      <div class="s-plan">plan: ${plan}</div>
      ${escHtml}
    </div>`;
  const tl = $("#sentinelTimeline");
  tl.appendChild(row);
  requestAnimationFrame(() => row.classList.add("show"));
  tl.scrollTop = tl.scrollHeight;

  if (sentinel.idx >= obs.length) {
    stopSentinelPlay();
    $("#sentinelStep").disabled = true;
  }
  return true;
}

function playSentinel() {
  if (sentinel.timer) { stopSentinelPlay(); return; }
  if (sentinel.data && sentinel.idx >= sentinel.data.observations.length) resetSentinel();
  $("#sentinelPlay").textContent = "⏸ Pause";
  revealNextObservation();
  sentinel.timer = setInterval(() => {
    if (!revealNextObservation()) stopSentinelPlay();
  }, 1400);
}

async function openSentinel() {
  const overlay = $("#sentinelOverlay");
  overlay.hidden = false;
  try {
    const data = await loadSentinel();
    renderSentinelMission(data.mission);
    renderSentinelRoute(data.summary);
    if (sentinel.idx === 0) resetSentinel();
  } catch (e) {
    $("#sentinelMission").textContent = "Could not load sentinel timeline: " + e.message;
  }
}

function closeSentinel() {
  stopSentinelPlay();
  $("#sentinelOverlay").hidden = true;
}

function initSentinel() {
  $("#sentinelBtn").addEventListener("click", openSentinel);
  $("#sentinelClose").addEventListener("click", closeSentinel);
  $("#sentinelPlay").addEventListener("click", playSentinel);
  $("#sentinelStep").addEventListener("click", () => { stopSentinelPlay(); revealNextObservation(); });
  $("#sentinelReset").addEventListener("click", resetSentinel);
  $("#sentinelOverlay").addEventListener("click", (e) => {
    if (e.target.id === "sentinelOverlay") closeSentinel();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("#sentinelOverlay").hidden) closeSentinel();
  });
}

initSentinel();
init();

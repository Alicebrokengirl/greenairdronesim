import { api, el, fmt, sci, when, toast, loadingHtml, errorHtml, speciesColor, locale } from "./api.js";
import { t, mountLangSwitch, lang, translateStatic } from "./i18n.js";
import { initChart, disposeCharts, AXIS, TOOLTIP } from "./charts.js";
import { renderAnalysis } from "./analysis.js";
import { renderMap } from "./map.js";
import { renderDrone } from "./drone.js";
import { renderReport } from "./report.js";

export const state = {
  overview: null,
  scenarios: [],
  sid: localStorage.getItem("gad.sid") || null,
  isaac: null,
  route: "dashboard",
};

export function selectScenario(sid) {
  if (!state.scenarios.find((s) => s.id === sid)) return;
  state.sid = sid;
  localStorage.setItem("gad.sid", sid);
  const sel = document.getElementById("scenario-select");
  if (sel) sel.value = sid;
  render();
}

function openScenario(sid, route) {
  state.sid = sid;
  localStorage.setItem("gad.sid", sid);
  if (selectEl) selectEl.value = sid;
  if (routeFromHash() === route) render();
  else location.hash = `#/${route}`;
}

export function scenarioById(sid) {
  return state.scenarios.find((s) => s.id === sid) || state.scenarios[0];
}

const view = document.getElementById("view");
const titleEl = document.getElementById("page-title");
const kickerEl = document.getElementById("page-kicker");
const subEl = document.getElementById("page-sub");
const navEl = document.getElementById("nav");
const selectEl = document.getElementById("scenario-select");
const langEl = document.getElementById("lang");

let renderToken = 0;

const PAGES = {
  dashboard: renderDashboard,
  scenarios: renderScenarios,
  analysis: renderAnalysis,
  map: renderMap,
  drone: renderDrone,
  report: renderReport,
};

function routeFromHash() {
  const raw = location.hash.replace(/^#\/?/, "");
  return (raw.split("?")[0] || "dashboard").trim();
}

function populateScenarioSelect() {
  selectEl.innerHTML = "";
  for (const s of state.scenarios) {
    const opt = document.createElement("option");
    opt.value = s.id;
    opt.textContent = `${s.title} · ${s.category}`;
    selectEl.appendChild(opt);
  }
  if (state.sid) selectEl.value = state.sid;
  selectEl.disabled = state.scenarios.length === 0;
}

async function loadOverview(force = false) {
  if (state.overview && !force) return;
  const ov = await api.overview();
  state.overview = ov;
  state.scenarios = ov.scenarios;
  if (!state.sid || !state.scenarios.some((s) => s.id === state.sid)) {
    state.sid = state.scenarios[0]?.id || null;
  }
  populateScenarioSelect();
  updateSide();
}

function updateSide() {
  const ov = state.overview;
  const scEl = document.getElementById("side-scenarios");
  const upEl = document.getElementById("side-updated");
  if (scEl) scEl.textContent = ov ? `${ov.computed_count}/${ov.scenario_count}` : "—";
  if (upEl && ov) upEl.textContent = shortDate(ov.last_update);
  if (selectEl && state.sid) selectEl.value = state.sid;
}

function shortDate(ts) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleDateString(locale(), { month: "short", day: "2-digit" });
}

function setPageMeta(route) {
  kickerEl.textContent = t(`pages.${route}.kicker`);
  titleEl.textContent = t(`pages.${route}.title`);
  subEl.textContent = t(`pages.${route}.sub`);
  document.title = `GreenAirDrone — ${t(`pages.${route}.title`)}`;
}

async function render() {
  const route = routeFromHash();
  const page = PAGES[route];
  if (!page) {
    location.hash = "#/dashboard";
    return;
  }
  state.route = route;
  disposeCharts();
  setPageMeta(route);
  document.querySelectorAll(".nav-item").forEach((n) => {
    n.classList.toggle("active", n.dataset.route === route);
  });

  const token = ++renderToken;
  view.innerHTML = loadingHtml(t("common.loading"));
  try {
    await loadOverview();
    if (token !== renderToken) return;
    const node = await page({ state, selectScenario, scenarioById });
    if (token !== renderToken) return;
    view.innerHTML = "";
    view.append(node);
    requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
    setTimeout(refreshIsaacWidgets, 250);
    view.classList.remove("fade-in");
    void view.offsetWidth;
    view.classList.add("fade-in");
  } catch (err) {
    console.error(err);
    if (token === renderToken) view.innerHTML = errorHtml(t("common.error"), t("common.retry"));
  }
  updateSide();
}

/* ------------------------------------------------------------- dashboard */

function metricCard(label, value, unit, foot, tone = "") {
  return el(
    "div",
    { class: "card metric-card", "data-tone": tone },
    el("div", { class: "metric-label" }, label),
    el("div", { class: "metric-value" }, value, unit ? el("small", {}, unit) : null),
    el("div", { class: "metric-foot" }, foot)
  );
}

function speciesChips(s, limit = 8) {
  const wrap = el("div", { class: "chips" });
  for (const sp of s.species.slice(0, limit)) {
    wrap.append(
      el(
        "span",
        { class: "chip", title: sp.provenance || "" },
        el("span", {
          style: `display:inline-block;width:7px;height:7px;border-radius:2px;background:${speciesColor(sp.id)};margin-right:5px;vertical-align:middle`,
        }),
        sp.label
      )
    );
  }
  return wrap;
}

function maximaRows(s, limit = 4) {
  const entries = Object.entries(s.maxima)
    .map(([id, m]) => ({ id, ...m }))
    .sort((a, b) => b.ug_m3 - a.ug_m3)
    .slice(0, limit);
  const top = entries[0]?.ug_m3 || 1;
  const wrap = el("div", { class: "maxlist" });
  for (const m of entries) {
    const width = Math.max(3, (m.ug_m3 / top) * 100);
    wrap.append(
      el(
        "div",
        { class: "maxrow" },
        el("span", { style: "color:var(--muted)" }, m.display),
        el("div", { class: "maxbar" }, el("i", { style: `width:${width}%;background:${speciesColor(m.id)}` })),
        el("span", { class: "maxval" }, sci(m.ug_m3), el("small", {}, "µg/m³"))
      )
    );
  }
  return wrap;
}

function statusPill(s) {
  return el(
    "span",
    { class: `pill ${s.status === "computed" ? "ok" : "warn"}` },
    el("i", { class: "dot" }),
    t(s.status === "computed" ? "common.computed" : "common.partial")
  );
}

function scenarioCard(s) {
  const wind = s.wind?.speed_m_s;
  return el(
    "article",
    { class: "card sc-card", style: `--sc:${s.accent || "var(--accent)"}` },
    el(
      "div",
      { class: "sc-head" },
      el(
        "div",
        {},
        el("div", { class: "sc-name" }, s.title),
        el("div", { class: "sc-model" }, `OpenFOAM run · ${s.model_run}`)
      ),
      el("div", { style: "display:flex;gap:6px;align-items:center;flex-wrap:wrap", "data-live-sid": s.id }, statusPill(s))
    ),
    el("div", { class: "sc-desc" }, s.context),
    speciesChips(s),
    el(
      "div",
      { class: "sc-meta" },
      el("div", {}, el("div", { class: "k" }, t("dash.wind")), el("div", { class: "v" }, wind ? `${wind} m/s → +x` : "—")),
      el("div", {}, el("div", { class: "k" }, t("dash.source")), el("div", { class: "v" }, s.kind || "—")),
      el("div", {}, el("div", { class: "k" }, t("dash.duration")), el("div", { class: "v" }, `${fmt(s.duration_s)} s`)),
      el("div", {}, el("div", { class: "k" }, t("dash.measurements")), el("div", { class: "v" }, fmt(s.measurements)))
    ),
    el("div", { class: "card-note" }, t("dash.maxima")),
    maximaRows(s),
    el(
      "div",
      { style: "margin-top:auto;display:flex;gap:9px" },
      el(
        "button",
        { class: "btn primary", onclick: () => openScenario(s.id, "analysis") },
        t("dash.open")
      ),
      el(
        "button",
        { class: "btn ghost", onclick: () => openScenario(s.id, "map") },
        t("dash.openMap")
      )
    )
  );
}

function isaacCard() {
  const card = el(
    "div",
    { class: "card" },
    el(
      "div",
      { class: "card-head" },
      el("div", {}, el("div", { class: "card-title" }, t("dash.isaac.title")), el("div", { class: "card-note", id: "isaac-state" }, "—")),
      el("span", { class: "pill off", id: "isaac-pill-live" }, el("i", { class: "dot" }), t("common.offline"))
    ),
    el(
      "div",
      { class: "statgrid", id: "isaac-live" },
      el("div", { class: "stat" }, el("div", { class: "k" }, t("dash.isaac.t")), el("div", { class: "v", id: "isaac-t" }, "—")),
      el("div", { class: "stat" }, el("div", { class: "k" }, t("dash.isaac.fps")), el("div", { class: "v", id: "isaac-fps" }, "—"))
    ),
    el("div", { class: "card-note", id: "isaac-scenario", style: "margin-top:10px" }, "—"),
    el("div", { class: "note", style: "margin-top:14px" }, t("dash.isaac.hint"))
  );
  return card;
}

function comparisonChart() {
  const wrap = el("div", { class: "card" });
  wrap.append(
    el("div", { class: "card-head" }, el("div", {}, el("div", { class: "card-title" }, t("dash.cmp.title")), el("div", { class: "card-note" }, t("dash.cmp.note")))),
    el("div", { class: "chart small", id: "cmp-chart" })
  );
  requestAnimationFrame(() => {
    const dom = document.getElementById("cmp-chart");
    if (!dom) return;
    const chart = initChart(dom);
    const species = Array.from(new Set(state.scenarios.flatMap((s) => s.species.map((x) => x.id))));
    chart.setOption({
      grid: { left: 54, right: 14, top: 30, bottom: 34 },
      tooltip: {
        ...TOOLTIP,
        trigger: "axis",
        valueFormatter: (v) => (v == null ? "—" : `${sci(v)} µg/m³`),
      },
      legend: { top: 0, right: 0, textStyle: { color: AXIS.text, fontSize: 11 }, itemWidth: 10, itemHeight: 10 },
      xAxis: {
        type: "category",
        data: species,
        axisLine: { lineStyle: { color: AXIS.line } },
        axisTick: { show: false },
        axisLabel: { color: AXIS.text, fontSize: 10.5 },
      },
      yAxis: {
        type: "log",
        min: 1,
        axisLabel: { color: AXIS.text, fontSize: 10.5, formatter: (v) => sci(v) },
        splitLine: { lineStyle: { color: AXIS.split } },
      },
      series: state.scenarios.map((s) => ({
        name: s.title,
        type: "bar",
        data: species.map((sp) => s.maxima[sp]?.ug_m3 ?? null),
        barMaxWidth: 22,
        itemStyle: { color: s.accent, borderRadius: 0 },
      })),
    });
  });
  return wrap;
}

async function renderDashboard() {
  await loadOverview();
  const ov = state.overview;
  const node = el("div", {});

  node.append(
    el(
      "div",
      { class: "grid k4" },
      metricCard(t("dash.metric.scenarios"), `${ov.computed_count}/${ov.scenario_count}`, "", t("dash.metric.scenarios.foot")),
      metricCard(t("dash.metric.computed"), String(ov.computed_count), "", t("dash.metric.computed.foot"), "ok"),
      metricCard(t("dash.metric.measurements"), fmt(ov.measurement_count), "", t("dash.metric.measurements.foot"), "info"),
      metricCard(t("dash.metric.updated"), shortDate(ov.last_update), "", when(ov.last_update), "dim")
    )
  );

  node.append(el("div", { class: "grid k2", style: "margin-top:16px" }, isaacCard(), comparisonChart()));

  node.append(
    el("div", { class: "section-title" }, el("h2", {}, t("dash.section.overview")), el("span", { class: "hint" }, t("dash.section.overview.hint"))),
    el("div", { class: "grid k3" }, state.scenarios.map(scenarioCard))
  );

  if (state.overview.missing_scenarios?.length) {
    node.append(
      el("div", { class: "note", style: "margin-top:16px" },
        `${t("dash.notAvailable")}: ${state.overview.missing_scenarios.join(", ")}.`)
    );
  }
  refreshIsaacWidgets();
  return node;
}

/* ------------------------------------------------------------- scenarios */

function scenarioDetail(s) {
  const d = s.domain || {};
  const domTxt = `x ${d.x?.[0] ?? "?"}…${d.x?.[1] ?? "?"} m · y ${d.y?.[0] ?? "?"}…${d.y?.[1] ?? "?"} m · z ${d.z?.[0] ?? "?"}…${d.z?.[1] ?? "?"} m`;
  const maxEntries = Object.entries(s.maxima).sort((a, b) => b[1].ug_m3 - a[1].ug_m3);
  const table = el(
    "div",
    { class: "table-wrap", style: "max-height:none" },
    el(
      "table",
      { class: "data" },
      el(
        "thead",
        {},
        el(
          "tr",
          {},
          [
            el("th", {}, t("sc.th.species")),
            el("th", { style: "text-transform:none" }, t("sc.th.peak")),
            el("th", {}, t("sc.th.location")),
            el("th", {}, t("sc.th.stored")),
            el("th", {}, t("sc.th.phase")),
          ]
        )
      ),
      el(
        "tbody",
        {},
        maxEntries.map(([id, m]) =>
          el(
            "tr",
            {},
            el("td", { style: `color:${speciesColor(id)};font-weight:600` }, m.display),
            el("td", {}, sci(m.ug_m3)),
            el("td", { class: "dim" }, m.location_m ? m.location_m.map((v) => Number(v).toFixed(1)).join(", ") : "—"),
            el("td", {}, m.stored_kg ? sci(m.stored_kg) : "—"),
            el("td", { class: "dim" }, m.phase || "—")
          )
        )
      )
    )
  );

  const limitations = (s.limitations || []).map((l) => el("li", {}, l));
  const checkEntries = Object.entries(s.checks || {}).filter(([, v]) => (typeof v === "number" ? v !== 0 : Boolean(v)));
  const checks = checkEntries.length
    ? checkEntries.map(([k, v]) => el("span", { class: "chip" }, `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`))
    : Object.keys(s.checks || {}).length
      ? [el("span", { class: "chip" }, t("sc.checksOk"))]
      : [];

  return el(
    "article",
    { class: "card", style: "margin-bottom:16px" },
    el(
      "div",
      { class: "card-head" },
      el(
        "div",
        {},
        el("div", { class: "sc-name", style: "font-size:19px" }, s.title),
        el("div", { class: "sc-model" }, `${s.description} · OpenFOAM run: ${s.model_run}`)
      ),
      el("div", { style: "display:flex;gap:6px;align-items:center;flex-wrap:wrap", "data-live-sid": s.id }, statusPill(s))
    ),
    el(
      "div",
      { class: "grid k2", style: "gap:20px" },
      el(
        "div",
        {},
        el("div", { class: "sc-meta", style: "grid-template-columns:repeat(2,minmax(0,1fr));margin-bottom:14px" },
          el("div", {}, el("div", { class: "k" }, t("dash.wind")), el("div", { class: "v" }, `${s.wind?.speed_m_s ?? "—"} m/s, +x`)),
          el("div", {}, el("div", { class: "k" }, t("dash.duration")), el("div", { class: "v" }, `${fmt(s.duration_s)} s, ${s.frame_count} frames`)),
          el("div", {}, el("div", { class: "k" }, t("sc.domain")), el("div", { class: "v", style: "font-size:11.5px" }, domTxt)),
          el("div", {}, el("div", { class: "k" }, t("sc.mesh")), el("div", { class: "v" }, `${fmt(s.mesh_cells)} cells · ${s.grid_shape.join("×")}`)),
          el("div", {}, el("div", { class: "k" }, t("dash.measurements")), el("div", { class: "v" }, `${fmt(s.measurements)} samples`)),
          el("div", {}, el("div", { class: "k" }, t("side.updated")), el("div", { class: "v" }, when(s.last_update)))
        ),
        el("div", { class: "card-note", style: "margin-bottom:6px" }, t("sc.species")),
        speciesChips(s, 12),
        el("div", { class: "chips", style: "margin-top:10px" }, checks),
        el(
          "div",
          { style: "display:flex;gap:9px;margin-top:16px" },
          el("button", { class: "btn primary", onclick: () => openScenario(s.id, "analysis") }, t("sc.openAnalysis")),
          el("button", { class: "btn", onclick: () => openScenario(s.id, "map") }, t("sc.openMap")),
          el(
            "button",
            {
              class: "btn",
              onclick: async () => {
                try {
                  const r = await api.switchIsaac(s.id);
                  toast(r.connected ? t("sc.liveRequested") : t("dash.isaac.disconnected"));
                } catch (_) {
                  toast(t("common.error"));
                }
              },
            },
            t("sc.runLive")
          ),
          el("button", { class: "btn", onclick: () => openScenario(s.id, "drone") }, t("nav.drone")),
          el("button", { class: "btn ghost", onclick: () => openScenario(s.id, "report") }, t("nav.report"))
        )
      ),
      el("div", {}, el("div", { class: "card-note", style: "margin-bottom:8px" }, t("sc.maxima")), table)
    ),
    limitations.length
      ? el(
          "div",
          { style: "margin-top:16px" },
          el("div", { class: "card-note", style: "margin-bottom:6px" }, t("sc.limitations")),
          el("ul", { style: "margin:0;padding-left:18px;color:var(--muted);font-size:12.5px" }, limitations)
        )
      : null
  );
}

async function renderScenarios() {
  await loadOverview();
  const node = el("div", {});
  for (const s of state.scenarios) node.append(scenarioDetail(s));
  return node;
}

/* ----------------------------------------------------------------- isaac */

function updateIsaacPill(st) {
  const pill = document.getElementById("isaac-pill");
  if (pill) {
    pill.className = `pill ${st.connected ? "ok" : "off"}`;
    pill.innerHTML = `<i class="dot"></i><span>${st.connected ? t("common.online") : t("common.offline")}</span>`;
  }
  const live = document.getElementById("isaac-pill-live");
  if (live) {
    live.className = `pill ${st.connected ? "ok" : "off"}`;
    live.innerHTML = `<i class="dot"></i><span>${st.connected ? t("common.online") : t("common.offline")}</span>`;
  }
}

function setIsaacWidgets(st) {
  state.isaac = st;
  updateIsaacPill(st);
  const activeSid = st.connected ? st.scenario : null;
  document.querySelectorAll("[data-live-sid]").forEach((node) => {
    const active = node.dataset.liveSid === activeSid;
    let badge = node.querySelector(".pill.live.js-live");
    if (active && !badge) {
      badge = document.createElement("span");
      badge.className = "pill live js-live";
      badge.innerHTML = '<i class="dot"></i>LIVE';
      node.prepend(badge);
    } else if (!active && badge) {
      badge.remove();
    }
  });
  const stateEl = document.getElementById("isaac-state");
  if (stateEl) stateEl.textContent = t(st.connected ? "dash.isaac.connected" : "dash.isaac.disconnected");
  const tEl = document.getElementById("isaac-t");
  if (tEl) tEl.textContent = st.connected && st.t != null ? `${Number(st.t).toFixed(1)} s` : "—";
  const fEl = document.getElementById("isaac-fps");
  if (fEl) fEl.textContent = st.connected && st.fps != null ? `${Number(st.fps).toFixed(1)} fps` : "—";
  const sEl = document.getElementById("isaac-scenario");
  if (sEl) {
    const live = state.scenarios.find((x) => x.id === st.scenario);
    sEl.textContent = st.connected
      ? `${live?.title || st.scenario} · ${st.fps != null ? Number(st.fps).toFixed(1) : "—"} avg fps · ${st.t != null ? Number(st.t).toFixed(1) : "—"} s`
      : t("dash.isaac.disconnected");
  }
}

export function refreshIsaacWidgets() {
  api
    .isaac()
    .then((st) => setIsaacWidgets(st))
    .catch(() => {});
}

async function pollIsaac() {
  try {
    setIsaacWidgets(await api.isaac());
  } catch (_) {}
  setTimeout(pollIsaac, 5000);
}

/* ------------------------------------------------------------------ boot */

function boot() {
  translateStatic();
  mountLangSwitch(langEl);
  document.addEventListener("langchange", () => {
    translateStatic();
    mountLangSwitch(langEl);
    render();
  });
  selectEl.addEventListener("change", () => {
    state.sid = selectEl.value;
    localStorage.setItem("gad.sid", state.sid);
    render();
  });
  navEl.addEventListener("click", (e) => {
    const a = e.target.closest(".nav-item");
    if (!a) return;
  });
  window.addEventListener("hashchange", render);
  render();
  pollIsaac();
}

boot();







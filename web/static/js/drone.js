import { api, el, fmt, sci, speciesColor } from "./api.js";
import { t } from "./i18n.js";
import { initChart, AXIS, TOOLTIP } from "./charts.js";

const STOPS = ["#25597a", "#3a7f92", "#63a69a", "#9cc383", "#d8cf72", "#f0a33c", "#e2553d"];

function hex2rgb(h) {
  return [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
}
function lerpColor(a, b, t) {
  const A = hex2rgb(a);
  const B = hex2rgb(b);
  return `rgb(${Math.round(A[0] + (B[0] - A[0]) * t)},${Math.round(A[1] + (B[1] - A[1]) * t)},${Math.round(A[2] + (B[2] - A[2]) * t)})`;
}
function boxCorners(b) {
  if (!Array.isArray(b) || b.length !== 2) return null;
  const [[x0, y0, z0], [x1, y1, z1]] = b;
  return [
    [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
    [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
  ];
}

function ramp(n) {
  const x = Math.min(1, Math.max(0, n)) * (STOPS.length - 1);
  const i = Math.min(STOPS.length - 2, Math.floor(x));
  return lerpColor(STOPS[i], STOPS[i + 1], x - i);
}

class TrajectoryView {
  constructor(canvas, box, source) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.box = box;
    this.source = boxCorners(source);
    this.yaw = 0.72;
    this.pitch = 0.55;
    this.zoom = 1;
    this.rows = [];
    this.values = [];
    this.selected = -1;
    this.maxV = 1;
    this.hover = null;
    this.drag = null;
    this.screen = [];
    this._bind();
    this.resize();
  }

  _bind() {
    const c = this.canvas;
    c.addEventListener("pointerdown", (e) => {
      this.drag = { x: e.clientX, y: e.clientY, yaw: this.yaw, pitch: this.pitch };
      c.setPointerCapture(e.pointerId);
    });
    c.addEventListener("pointermove", (e) => {
      if (this.drag) {
        this.yaw = this.drag.yaw + (e.clientX - this.drag.x) * 0.008;
        this.pitch = Math.min(1.25, Math.max(0.12, this.drag.pitch + (e.clientY - this.drag.y) * 0.006));
        this.draw();
        return;
      }
      const rect = c.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      let found = null;
      for (const p of this.screen) {
        if ((p.x - mx) ** 2 + (p.y - my) ** 2 < 90) {
          found = p;
          break;
        }
      }
      if (found !== this.hover) {
        this.hover = found;
        this.draw();
        this._tooltip(found, mx, my);
      }
    });
    const end = () => {
      this.drag = null;
    };
    c.addEventListener("pointerup", end);
    c.addEventListener("pointercancel", end);
    c.addEventListener("wheel", (e) => {
      e.preventDefault();
      this.zoom = Math.min(2.6, Math.max(0.55, this.zoom * (e.deltaY > 0 ? 0.92 : 1.08)));
      this.draw();
    }, { passive: false });
    c.addEventListener("pointerleave", () => {
      if (this.hover) {
        this.hover = null;
        this.draw();
        this._tooltip(null);
      }
    });
    new ResizeObserver(() => this.resize()).observe(c);
  }

  _tooltip(p, mx, my) {
    const tip = this.canvas.parentElement.querySelector(".traj-tip");
    if (!tip) return;
    if (!p) {
      tip.style.opacity = "0";
      return;
    }
    const row = this.rows[p.i];
    tip.innerHTML = `<div style="font-weight:650">t = ${fmt(row.t)} s</div>
      <div style="color:var(--muted);font-size:11.5px">x ${row.x.toFixed(1)} · y ${row.y.toFixed(1)} · z ${row.z.toFixed(1)} m</div>
      <div style="margin-top:3px;color:${speciesColor(this.species)};font-weight:600">${sci(this.values[p.i])} µg/m³</div>`;
    const host = this.canvas.parentElement.getBoundingClientRect();
    tip.style.left = `${Math.min(mx + 14, host.width - 150)}px`;
    tip.style.top = `${Math.max(8, my - 50)}px`;
    tip.style.opacity = "1";
  }

  resize() {
    const rect = this.canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.w = Math.max(rect.width, 200);
    this.h = Math.max(rect.height || 0, 320);
    this.canvas.width = Math.round(this.w * dpr);
    this.canvas.height = Math.round(this.h * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.draw();
  }

  setData(rows, values, species) {
    this.rows = rows;
    this.values = values;
    this.species = species;
    this.maxV = Math.max(1e-6, ...values.filter((v) => v != null && v > 0));
    this.draw();
  }

  setSelected(i) {
    this.selected = i;
    this.draw();
  }

  _project(x, y, z) {
    const { x: bx, y: by, z: bz } = this.box;
    const cx = (bx[0] + bx[1]) / 2;
    const cy = (by[0] + by[1]) / 2;
    const cz = (bz[0] + bz[1]) / 2;
    const dx = x - cx;
    const dy = y - cy;
    const dz = z - cz;
    const cyw = Math.cos(this.yaw);
    const syw = Math.sin(this.yaw);
    const rx = dx * cyw - dy * syw;
    const ry = dx * syw + dy * cyw;
    const cp = Math.cos(this.pitch);
    const sp = Math.sin(this.pitch);
    const sx = rx;
    const sy = dz * cp - ry * sp;
    const depth = ry * cp + dz * sp;
    const s = (Math.min(this.w, this.h) / 118) * this.zoom;
    return { x: this.w / 2 + sx * s, y: this.h / 2 - sy * s + 16, depth };
  }

  draw() {
    const ctx = this.ctx;
    if (!ctx) return;
    ctx.clearRect(0, 0, this.w, this.h);
    const { x: bx, y: by, z: bz } = this.box;
    const C = [
      [bx[0], by[0], bz[0]], [bx[1], by[0], bz[0]], [bx[1], by[1], bz[0]], [bx[0], by[1], bz[0]],
      [bx[0], by[0], bz[1]], [bx[1], by[0], bz[1]], [bx[1], by[1], bz[1]], [bx[0], by[1], bz[1]],
    ].map((p) => this._project(...p));

    ctx.save();
    ctx.beginPath();
    ctx.moveTo(C[0].x, C[0].y);
    for (const i of [1, 2, 3]) ctx.lineTo(C[i].x, C[i].y);
    ctx.closePath();
    ctx.fillStyle = "rgba(255,255,255,0.015)";
    ctx.fill();

    ctx.strokeStyle = "rgba(255,255,255,0.055)";
    ctx.lineWidth = 1;
    for (let gx = bx[0]; gx <= bx[1]; gx += 10) {
      const a = this._project(gx, by[0], bz[0]);
      const b = this._project(gx, by[1], bz[0]);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
    for (let gy = by[0]; gy <= by[1]; gy += 10) {
      const a = this._project(bx[0], gy, bz[0]);
      const b = this._project(bx[1], gy, bz[0]);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
    ctx.restore();

    const edges = [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]];
    ctx.strokeStyle = "rgba(255,255,255,0.16)";
    ctx.lineWidth = 1;
    for (const [a, b] of edges) {
      ctx.beginPath();
      ctx.moveTo(C[a].x, C[a].y);
      ctx.lineTo(C[b].x, C[b].y);
      ctx.stroke();
    }

    const corners = this.source || boxCorners([[30, -6, 0], [40, 6, 10]]);
    const sb = corners.map((p) => this._project(...p));
    ctx.strokeStyle = "rgba(255,138,61,0.75)";
    ctx.lineWidth = 1.2;
    for (const [a, b] of edges) {
      ctx.beginPath();
      ctx.moveTo(sb[a].x, sb[a].y);
      ctx.lineTo(sb[b].x, sb[b].y);
      ctx.stroke();
    }

    ctx.fillStyle = "rgba(141,154,173,0.8)";
    ctx.font = "11px 'IBM Plex Mono', monospace";
    ctx.fillText("x", C[1].x + 6, C[1].y + 4);
    ctx.fillText("y", C[3].x - 14, C[3].y + 4);
    ctx.fillText("z", C[4].x - 4, C[4].y - 8);

    if (!this.rows.length) return;

    ctx.strokeStyle = "rgba(88,166,214,0.8)";
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    let started = false;
    for (const r of this.rows) {
      const p = this._project(r.x, r.y, r.z);
      if (!started) {
        ctx.moveTo(p.x, p.y);
        started = true;
      } else ctx.lineTo(p.x, p.y);
    }
    ctx.stroke();

    const lmin = Math.log10(Math.max(this.maxV / 1000, 1e-6));
    const span = Math.max(Math.log10(this.maxV) - lmin, 1e-6);
    const proj = this.rows.map((r, i) => {
      const p = this._project(r.x, r.y, r.z);
      return { ...p, i };
    });
    proj.sort((a, b) => a.depth - b.depth);
    this.screen = [];
    for (const p of proj) {
      const v = this.values[p.i];
      const sel = p.i === this.selected;
      const hov = this.hover && this.hover.i === p.i;
      let color = "rgba(120,132,150,0.55)";
      if (v != null && v > 0) {
        const n = Math.min(1, Math.max(0, (Math.log10(v) - lmin) / span));
        color = ramp(n);
      }
      const r = sel ? 5.2 : hov ? 4.2 : 2.4;
      ctx.beginPath();
      ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
      if (sel) {
        ctx.beginPath();
        ctx.arc(p.x, p.y, 8.5, 0, Math.PI * 2);
        ctx.strokeStyle = "rgba(255,255,255,0.85)";
        ctx.lineWidth = 1.4;
        ctx.stroke();
      }
      this.screen.push({ x: p.x, y: p.y, i: p.i });
    }
  }
}

export async function renderDrone(ctx) {
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  const sid = params.get("scenario") || ctx.state.sid;
  const scenario = ctx.scenarioById(sid);
  if (!scenario) return el("div", { class: "empty" }, "No scenario");

  const meas = await api.measurements(scenario.id);
  const rows = meas.rows.slice().sort((a, b) => a.t - b.t);
  const species = meas.species.length ? meas.species : scenario.species.map((s) => s.id);
  const labels = Object.fromEntries(scenario.species.map((s) => [s.id, s.label]));

  const ui = {
    species: species.includes("CO") ? "CO" : species[0],
    selected: -1,
  };

  function valuesFor(sp) {
    return rows.map((r) => (r.values[sp] == null ? null : r.values[sp]));
  }

  function statsFor(sp) {
    const vals = valuesFor(sp).filter((v) => v != null && v > 0);
    if (!vals.length) return { min: 0, max: 0, mean: 0, count: 0 };
    return {
      min: Math.min(...vals),
      max: Math.max(...vals),
      mean: vals.reduce((a, b) => a + b, 0) / vals.length,
      count: vals.length,
    };
  }

  const box = { x: [0, 100], y: [-25, 25], z: [0, 40] };
  const canvas = el("canvas");
  const tip = el("div", { class: "traj-tip", style: "position:absolute;pointer-events:none;background:rgba(17,23,34,.96);border:1px solid rgba(255,255,255,.12);border-radius:9px;padding:8px 11px;font-size:12px;opacity:0;transition:opacity .12s;z-index:5;min-width:130px" });
  const hint = el("div", { class: "traj-hint" }, t("drone.hint"));
  const trajHost = el("div", { class: "trajectory" }, canvas, tip, hint);

  const speciesSelect = el(
    "select",
    { class: "select", style: "min-width:140px" },
    species.map((s) => el("option", { value: s }, labels[s] || s))
  );
  speciesSelect.value = ui.species;

  const statVals = {};
  const statCard = (id, label) => {
    const v = el("div", { class: "metric-value", style: "font-size:23px" }, "—");
    statVals[id] = v;
    return el("div", { class: "card metric-card" }, el("div", { class: "metric-label" }, label), v);
  };

  const metrics = el(
    "div",
    { class: "grid k4" },
    statCard("count", t("drone.points")),
    statCard("max", t("drone.max")),
    statCard("mean", t("drone.mean")),
    statCard("unavailable", t("drone.unavailable"))
  );

  const chartEl = el("div", { class: "chart small", id: "drone-chart" });
  const chartCard = el(
    "div",
    { class: "card" },
    el(
      "div",
      { class: "card-head" },
      el("div", {}, el("div", { class: "card-title" }, t("drone.chart")), el("div", { class: "card-note" }, `${scenario.title} · ${rows.length} samples`)),
      el("div", { class: "field" }, el("label", {}, t("an.species")), speciesSelect)
    ),
    chartEl
  );

  const tbody = el("tbody");
  const table = el(
    "div",
    { class: "table-wrap" },
    el(
      "table",
      { class: "data" },
      el("thead", {}, el("tr", {}, ["t, s", "x, m", "y, m", "z, m", "µg/m³", "status"].map((h) => el("th", { style: h.startsWith("µ") ? "text-transform:none" : null }, h)))),
      tbody
    )
  );
  const tableCard = el(
    "div",
    { class: "card", style: "margin-top:16px" },
    el("div", { class: "card-head" }, el("div", {}, el("div", { class: "card-title" }, t("drone.table")), el("div", { class: "card-note" }, t("drone.selectHint")))),
    table
  );

  const layout = el(
    "div",
    { class: "drone-layout", style: "margin-top:16px" },
    el(
      "div",
      { class: "card" },
      el("div", { class: "card-head" }, el("div", {}, el("div", { class: "card-title" }, t("drone.path")), el("div", { class: "card-note" }, `${scenario.model_run} · domain ${box.x[1]}×${box.y[1] - box.y[0]}×${box.z[1]} m`))),
      trajHost
    ),
    el("div", {}, chartCard, tableCard)
  );

  const node = el("div", {}, metrics, layout);

  const view = new TrajectoryView(canvas, box, scenario.source_box);
  const chart = initChart(chartEl);

  function renderTable() {
    tbody.innerHTML = "";
    rows.forEach((r, i) => {
      const v = r.values[ui.species];
      const tr = el(
        "tr",
        { class: i === ui.selected ? "selected" : "" },
        el("td", {}, fmt(r.t)),
        el("td", {}, r.x.toFixed(1)),
        el("td", {}, r.y.toFixed(1)),
        el("td", {}, r.z.toFixed(1)),
        el("td", { class: v == null ? "dim" : "" }, v == null ? "—" : sci(v)),
        el("td", { class: v == null ? "dim" : "" }, v == null ? "—" : t("drone.available"))
      );
      tr.title = r.reason || "";
      tr.addEventListener("click", () => select(i));
      tbody.appendChild(tr);
    });
  }

  function select(i) {
    ui.selected = i;
    view.setSelected(i);
    tbody.querySelectorAll("tr").forEach((tr, idx) => tr.classList.toggle("selected", idx === i));
    chart.dispatchAction({ type: "highlight", seriesIndex: 0, dataIndex: i });
    chart.dispatchAction({ type: "showTip", seriesIndex: 0, dataIndex: i });
  }

  function renderChart() {
    const color = speciesColor(ui.species);
    const vals = valuesFor(ui.species);
    chart.setOption(
      {
        grid: { left: 56, right: 18, top: 22, bottom: 34 },
        tooltip: {
          ...TOOLTIP,
          trigger: "axis",
          formatter: (ps) => {
            const p = ps[0];
            const r = rows[p.dataIndex];
            return `<div style="font-weight:650;margin-bottom:4px;color:${color}">${labels[ui.species] || ui.species} · ${sci(p.value)} µg/m³</div>
              <div style="color:#8b95a6">t = ${fmt(r.t)} s<br/>x ${r.x.toFixed(1)} · y ${r.y.toFixed(1)} · z ${r.z.toFixed(1)} m</div>`;
          },
        },
        xAxis: {
          type: "category",
          data: rows.map((r) => String(r.t)),
          axisLabel: { color: AXIS.text, fontSize: 10.5 },
          axisLine: { lineStyle: { color: AXIS.line } },
          axisTick: { show: false },
        },
        yAxis: {
          type: "log",
          min: 1,
          axisLabel: { color: AXIS.text, fontSize: 10.5, formatter: (v) => sci(v) },
          splitLine: { lineStyle: { color: AXIS.split } },
        },
        series: [
          {
            type: "line",
            data: vals,
            connectNulls: true,
            showSymbol: true,
            symbolSize: 4,
            lineStyle: { color, width: 2 },
            itemStyle: { color },
            areaStyle: {
              color: {
                type: "linear",
                x: 0, y: 0, x2: 0, y2: 1,
                colorStops: [
                  { offset: 0, color: color + "40" },
                  { offset: 1, color: color + "00" },
                ],
              },
            },
            markPoint: {
              symbol: "pin",
              symbolSize: 34,
              itemStyle: { color: "rgba(255,92,122,0.85)" },
              label: { color: "#fff", fontSize: 9, formatter: (p) => sci(p.value) },
              data: [{ type: "max", name: "max" }],
            },
          },
        ],
      },
      true
    );
  }

  function updateStats() {
    const st = statsFor(ui.species);
    const unavailable = rows.filter((r) => r.values[ui.species] == null).length;
    statVals.count.innerHTML = `${rows.length} <small>${t("drone.points")}</small>`;
    statVals.max.innerHTML = `${sci(st.max)} <small>µg/m³</small>`;
    statVals.mean.innerHTML = `${sci(st.mean)} <small>µg/m³</small>`;
    statVals.unavailable.innerHTML = `${unavailable}`;
  }

  function refresh(keepSelection = false) {
    renderTable();
    renderChart();
    updateStats();
    view.setData(rows, valuesFor(ui.species), ui.species);
    if (keepSelection) view.setSelected(ui.selected);
  }

  speciesSelect.addEventListener("change", () => {
    ui.species = speciesSelect.value;
    ui.selected = -1;
    refresh();
  });

  chart.on("click", (p) => {
    if (p.componentType === "series") select(p.dataIndex);
  });

  refresh();
  return node;
}

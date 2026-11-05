import { api, el, fmt, sci, speciesColor } from "./api.js";
import { t } from "./i18n.js";

const RAMP = ["#0a1420", "#10263c", "#173c58", "#25597a", "#3a7f92", "#63a69a", "#9cc383", "#d8cf72", "#f0a33c", "#e2553d"];

const hex2rgb = (h) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];

function sampleRamp(n) {
  const v = Math.min(1, Math.max(0, n)) * (RAMP.length - 1);
  const i = Math.min(RAMP.length - 2, Math.floor(v));
  const f = v - i;
  const A = hex2rgb(RAMP[i]);
  const B = hex2rgb(RAMP[i + 1]);
  return [
    Math.round(A[0] + (B[0] - A[0]) * f),
    Math.round(A[1] + (B[1] - A[1]) * f),
    Math.round(A[2] + (B[2] - A[2]) * f),
  ];
}

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const nearest = (arr, v) => arr.reduce((best, x, i) => (Math.abs(x - v) < Math.abs(arr[best] - v) ? i : best), 0);
const MONO = "'IBM Plex Mono', ui-monospace, monospace";

function contour(values, rows, cols, thr) {
  const segs = [];
  const at = (r, c) => Number(values[r]?.[c] ?? 0);
  const ix = (v1, v2) => (thr - v1) / (v2 - v1 || 1e-12);
  for (let r = 0; r < rows - 1; r++) {
    for (let c = 0; c < cols - 1; c++) {
      const a = at(r, c);
      const b = at(r, c + 1);
      const d = at(r + 1, c + 1);
      const e = at(r + 1, c);
      const idx = (a > thr ? 1 : 0) | (b > thr ? 2 : 0) | (d > thr ? 4 : 0) | (e > thr ? 8 : 0);
      if (idx === 0 || idx === 15) continue;
      const top = [c + ix(a, b), r];
      const right = [c + 1, r + ix(b, d)];
      const bottom = [c + ix(e, d), r + 1];
      const left = [c, r + ix(a, e)];
      const table = {
        1: [left, top], 2: [top, right], 3: [left, right], 4: [right, bottom],
        5: [left, top, right, bottom], 6: [top, bottom], 7: [left, bottom],
        8: [bottom, left], 9: [bottom, top], 10: [top, right, bottom, left],
        11: [right, bottom], 12: [right, left], 13: [right, top], 14: [top, left],
      };
      const pts = table[idx] || [];
      for (let i = 0; i + 1 < pts.length; i += 2) segs.push([pts[i], pts[i + 1]]);
    }
  }
  return segs;
}

function azimuth(direction) {
  const [dx, dy] = direction || [1, 0];
  const deg = (Math.atan2(dy, dx) * 180) / Math.PI;
  return (90 - deg + 360) % 360;
}

export async function renderMap(ctx) {
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  const sid = params.get("scenario") || ctx.state.sid;
  const scenario = ctx.scenarioById(sid);
  if (!scenario) return el("div", { class: "empty" }, t("map.empty"));

  const [axes, meas] = await Promise.all([api.axes(scenario.id), api.measurements(scenario.id)]);
  const speciesList = scenario.species;
  const times = scenario.times.length ? scenario.times : [0];
  const zAxis = axes.z || [0];
  const domain = scenario.domain || { x: [0, 100], y: [-25, 25], z: [0, 40] };
  const source = scenario.source_box || [[30, -6, 0], [40, 6, 10]];
  const wind = scenario.wind || { speed_m_s: 0, direction: [1, 0, 0] };

  const ui = {
    species: speciesList.find((s) => s.id === "CO")?.id || speciesList[0]?.id,
    tIdx: times.length - 1,
    zIdx: nearest(zAxis, 1.5),
    pct: 5,
    playing: false,
    data: null,
    drone: meas.rows || [],
  };

  const canvas = el("canvas", { class: "map-canvas" });
  const tip = el("div", { class: "map-tip" });
  const panel = el("div", { class: "map-panel" }, canvas, tip);

  const speciesSelect = el(
    "select",
    { class: "select", style: "min-width:130px" },
    speciesList.map((s) => el("option", { value: s.id }, s.label))
  );
  speciesSelect.value = ui.species;

  const heightSelect = el(
    "select",
    { class: "select", style: "min-width:96px" },
    zAxis.map((z, i) => el("option", { value: String(i) }, `${z.toFixed(1)} m`))
  );
  heightSelect.value = String(ui.zIdx);

  const timeRange = el("input", { type: "range", min: 0, max: Math.max(0, times.length - 1), step: 1, value: ui.tIdx, style: "width:220px" });
  const timeValue = el("span", { class: "value" }, `${fmt(times[ui.tIdx])} s`);
  const playBtn = el("button", { class: "btn small", type: "button" }, t("common.play"));

  const pctRange = el("input", { type: "range", min: 1, max: 50, step: 1, value: ui.pct, style: "width:150px" });
  const pctValue = el("span", { class: "value" }, `${ui.pct}%`);

  const controls = el(
    "div",
    { class: "card", style: "margin-bottom:14px" },
    el(
      "div",
      { class: "controls" },
      el("div", { class: "field" }, el("label", {}, t("an.species")), speciesSelect),
      el("div", { class: "field" }, el("label", {}, t("map.height")), heightSelect),
      el(
        "div",
        { class: "field", style: "flex:1;min-width:260px" },
        el("label", {}, t("an.time")),
        el("div", { style: "display:flex;align-items:center;gap:10px" }, timeRange, timeValue, playBtn)
      ),
      el("div", { class: "field" }, el("label", {}, t("map.threshold")), el("div", { style: "display:flex;align-items:center;gap:10px" }, pctRange, pctValue))
    )
  );

  const legMin = el("span", {}, "—");
  const legMax = el("span", {}, "—");
  const legendCard = el(
    "div",
    { class: "card" },
    el("div", { class: "card-head" }, el("div", {}, el("div", { class: "card-title" }, t("map.legend")), el("div", { class: "card-note" }, `${timestr()}`))),
    el(
      "div",
      { class: "map-legend" },
      el("div", { class: "map-legend-bar" }),
      el("div", { class: "map-legend-ticks" }, legMin, legMax)
    )
  );

  const statEls = {};
  const statRow = (id, label) => {
    const v = el("div", { class: "v" }, "—");
    statEls[id] = v;
    return el("div", { class: "map-stat" }, el("div", { class: "k" }, label), v);
  };
  const statsCard = el(
    "div",
    { class: "card", style: "margin-top:14px" },
    el("div", { class: "card-head" }, el("div", {}, el("div", { class: "card-title" }, t("an.stats")), el("div", { class: "card-note" }, "z-slice"))),
    el(
      "div",
      { class: "map-stats" },
      statRow("peak", t("map.peak")),
      statRow("reach", t("map.reach")),
      statRow("area", t("map.area")),
      statRow("dir", t("map.direction")),
      statRow("wind", t("map.wind"))
    )
  );

  const hintCard = el(
    "div",
    { class: "card", style: "margin-top:14px" },
    el("div", { class: "map-note" }, t("map.schematic")),
    el("div", { class: "card-note", style: "margin-top:8px;line-height:1.5" }, t("map.hint"))
  );

  const layout = el(
    "div",
    { class: "map-layout" },
    el("div", {}, controls, panel),
    el("div", {}, legendCard, statsCard, hintCard)
  );

  const node = el("div", {}, layout);

  function timestr() {
    return `${fmt(times[ui.tIdx])} s · z = ${(zAxis[ui.zIdx] ?? 0).toFixed(1)} m`;
  }

  /* ------------------------------------------------------------- rendering */

  let W = 0;
  let H = 0;
  let plot = { x: 0, y: 0, w: 1, h: 1 };
  let geo = null;
  let hover = null;

  const dpr = () => window.devicePixelRatio || 1;

  const toPx = (x, y) => {
    const g = geo;
    return [
      plot.x + ((x - g.x0) / (g.x1 - g.x0)) * plot.w,
      plot.y + plot.h - ((y - g.y0) / (g.y1 - g.y0)) * plot.h,
    ];
  };

  const fromPx = (px, py) => {
    const g = geo;
    return [
      g.x0 + ((px - plot.x) / plot.w) * (g.x1 - g.x0),
      g.y0 + ((plot.y + plot.h - py) / plot.h) * (g.y1 - g.y0),
    ];
  };

  function resize() {
    const rect = panel.getBoundingClientRect();
    W = Math.max(rect.width, 320);
    H = canvas.clientHeight || 560;
    const d = dpr();
    canvas.width = Math.round(W * d);
    canvas.height = Math.round(H * d);
    const ctx2d = canvas.getContext("2d");
    ctx2d.setTransform(d, 0, 0, d, 0, 0);
    draw();
  }

  function offscreen() {
    const d = ui.data;
    if (!d) return null;
    const rows = d.values.length;
    const cols = d.values[0]?.length || 0;
    if (!rows || !cols) return null;
    const off = document.createElement("canvas");
    off.width = cols;
    off.height = rows;
    const octx = off.getContext("2d");
    const img = octx.createImageData(cols, rows);
    const vmax = Math.max(d.stats.max, 1e-9);
    const lmin = Math.log10(vmax) - 3;
    const span = 3;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const v = Number(d.values[r][c]);
        const o = (r * cols + c) * 4;
        if (!(v > 0)) {
          img.data[o + 3] = 0;
          continue;
        }
        const n = clamp((Math.log10(v) - lmin) / span, 0, 1);
        const [rr, gg, bb] = sampleRamp(n);
        img.data[o] = rr;
        img.data[o + 1] = gg;
        img.data[o + 2] = bb;
        img.data[o + 3] = Math.round(40 + 215 * Math.pow(n, 0.55));
      }
    }
    octx.putImageData(img, 0, 0);
    return { canvas: off, rows, cols, vmax };
  }

  function draw() {
    const ctx2d = canvas.getContext("2d");
    if (!ctx2d) return;
    ctx2d.clearRect(0, 0, W, H);
    ctx2d.fillStyle = "#090b0e";
    ctx2d.fillRect(0, 0, W, H);

    const padLeft = 46;
    const padRight = 18;
    const padTop = 30;
    const padBottom = 34;
    plot = { x: padLeft, y: padTop, w: Math.max(40, W - padLeft - padRight), h: Math.max(40, H - padTop - padBottom) };

    geo = ui.geo || {
      x0: domain.x?.[0] ?? 0,
      x1: domain.x?.[1] ?? 100,
      y0: domain.y?.[0] ?? -25,
      y1: domain.y?.[1] ?? 25,
    };

    ctx2d.save();
    ctx2d.strokeStyle = "rgba(255,255,255,0.055)";
    ctx2d.lineWidth = 1;
    ctx2d.font = `9px ${MONO}`;
    ctx2d.fillStyle = "#6b7482";
    for (let gx = Math.ceil(geo.x0 / 10) * 10; gx <= geo.x1; gx += 10) {
      const [px] = toPx(gx, 0);
      ctx2d.beginPath();
      ctx2d.moveTo(px, plot.y);
      ctx2d.lineTo(px, plot.y + plot.h);
      ctx2d.stroke();
      ctx2d.textAlign = "center";
      ctx2d.fillText(String(gx), px, plot.y + plot.h + 14);
    }
    for (let gy = Math.ceil(geo.y0 / 10) * 10; gy <= geo.y1; gy += 10) {
      const [, py] = toPx(0, gy);
      ctx2d.beginPath();
      ctx2d.moveTo(plot.x, py);
      ctx2d.lineTo(plot.x + plot.w, py);
      ctx2d.stroke();
      ctx2d.textAlign = "right";
      ctx2d.fillText(String(gy), plot.x - 8, py + 3);
    }
    ctx2d.strokeStyle = "rgba(255,255,255,0.14)";
    ctx2d.strokeRect(plot.x + 0.5, plot.y + 0.5, plot.w - 1, plot.h - 1);

    ctx2d.textAlign = "center";
    ctx2d.fillStyle = "#7d8797";
    ctx2d.font = `9px ${MONO}`;
    ctx2d.fillText("x, m", plot.x + plot.w / 2, H - 6);
    ctx2d.save();
    ctx2d.translate(11, plot.y + plot.h / 2);
    ctx2d.rotate(-Math.PI / 2);
    ctx2d.fillText("y, m", 0, 0);
    ctx2d.restore();
    ctx2d.restore();

    const off = offscreen();

    ctx2d.save();
    ctx2d.beginPath();
    ctx2d.rect(plot.x, plot.y, plot.w, plot.h);
    ctx2d.clip();

    if (off) {
      ctx2d.imageSmoothingEnabled = true;
      ctx2d.save();
      ctx2d.translate(plot.x, plot.y + plot.h);
      ctx2d.scale(1, -1);
      ctx2d.drawImage(off.canvas, 0, 0, plot.w, plot.h);
      ctx2d.restore();
    }

    if (off && ui.data) {
      const thr = off.vmax * (ui.pct / 100);
      const segs = contour(ui.data.values, off.rows, off.cols, thr);
      ctx2d.save();
      ctx2d.strokeStyle = "rgba(240,163,60,0.92)";
      ctx2d.lineWidth = 1.3;
      ctx2d.shadowColor = "rgba(240,163,60,0.45)";
      ctx2d.shadowBlur = 5;
      ctx2d.beginPath();
      for (const [a, b] of segs) {
        const [ax, ay] = toPx(
          geo.x0 + (a[0] / (off.cols - 1 || 1)) * (geo.x1 - geo.x0),
          geo.y0 + (a[1] / (off.rows - 1 || 1)) * (geo.y1 - geo.y0)
        );
        const [bx, by] = toPx(
          geo.x0 + (b[0] / (off.cols - 1 || 1)) * (geo.x1 - geo.x0),
          geo.y0 + (b[1] / (off.rows - 1 || 1)) * (geo.y1 - geo.y0)
        );
        ctx2d.moveTo(ax, ay);
        ctx2d.lineTo(bx, by);
      }
      ctx2d.stroke();
      ctx2d.restore();

      const axis = [];
      for (let c = 0; c < off.cols; c++) {
        let wsum = 0;
        let vsum = 0;
        let colMax = 0;
        for (let r = 0; r < off.rows; r++) {
          const v = Number(ui.data.values[r][c]);
          if (v > 0) {
            wsum += v * r;
            vsum += v;
            colMax = Math.max(colMax, v);
          }
        }
        if (vsum > 0 && colMax >= thr) {
          axis.push([
            geo.x0 + (c / (off.cols - 1 || 1)) * (geo.x1 - geo.x0),
            geo.y0 + (wsum / vsum / (off.rows - 1 || 1)) * (geo.y1 - geo.y0),
          ]);
        }
      }
      if (axis.length > 1) {
        ctx2d.save();
        ctx2d.strokeStyle = "rgba(255,255,255,0.4)";
        ctx2d.setLineDash([5, 5]);
        ctx2d.lineWidth = 1;
        ctx2d.beginPath();
        axis.forEach(([x, y], i) => {
          const [px, py] = toPx(x, y);
          if (i === 0) ctx2d.moveTo(px, py);
          else ctx2d.lineTo(px, py);
        });
        ctx2d.stroke();
        ctx2d.restore();
      }

      let best = { v: -1, x: geo.x0, y: geo.y0 };
      for (let r = 0; r < off.rows; r++) {
        for (let c = 0; c < off.cols; c++) {
          const v = Number(ui.data.values[r][c]);
          if (v > best.v) {
            best = {
              v,
              x: geo.x0 + (c / (off.cols - 1 || 1)) * (geo.x1 - geo.x0),
              y: geo.y0 + (r / (off.rows - 1 || 1)) * (geo.y1 - geo.y0),
            };
          }
        }
      }
      if (best.v > 0) {
        const [px, py] = toPx(best.x, best.y);
        ctx2d.save();
        ctx2d.strokeStyle = "rgba(255,255,255,0.8)";
        ctx2d.lineWidth = 1;
        ctx2d.beginPath();
        ctx2d.moveTo(px - 7, py);
        ctx2d.lineTo(px + 7, py);
        ctx2d.moveTo(px, py - 7);
        ctx2d.lineTo(px, py + 7);
        ctx2d.stroke();
        ctx2d.restore();
      }
    }

    if (hover) {
      const [px, py] = toPx(hover.x, hover.y);
      ctx2d.save();
      ctx2d.strokeStyle = "rgba(255,255,255,0.28)";
      ctx2d.setLineDash([2, 3]);
      ctx2d.beginPath();
      ctx2d.moveTo(px, plot.y);
      ctx2d.lineTo(px, plot.y + plot.h);
      ctx2d.moveTo(plot.x, py);
      ctx2d.lineTo(plot.x + plot.w, py);
      ctx2d.stroke();
      ctx2d.restore();
    }

    ctx2d.restore();

    const [[sx0, sy0], [sx1, sy1]] = [source[0], source[1]];
    const [p0x, p0y] = toPx(sx0, sy1);
    const [p1x, p1y] = toPx(sx1, sy0);
    ctx2d.save();
    ctx2d.beginPath();
    ctx2d.rect(p0x, p0y, p1x - p0x, p1y - p0y);
    ctx2d.clip();
    ctx2d.strokeStyle = "rgba(240,163,60,0.34)";
    ctx2d.lineWidth = 1;
    for (let i = -H; i < W + H; i += 7) {
      ctx2d.beginPath();
      ctx2d.moveTo(i, 0);
      ctx2d.lineTo(i + H, H);
      ctx2d.stroke();
    }
    ctx2d.restore();
    ctx2d.save();
    ctx2d.strokeStyle = "rgba(240,163,60,0.9)";
    ctx2d.lineWidth = 1.2;
    ctx2d.strokeRect(p0x, p0y, p1x - p0x, p1y - p0y);
    ctx2d.fillStyle = "rgba(240,163,60,0.95)";
    ctx2d.font = `8px ${MONO}`;
    ctx2d.textAlign = "left";
    ctx2d.fillText(t("map.source").toUpperCase(), p0x + 3, p0y - 4);
    ctx2d.restore();

    if (ui.drone.length) {
      ctx2d.save();
      ctx2d.fillStyle = "rgba(88,166,214,0.75)";
      for (const r of ui.drone) {
        const [px, py] = toPx(r.x, r.y);
        ctx2d.beginPath();
        ctx2d.arc(px, py, 1.6, 0, Math.PI * 2);
        ctx2d.fill();
      }
      ctx2d.restore();
    }

    const az = azimuth(wind.direction);
    const arrow = { x: plot.x + plot.w - 74, y: plot.y + 16 };
    ctx2d.save();
    ctx2d.translate(arrow.x, arrow.y);
    ctx2d.rotate(((az - 90) * Math.PI) / 180);
    ctx2d.strokeStyle = "rgba(255,255,255,0.6)";
    ctx2d.fillStyle = "rgba(255,255,255,0.6)";
    ctx2d.lineWidth = 1;
    ctx2d.beginPath();
    ctx2d.moveTo(-14, 0);
    ctx2d.lineTo(10, 0);
    ctx2d.moveTo(10, 0);
    ctx2d.lineTo(4, -3);
    ctx2d.moveTo(10, 0);
    ctx2d.lineTo(4, 3);
    ctx2d.stroke();
    ctx2d.restore();
    ctx2d.save();
    ctx2d.fillStyle = "#8b95a6";
    ctx2d.font = `8.5px ${MONO}`;
    ctx2d.textAlign = "right";
    ctx2d.fillText(`WIND ${fmt(wind.speed_m_s)} m/s · ${String(Math.round(az)).padStart(3, "0")}°`, plot.x + plot.w - 4, plot.y + 34);
    ctx2d.restore();

    ctx2d.save();
    ctx2d.strokeStyle = "rgba(255,255,255,0.5)";
    ctx2d.fillStyle = "rgba(255,255,255,0.5)";
    ctx2d.lineWidth = 1;
    const nx = plot.x + plot.w - 18;
    const ny = plot.y + 58;
    ctx2d.beginPath();
    ctx2d.moveTo(nx, ny + 12);
    ctx2d.lineTo(nx, ny - 8);
    ctx2d.moveTo(nx, ny - 8);
    ctx2d.lineTo(nx - 3, ny - 3);
    ctx2d.moveTo(nx, ny - 8);
    ctx2d.lineTo(nx + 3, ny - 3);
    ctx2d.stroke();
    ctx2d.font = `9px ${MONO}`;
    ctx2d.textAlign = "center";
    ctx2d.fillText("N", nx, ny + 22);
    ctx2d.restore();

    drawScale(ctx2d);
  }

  function drawScale(ctx2d) {
    const span = Math.max(1, geo.x1 - geo.x0);
    let unit = 5;
    for (const u of [5, 10, 20, 25, 50]) {
      if (u / span <= 0.28) unit = u;
    }
    const px = (unit / span) * plot.w;
    const x0 = plot.x + 12;
    const y0 = plot.y + plot.h - 12;
    ctx2d.save();
    ctx2d.strokeStyle = "rgba(255,255,255,0.55)";
    ctx2d.fillStyle = "rgba(255,255,255,0.55)";
    ctx2d.lineWidth = 1;
    ctx2d.beginPath();
    ctx2d.moveTo(x0, y0);
    ctx2d.lineTo(x0 + px, y0);
    ctx2d.moveTo(x0, y0 - 3);
    ctx2d.lineTo(x0, y0 + 3);
    ctx2d.moveTo(x0 + px, y0 - 3);
    ctx2d.lineTo(x0 + px, y0 + 3);
    ctx2d.stroke();
    ctx2d.font = `8.5px ${MONO}`;
    ctx2d.textAlign = "left";
    ctx2d.fillText(`${unit} m`, x0, y0 - 5);
    ctx2d.restore();
  }

  /* ---------------------------------------------------------------- update */

  function stats() {
    const d = ui.data;
    if (!d) return null;
    const rows = d.values.length;
    const cols = d.values[0]?.length || 0;
    const thr = Math.max(d.stats.max, 1e-9) * (ui.pct / 100);
    const cell = ((geo.x1 - geo.x0) / Math.max(1, cols - 1)) * ((geo.y1 - geo.y0) / Math.max(1, rows - 1));
    let best = { v: -1, x: geo.x0, y: geo.y0 };
    let area = 0;
    let reach = geo.x0;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const v = Number(d.values[r][c]);
        const x = geo.x0 + (c / Math.max(1, cols - 1)) * (geo.x1 - geo.x0);
        if (v > best.v) {
          best = { v, x, y: geo.y0 + (r / Math.max(1, rows - 1)) * (geo.y1 - geo.y0) };
        }
        if (v >= thr) {
          area += cell;
          reach = Math.max(reach, x);
        }
      }
    }
    return { best, area, reach, thr };
  }

  function updateStats() {
    const st = stats();
    if (!st) return;
    const az = azimuth(wind.direction);
    const [bx, by] = [st.best.x, st.best.y];
    const srcX = source[0]?.[0] ?? geo.x0;
    statEls.peak.innerHTML = `${sci(st.best.v)} <small>µg/m³</small>`;
    statEls.reach.innerHTML = `${fmt(Math.max(0, st.reach - srcX))} <small>m</small>`;
    statEls.area.innerHTML = `${fmt(st.area)} <small>m²</small>`;
    statEls.dir.innerHTML = `${String(Math.round(az)).padStart(3, "0")}°`;
    statEls.wind.innerHTML = `${fmt(wind.speed_m_s)} <small>m/s</small>`;
    statEls.peak.title = `x ${bx.toFixed(1)} m · y ${by.toFixed(1)} m`;
    statEls.reach.title = `x ${st.reach.toFixed(1)} m (source x ${srcX.toFixed(1)} m)`;
  }

  function updateLegend() {
    const d = ui.data;
    if (!d) return;
    legMin.textContent = "0";
    legMax.textContent = `${sci(d.stats.max)} µg/m³`;
    const note = legendCard.querySelector(".card-note");
    if (note) note.textContent = timestr();
  }

  function readout(px, py) {
    const d = ui.data;
    if (!d) return null;
    const rows = d.values.length;
    const cols = d.values[0]?.length || 0;
    const [x, y] = fromPx(px, py);
    const c = clamp(Math.round(((x - geo.x0) / (geo.x1 - geo.x0)) * (cols - 1)), 0, cols - 1);
    const r = clamp(Math.round(((y - geo.y0) / (geo.y1 - geo.y0)) * (rows - 1)), 0, rows - 1);
    const v = Number(d.values[r][c]);
    return { x, y, v, px, py };
  }

  let loadToken = 0;
  async function load() {
    const token = ++loadToken;
    try {
      const data = await api.slice(scenario.id, {
        species: ui.species,
        t: times[ui.tIdx],
        axis: "z",
        index: ui.zIdx,
      });
      if (token !== loadToken) return;
      ui.data = data;
      ui.geo = {
        x0: Number(data.horizontal?.min ?? domain.x?.[0] ?? 0),
        x1: Number(data.horizontal?.max ?? domain.x?.[1] ?? 100),
        y0: Number(data.vertical?.min ?? domain.y?.[0] ?? -25),
        y1: Number(data.vertical?.max ?? domain.y?.[1] ?? 25),
      };
      draw();
      updateLegend();
      updateStats();
    } catch (_) {
      if (token === loadToken) tip.textContent = t("map.empty");
    }
  }

  function setPlaying(on) {
    ui.playing = on;
    playBtn.textContent = on ? t("common.pause") : t("common.play");
    playBtn.classList.toggle("primary", on);
    if (on) {
      playTimer = setInterval(() => {
        ui.tIdx = (ui.tIdx + 1) % times.length;
        timeRange.value = String(ui.tIdx);
        timeValue.textContent = `${fmt(times[ui.tIdx])} s`;
        load();
      }, 900);
    } else {
      clearInterval(playTimer);
      playTimer = null;
    }
  }

  let playTimer = null;

  speciesSelect.addEventListener("change", () => {
    ui.species = speciesSelect.value;
    load();
  });
  heightSelect.addEventListener("change", () => {
    ui.zIdx = Number(heightSelect.value);
    load();
  });
  timeRange.addEventListener("input", () => {
    ui.tIdx = Number(timeRange.value);
    timeValue.textContent = `${fmt(times[ui.tIdx])} s`;
    load();
  });
  pctRange.addEventListener("input", () => {
    ui.pct = Number(pctRange.value);
    pctValue.textContent = `${ui.pct}%`;
    draw();
    updateStats();
  });
  playBtn.addEventListener("click", () => setPlaying(!ui.playing));

  canvas.addEventListener("pointermove", (e) => {
    const rect = canvas.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    if (px < plot.x || px > plot.x + plot.w || py < plot.y || py > plot.y + plot.h) {
      hover = null;
      tip.style.opacity = "0";
      draw();
      return;
    }
    const p = readout(px, py);
    if (!p) return;
    hover = { x: p.x, y: p.y };
    draw();
    const sp = scenario.species.find((s) => s.id === ui.species);
    tip.innerHTML = `<div class="tip-k">${t("map.readout")}</div>
      <div class="tip-v">x ${p.x.toFixed(1)} · y ${p.y.toFixed(1)} m</div>
      <div class="tip-v" style="color:${speciesColor(ui.species)}">${sci(p.v)} µg/m³</div>
      <div class="tip-k" style="margin-top:4px">${sp?.label || ui.species} · z ${(zAxis[ui.zIdx] ?? 0).toFixed(1)} m</div>`;
    const host = panel.getBoundingClientRect();
    const left = clamp(px + 16, 8, host.width - 170);
    const top = clamp(py - 54, 8, host.height - 96);
    tip.style.left = `${left}px`;
    tip.style.top = `${top}px`;
    tip.style.opacity = "1";
  });
  canvas.addEventListener("pointerleave", () => {
    hover = null;
    tip.style.opacity = "0";
    draw();
  });

  new ResizeObserver(() => resize()).observe(panel);
  resize();
  await load();

  return node;
}

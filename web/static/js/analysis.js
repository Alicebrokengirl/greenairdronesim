import { api, el, fmt, sci, when, toast, speciesColor } from "./api.js";
import { t } from "./i18n.js";
import { initChart, AXIS, TOOLTIP } from "./charts.js";

const HEAT = ["#0a1420", "#10263c", "#173c58", "#25597a", "#3a7f92", "#63a69a", "#9cc383", "#d8cf72", "#f0a33c", "#e2553d"];
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const nearest = (arr, v) => arr.reduce((best, x, i) => (Math.abs(x - v) < Math.abs(arr[best] - v) ? i : best), 0);

export async function renderAnalysis(ctx) {
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  const sid = params.get("scenario") || ctx.state.sid;
  const scenario = ctx.scenarioById(sid);
  if (!scenario) return el("div", { class: "empty" }, t("an.empty"));

  const [axes, ts] = await Promise.all([api.axes(scenario.id), api.timeseries(scenario.id)]);
  const times = scenario.times.length ? scenario.times : ts.times;
  const speciesList = scenario.species;

  const ui = {
    species: speciesList.find((s) => s.id === "CO")?.id || speciesList[0]?.id,
    tIdx: Math.max(0, times.length - 1),
    axis: "z",
    index: null,
    decades: 4,
    playing: false,
    data: null,
  };
  ui.index = defaultIndex("z");

  function defaultIndex(axis) {
    if (axis === "z") return nearest(axes.z, 5);
    if (axis === "y") return nearest(axes.y, 0);
    return nearest(axes.x, 35);
  }

  /* --------------------------------------------------------------- layout */
  const speciesSelect = el(
    "select",
    { class: "select", style: "min-width:150px" },
    speciesList.map((s) => el("option", { value: s.id }, s.label))
  );
  speciesSelect.value = ui.species;

  const planeSeg = el(
    "div",
    { class: "seg" },
    [
      ["z", t("an.plane.z")],
      ["y", t("an.plane.y")],
      ["x", t("an.plane.x")],
    ].map(([id, label]) => el("button", { type: "button", "data-axis": id, class: id === "z" ? "active" : "" }, label))
  );

  const timeRange = el("input", { type: "range", min: 0, max: times.length - 1, step: 1, value: ui.tIdx, style: "width:230px" });
  const timeValue = el("span", { class: "value" }, `${fmt(times[ui.tIdx])} s`);
  const playBtn = el("button", { class: "btn small", type: "button" }, t("common.play"));

  const indexRange = el("input", { type: "range", min: 0, max: axes.z.length - 1, step: 1, value: ui.index, style: "width:190px" });
  const indexValue = el("span", { class: "value" }, `${axes.z[ui.index].toFixed(1)} m`);

  const decadesRange = el("input", { type: "range", min: 1, max: 5, step: 1, value: ui.decades, style: "width:150px" });
  const decadesValue = el("span", { class: "value" }, `${ui.decades} dec`);

  const controls = el(
    "div",
    { class: "card", style: "margin-bottom:16px" },
    el(
      "div",
      { class: "controls" },
      el("div", { class: "field" }, el("label", {}, t("an.species")), speciesSelect),
      el("div", { class: "field" }, el("label", {}, t("an.plane")), planeSeg),
      el("div", { class: "field", style: "flex:1;min-width:240px" }, el("label", {}, t("an.time")), el("div", { style: "display:flex;align-items:center;gap:10px" }, timeRange, timeValue, playBtn)),
      el("div", { class: "field" }, el("label", {}, t("an.index")), el("div", { style: "display:flex;align-items:center;gap:10px" }, indexRange, indexValue)),
      el("div", { class: "field" }, el("label", {}, t("an.range")), el("div", { style: "display:flex;align-items:center;gap:10px" }, decadesRange, decadesValue))
    )
  );

  const sliceTitle = el("div", { class: "card-title" }, t("an.chart.slice"));
  const sliceNote = el("div", { class: "card-note" }, "");
  const sliceChartEl = el("div", { class: "chart", id: "slice-chart" });
  const planeBadge = el("span", { class: "pill", id: "slice-plane" }, "—");
  const legMin = el("span", {}, "—");
  const legMax = el("span", {}, "—");

  const sliceCard = el(
    "div",
    { class: "card", style: "padding:16px 16px 12px" },
    el("div", { class: "card-head" }, el("div", {}, sliceTitle, sliceNote), planeBadge),
    sliceChartEl,
    el("div", { class: "legend-scale" }, legMin, el("div", { class: "legend-bar" }), legMax)
  );

  const tsChartEl = el("div", { class: "chart small", id: "ts-chart" });
  const tsCard = el(
    "div",
    { class: "card", style: "margin-top:16px" },
    el("div", { class: "card-head" }, el("div", {}, el("div", { class: "card-title" }, t("an.chart.timeseries")), el("div", { class: "card-note" }, scenario.title))),
    tsChartEl
  );

  const statDefs = [
    ["max", t("an.stat.max")],
    ["p95", t("an.stat.p95")],
    ["mean", t("an.stat.mean")],
    ["p50", t("an.stat.p50")],
    ["min", t("an.stat.min")],
    ["plane", t("an.plane")],
  ];
  const statEls = {};
  const statsCard = el(
    "div",
    { class: "card" },
    el("div", { class: "card-head" }, el("div", {}, el("div", { class: "card-title" }, t("an.stats")), el("div", { class: "card-note" }, `${scenario.title} · ${scenario.model_run}`))),
    el(
      "div",
      { class: "statgrid" },
      statDefs.map(([id, label]) => {
        const v = el("div", { class: "v" }, "—");
        statEls[id] = v;
        return el("div", { class: "stat" }, el("div", { class: "k" }, label), v);
      })
    )
  );

  const sp = speciesList.find((s) => s.id === ui.species) || {};
  const infoCard = el(
    "div",
    { class: "card", style: "margin-top:16px" },
    el("div", { class: "card-head" }, el("div", {}, el("div", { class: "card-title" }, t("an.meta")), el("div", { class: "card-note" }, `${scenario.domain?.x?.[0]}–${scenario.domain?.x?.[1]} m domain`))),
    el(
      "div",
      { class: "sc-meta" },
      el("div", {}, el("div", { class: "k" }, t("an.wind")), el("div", { class: "v" }, `${scenario.wind?.speed_m_s ?? "—"} m/s → +x`)),
      el("div", {}, el("div", { class: "k" }, t("an.sourceBox")), el("div", { class: "v" }, (scenario.source_box || []).map((p) => `[${p.join(", ")}]`).join(" "))),
      el("div", {}, el("div", { class: "k" }, t("an.frames")), el("div", { class: "v" }, `${scenario.frame_count} · ${fmt(scenario.duration_s)} s`)),
      el("div", {}, el("div", { class: "k" }, t("an.mesh")), el("div", { class: "v" }, `${fmt(scenario.mesh_cells)}`))
    ),
    el("div", { class: "note", style: "margin-top:12px" }, scenario.parameter_warning || (scenario.limitations?.[0] || ""))
  );

  const layout = el(
    "div",
    { class: "analysis-layout" },
    el("div", {}, sliceCard, tsCard),
    el("div", {}, statsCard, infoCard)
  );

  const node = el("div", {}, controls, layout);

  /* --------------------------------------------------------------- charts */
  const sliceChart = initChart(sliceChartEl);
  const tsChart = initChart(tsChartEl);

  function updateLegend(vmin, vmax) {
    legMin.textContent = `${sci(vmin)} µg/m³`;
    legMax.textContent = `${sci(vmax)} µg/m³`;
  }

  function renderHeatmap(data) {
    ui.data = data;
    const values = data.values;
    const rows = values.length;
    const cols = values[0]?.length || 0;
    const vmax = Math.max(data.stats.max, 1e-6);
    const vmin = Math.max(vmax / 10 ** ui.decades, 1e-9);
    const lmin = Math.log10(vmin);
    const span = Math.max(Math.log10(vmax) - lmin, 1e-6);

    const hName = data.horizontal.name;
    const vName = data.vertical.name;
    const hMin = data.horizontal.min;
    const hMax = data.horizontal.max;
    const vMin = data.vertical.min;
    const vMax = data.vertical.max;
    const hCoords = Array.from({ length: cols }, (_, i) => hMin + ((hMax - hMin) * i) / Math.max(cols - 1, 1));
    const vCoords = Array.from({ length: rows }, (_, i) => vMin + ((vMax - vMin) * i) / Math.max(rows - 1, 1));

    const raw = new Array(rows * cols);
    const pts = [];
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const v = Number(values[r][c]);
        raw[r * cols + c] = v;
        if (v > 0) {
          const n = clamp((Math.log10(v) - lmin) / span, 0, 1);
          pts.push([c, r, Number(n.toFixed(4))]);
        }
      }
    }

    const stepX = Math.max(1, Math.ceil(cols / 8));
    const stepY = Math.max(1, Math.ceil(rows / 7));

    sliceChart.setOption(
      {
        animation: false,
        grid: { left: 50, right: 18, top: 12, bottom: 40 },
        tooltip: {
          ...TOOLTIP,
          formatter: (p) => {
            const [c, r] = p.data;
            const v = raw[r * cols + c];
            return `<div style="font-weight:650;margin-bottom:4px;color:${speciesColor(data.species)}">${data.display} · ${sci(v)} µg/m³</div>
              <div style="color:#8d9aad">${hName} = ${hCoords[c].toFixed(1)} m<br/>${vName} = ${vCoords[r].toFixed(1)} m</div>`;
          },
        },
        xAxis: {
          type: "category",
          data: hCoords.map((v) => Number(v.toFixed(2))),
          name: `${hName}, m`,
          nameLocation: "middle",
          nameGap: 26,
          nameTextStyle: { color: AXIS.text, fontSize: 11 },
          axisLabel: { color: AXIS.text, fontSize: 10.5, interval: (i) => i % stepX === 0, formatter: (v) => Math.round(Number(v)) },
          axisLine: { lineStyle: { color: AXIS.line } },
          axisTick: { show: false },
          splitLine: { show: false },
        },
        yAxis: {
          type: "category",
          data: vCoords.map((v) => Number(v.toFixed(2))),
          name: `${vName}, m`,
          nameLocation: "middle",
          nameGap: 38,
          nameTextStyle: { color: AXIS.text, fontSize: 11 },
          axisLabel: { color: AXIS.text, fontSize: 10.5, interval: (i) => i % stepY === 0, formatter: (v) => Math.round(Number(v)) },
          axisLine: { lineStyle: { color: AXIS.line } },
          axisTick: { show: false },
          splitLine: { show: false },
        },
        visualMap: { show: false, min: 0, max: 1, inRange: { color: HEAT } },
        series: [
          {
            type: "heatmap",
            data: pts,
            progressive: 0,
            itemStyle: { borderWidth: 0 },
            emphasis: { itemStyle: { borderColor: "rgba(255,255,255,.7)", borderWidth: 1 } },
          },
        ],
      },
      true
    );

    updateLegend(vmin, vmax);
    const coord = Number(data.coord);
    const planeName = data.axis === "z" ? "z" : data.axis === "y" ? "y" : "x";
    sliceTitle.textContent = t("an.chart.slice");
    sliceNote.textContent = `${data.display} · ${fmt(data.time)} s · ${planeName} = ${coord.toFixed(1)} m`;
    planeBadge.textContent = `${data.axis.toUpperCase()} · ${coord.toFixed(1)} m`;

    statEls.max.innerHTML = `${sci(data.stats.max)} <small>µg/m³</small>`;
    statEls.p95.innerHTML = `${sci(data.stats.p95)} <small>µg/m³</small>`;
    statEls.mean.innerHTML = `${sci(data.stats.mean)} <small>µg/m³</small>`;
    statEls.p50.innerHTML = `${sci(data.stats.p50)} <small>µg/m³</small>`;
    statEls.min.innerHTML = `${data.stats.min < 1e-3 ? "0" : sci(data.stats.min)} <small>µg/m³</small>`;
    statEls.plane.textContent = `${coord.toFixed(1)} m`;
  }

  function renderTimeseries() {
    const series = ts.series[ui.species];
    if (!series) return;
    const labels = ts.times.map((v) => String(v));
    const color = speciesColor(ui.species);
    const mark =
      labels.length && ui.tIdx < labels.length
        ? {
            symbol: "none",
            silent: true,
            label: { show: false },
            lineStyle: { color: "rgba(255,255,255,0.35)", width: 1, type: "dashed" },
            data: [{ xAxis: labels[ui.tIdx] }],
          }
        : undefined;
    tsChart.setOption(
      {
        grid: { left: 56, right: 16, top: 18, bottom: 32 },
        tooltip: { ...TOOLTIP, trigger: "axis", valueFormatter: (v) => `${sci(v)} µg/m³` },
        xAxis: {
          type: "category",
          data: labels,
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
            name: "max",
            type: "line",
            data: series.max,
            smooth: true,
            showSymbol: true,
            symbolSize: 4,
            lineStyle: { color, width: 2 },
            itemStyle: { color },
            areaStyle: {
              color: {
                type: "linear",
                x: 0, y: 0, x2: 0, y2: 1,
                colorStops: [
                  { offset: 0, color: color + "44" },
                  { offset: 1, color: color + "00" },
                ],
              },
            },
            markLine: mark,
          },
          {
            name: "mean",
            type: "line",
            data: series.mean,
            smooth: true,
            showSymbol: false,
            lineStyle: { color: "rgba(255,255,255,0.22)", width: 1.4, type: "dashed" },
          },
        ],
        legend: { show: false },
      },
      true
    );
  }

  let sliceToken = 0;
  async function loadSlice() {
    const token = ++sliceToken;
    try {
      const data = await api.slice(scenario.id, {
        species: ui.species,
        t: times[ui.tIdx],
        axis: ui.axis,
        index: ui.index,
      });
      if (token !== sliceToken) return;
      ui.index = data.index;
      indexRange.value = String(ui.index);
      renderHeatmap(data);
    } catch (err) {
      if (token === sliceToken) toast(t("common.error"));
    }
  }

  function syncIndexUI() {
    indexRange.max = String(axes[ui.axis].length - 1);
    indexRange.value = String(ui.index);
    indexValue.textContent = `${axes[ui.axis][ui.index]?.toFixed(1) ?? "—"} m`;
  }

  /* --------------------------------------------------------------- events */
  speciesSelect.addEventListener("change", () => {
    ui.species = speciesSelect.value;
    renderTimeseries();
    loadSlice();
  });

  planeSeg.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-axis]");
    if (!b) return;
    ui.axis = b.dataset.axis;
    planeSeg.querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
    ui.index = defaultIndex(ui.axis);
    syncIndexUI();
    loadSlice();
  });

  timeRange.addEventListener("input", () => {
    ui.tIdx = Number(timeRange.value);
    timeValue.textContent = `${fmt(times[ui.tIdx])} s`;
    renderTimeseries();
    loadSlice();
  });

  indexRange.addEventListener("input", () => {
    ui.index = Number(indexRange.value);
    indexValue.textContent = `${axes[ui.axis][ui.index]?.toFixed(1) ?? "—"} m`;
  });
  indexRange.addEventListener("change", loadSlice);

  decadesRange.addEventListener("input", () => {
    ui.decades = Number(decadesRange.value);
    decadesValue.textContent = `${ui.decades} dec`;
    if (ui.data) renderHeatmap(ui.data);
  });

  let playTimer = null;
  function setPlaying(on) {
    ui.playing = on;
    playBtn.textContent = on ? t("common.pause") : t("common.play");
    playBtn.classList.toggle("primary", on);
    if (on) {
      playTimer = setInterval(() => {
        ui.tIdx = (ui.tIdx + 1) % times.length;
        timeRange.value = String(ui.tIdx);
        timeValue.textContent = `${fmt(times[ui.tIdx])} s`;
        renderTimeseries();
        loadSlice();
      }, 700);
    } else {
      clearInterval(playTimer);
      playTimer = null;
    }
  }
  playBtn.addEventListener("click", () => setPlaying(!ui.playing));

  tsChart.on("click", (p) => {
    if (p.componentType !== "series") return;
    ui.tIdx = p.dataIndex;
    timeRange.value = String(ui.tIdx);
    timeValue.textContent = `${fmt(times[ui.tIdx])} s`;
    renderTimeseries();
    loadSlice();
  });

  syncIndexUI();
  renderTimeseries();
  await loadSlice();

  return node;
}


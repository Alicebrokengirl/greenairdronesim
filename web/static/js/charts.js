const registry = new Set();

export function initChart(dom) {
  const chart = echarts.init(dom, null, { renderer: "canvas" });
  registry.add(chart);
  return chart;
}

export function disposeCharts() {
  for (const c of registry) {
    try {
      c.dispose();
    } catch (_) {}
  }
  registry.clear();
}

let timer;
window.addEventListener("resize", () => {
  clearTimeout(timer);
  timer = setTimeout(() => {
    for (const c of registry) c.resize();
  }, 120);
});

export const PALETTE = ["#f0a33c", "#58a6d6", "#d2689a", "#8ab66b", "#c9a227", "#9b8ad4", "#6fb3ae"];

export const AXIS = {
  line: "rgba(255,255,255,0.10)",
  text: "#7d8797",
  split: "rgba(255,255,255,0.055)",
};

export const TOOLTIP = {
  backgroundColor: "rgba(14,17,21,0.97)",
  borderColor: "rgba(255,255,255,0.12)",
  borderWidth: 1,
  padding: [8, 10],
  textStyle: { color: "#e6e9ee", fontSize: 11.5 },
  extraCssText: "box-shadow:0 8px 24px rgba(0,0,0,.5);",
};

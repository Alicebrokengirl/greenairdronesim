const cache = new Map();

async function get(path, ttl = 60000) {
  const now = Date.now();
  const hit = cache.get(path);
  if (hit && now - hit.at < ttl) return hit.value;
  const res = await fetch(path, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  const value = await res.json();
  cache.set(path, { at: now, value });
  return value;
}

export const api = {
  overview: () => get("/api/overview", 15000),
  scenarios: () => get("/api/scenarios", 15000),
  scenario: (sid) => get(`/api/scenario/${sid}`, 15000),
  axes: (sid) => get(`/api/scenario/${sid}/axes`, 60000),
  timeseries: (sid) => get(`/api/scenario/${sid}/timeseries`, 30000),
  measurements: (sid) => get(`/api/scenario/${sid}/measurements`, 30000),
  slice: (sid, { species, t, axis, index }) => {
    const q = new URLSearchParams({ species, t, axis });
    if (index !== undefined && index !== null) q.set("index", index);
    return get(`/api/scenario/${sid}/slice?${q}`, 120000);
  },
  isaac: () => get("/api/isaac/status", 5000),
  switchIsaac: (sid) =>
    fetch(`/api/isaac/scenario/${sid}`, { method: "POST" }).then((r) => r.json()),
};

export const SPECIES_COLORS = {
  CO: "#ffb454",
  NO2: "#ff6b8a",
  SO2: "#c08bff",
  PM25: "#61a8ff",
  PM10: "#3ee0c4",
  VOC: "#9be15d",
  HCl: "#ffd166",
  HCHO: "#f78fb3",
  HCN: "#7bdff2",
  BENZENE: "#e0aaff",
};

const LOCALES = { en: "en-US", uk: "uk-UA", ru: "ru-RU" };
export function locale() { return LOCALES[localStorage.getItem("gad.lang")] || "en-US"; }

const intFmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const oneFmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

export function fmt(v, digits = 0) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  if (digits === 0) return intFmt.format(v);
  return oneFmt.format(v);
}

export function sci(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  if (v === 0) return "0";
  const abs = Math.abs(v);
  if (abs >= 100000) {
    const e = Math.floor(Math.log10(abs));
    const m = (v / 10 ** e).toFixed(1);
    return `${m}×10${sup(e)}`;
  }
  if (abs >= 1000) return intFmt.format(v);
  if (abs >= 10) return oneFmt.format(v);
  if (abs >= 1) return v.toFixed(2);
  if (abs < 0.01) {
    const e = Math.floor(Math.log10(abs));
    const m = (v / 10 ** e).toFixed(1);
    return `${m}×10${sup(e)}`;
  }
  return v.toPrecision(2);
}

function sup(n) {
  const map = { "-": "⁻", 0: "⁰", 1: "¹", 2: "²", 3: "³", 4: "⁴", 5: "⁵", 6: "⁶", 7: "⁷", 8: "⁸", 9: "⁹" };
  return String(n)
    .split("")
    .map((c) => map[c] ?? c)
    .join("");
}

export function when(ts) {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  return d.toLocaleString(locale(), {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function speciesColor(s) {
  return SPECIES_COLORS[s] || "#8d9aad";
}

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined) continue;
    node.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return node;
}

let toastTimer;
export function toast(msg) {
  const node = document.getElementById("toast");
  if (!node) return;
  node.textContent = msg;
  node.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("show"), 2600);
}

export function loadingHtml(label = "Loading") {
  return `<div class="empty"><div class="pill"><i class="dot"></i>${label}…</div></div>`;
}

export function errorHtml(message, retry = "Retry") {
  return `<div class="empty"><p>${message}</p><button class="btn" onclick="location.reload()">${retry}</button></div>`;
}




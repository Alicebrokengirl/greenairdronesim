import { api, el, fmt, sci, toast, speciesColor } from "./api.js";
import { t, lang } from "./i18n.js";

const unitTh = (label) => {
  const i = label.lastIndexOf(",");
  if (i < 0) return el("th", {}, label);
  return el(
    "th",
    {},
    label.slice(0, i),
    " ",
    el("span", { style: "text-transform:none;letter-spacing:0.02em" }, label.slice(i + 1).trim())
  );
};
const UNIT_HEAD = () => unitTh(t("rep.peakUnit"));

export async function renderReport(ctx) {
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  const sid = params.get("scenario") || ctx.state.sid;
  const scenario = ctx.scenarioById(sid);
  if (!scenario) return el("div", { class: "empty" }, t("common.error"));

  const meas = await api.measurements(scenario.id);
  const maxEntries = Object.entries(scenario.maxima).sort((a, b) => b[1].ug_m3 - a[1].ug_m3);
  const generated = new Date();

  const measured = {};
  for (const sp of meas.species) {
    const vals = meas.rows.map((r) => r.values[sp]).filter((v) => v != null && v > 0);
    if (vals.length) {
      measured[sp] = {
        max: Math.max(...vals),
        mean: vals.reduce((a, b) => a + b, 0) / vals.length,
        n: vals.length,
      };
    }
  }

  const d = scenario.domain || {};
  const step = scenario.duration_s / Math.max(scenario.frame_count - 1, 1);
  const lastT = meas.rows[meas.rows.length - 1]?.t ?? 0;
  const firstT = meas.rows[0]?.t ?? 0;

  const report = el(
    "div",
    { class: "report" },
    el(
      "div",
      { class: "rep-head" },
      el(
        "div",
        {},
        el("div", { class: "page-kicker" }, "GreenAirDrone"),
        el("h1", {}, t("rep.heading")),
        el("p", { style: "margin:4px 0 0" }, `${scenario.title} · ${scenario.category}`),
        el("p", { style: "margin:2px 0 0;font-size:12px" }, scenario.description)
      ),
      el(
        "div",
        { class: "stamp" },
        el("div", {}, `${t("rep.generated")}: ${generated.toLocaleString()}`),
        el("div", {}, `${t("rep.source")}: ${scenario.model_run}`),
        el("div", {}, `OpenFOAM ${scenario.openfoam_version || ""}`.trim())
      )
    ),

    el("h2", {}, t("rep.conditions")),
    el(
      "table",
      {},
      el(
        "tbody",
        {},
        [
          [t("rep.wind"), `${scenario.wind?.speed_m_s ?? "—"} m/s → +x`],
          [t("rep.domain"), `x ${fmt(d.x?.[0])}–${fmt(d.x?.[1])} m · y ${fmt(d.y?.[0])}–${fmt(d.y?.[1])} m · z ${fmt(d.z?.[0])}–${fmt(d.z?.[1])} m`],
          [t("rep.mesh"), `${fmt(scenario.mesh_cells)} cells · ${scenario.grid_shape.join(" × ")}`],
          [t("rep.sourceBox"), (scenario.source_box || []).map((p) => `[${p.join(", ")}]`).join("  ")],
          [t("rep.frames"), `${scenario.frame_count} · 0–${fmt(scenario.duration_s)} s @ ${step.toFixed(0)} s`],
          [t("rep.samples"), String(meas.rows.length)],
          [t("rep.kind"), scenario.kind || "—"],
        ].map(([k, v]) => el("tr", {}, el("td", {}, k), el("td", { style: "text-align:right" }, v)))
      )
    ),

    el("h2", {}, t("rep.species")),
    el(
      "table",
      {},
      el(
        "thead",
        {},
        el(
          "tr",
          {},
          [
            t("sc.th.species"),
            t("rep.unit"),
            t("sc.th.phase"),
            t("rep.rate"),
            UNIT_HEAD(),
            t("rep.stored"),
            t("sc.provenance"),
          ].map((h) => (h instanceof Node ? h : el("th", {}, h)))
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
            el("td", { class: "u" }, "kg/m³ → µg/m³"),
            el("td", {}, m.phase || "—"),
            el("td", { style: "text-align:right" }, m.rate_kg_s != null ? sci(m.rate_kg_s) : "—"),
            el("td", { style: "text-align:right" }, sci(m.ug_m3)),
            el("td", { style: "text-align:right" }, sci(m.stored_kg)),
            el("td", { style: "text-align:right;font-size:11px;color:var(--muted-2)" }, m.provenance || "—")
          )
        )
      )
    ),

    el("h2", {}, t("rep.maxima")),
    el(
      "table",
      {},
      el(
        "thead",
        {},
        el(
          "tr",
          {},
          [t("sc.th.species"), UNIT_HEAD(), t("rep.location"), unitTh(t("rep.peakMeasured")), unitTh(t("rep.meanMeasured"))].map((h) =>
            h instanceof Node ? h : el("th", {}, h)
          )
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
            el("td", { style: "text-align:right" }, sci(m.ug_m3)),
            el("td", { style: "text-align:right" }, m.location_m ? m.location_m.map((v) => Number(v).toFixed(1)).join(", ") : "—"),
            el("td", { style: "text-align:right" }, measured[id] ? sci(measured[id].max) : "—"),
            el("td", { style: "text-align:right" }, measured[id] ? sci(measured[id].mean) : "—")
          )
        )
      )
    ),

    el("h2", {}, t("rep.limitations")),
    el("ul", {}, (scenario.limitations || []).map((l) => el("li", {}, l))),
    scenario.parameter_warning ? el("p", {}, scenario.parameter_warning) : null,
    scenario.checks && Object.keys(scenario.checks).length
      ? el(
          "p",
          { style: "font-size:12px" },
          `${t("rep.checks")}: ${Object.entries(scenario.checks)
            .map(([k, v]) => `${k} = ${typeof v === "object" ? JSON.stringify(v) : v}`)
            .join("; ")}`
        )
      : null,

    el("h2", {}, t("rep.measurements")),
    el("p", {}, `${meas.rows.length} ${t("rep.samplesNote")} ${fmt(firstT)}–${fmt(lastT)} s.`),
    el("p", { style: "color:var(--muted-2);font-size:12px" }, t("rep.note")),
    el(
      "p",
      { style: "font-size:11px;color:var(--muted-2);margin-top:18px" },
      `${t("rep.source")}: ${scenario.files.export_dir} · ${lang().toUpperCase()}`
    )
  );

  const actions = el(
    "div",
    { class: "no-print", style: "display:flex;gap:10px;justify-content:center;margin-bottom:18px" },
    el("button", { class: "btn primary", onclick: () => window.print() }, t("common.print")),
    el(
      "button",
      {
        class: "btn",
        onclick: () => {
          const payload = {
            product: "GreenAirDrone",
            generated_at: generated.toISOString(),
            scenario: {
              id: scenario.id,
              title: scenario.title,
              model_run: scenario.model_run,
              description: scenario.description,
              wind: scenario.wind,
              domain: scenario.domain,
              source_box: scenario.source_box,
              duration_s: scenario.duration_s,
              mesh_cells: scenario.mesh_cells,
              limitations: scenario.limitations,
              checks: scenario.checks,
            },
            maxima: scenario.maxima,
            measurements: { count: meas.rows.length, summary: measured },
          };
          const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `greenairdrone_${scenario.id}_report.json`;
          a.click();
          URL.revokeObjectURL(url);
          toast(t("rep.exported"));
        },
      },
      t("rep.export")
    )
  );

  return el("div", {}, actions, report);
}

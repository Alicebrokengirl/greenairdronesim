import csv
import json
from pathlib import Path

import numpy as np

root = Path(r"C:\isaac\data\industrial_fire")
exp = root / "export"
meta = json.loads((exp / "metadata.json").read_text())
print("summary:", json.dumps(meta["summary"], indent=1)[:2500])
print("species:", list(meta["species"]))
for t in ("10", "30", "60"):
    d = np.load(exp / f"fields_t{t}.npz")
    print(f"t={t}")
    for s in meta["species"]:
        a = d[s]
        nz = a[a > 0]
        if nz.size:
            p = np.percentile(nz, [50, 90, 99, 99.9])
            print(f"  {s:8s} max={a.max()*1e9:10.1f} ug/m3 cells>0={nz.size:6d} p50/90/99/99.9={np.round(p*1e9,1)}")
        else:
            print(f"  {s:8s} all zero")
    print("  U range", float(d["Ux"].min()), float(d["Ux"].max()))

with open(root / "drone_measurements.csv") as f:
    rows = list(csv.DictReader(f))
xs = np.array([float(r["x_m"]) for r in rows])
ys = np.array([float(r["y_m"]) for r in rows])
zs = np.array([float(r["z_m"]) for r in rows])
ts = np.array([float(r["sim_time_s"]) for r in rows])
print("trajectory rows", len(rows), "t", ts[0], ts[-1])
print("bbox x", xs.min(), xs.max(), "y", ys.min(), ys.max(), "z", zs.min(), zs.max())
print("speed approx", np.round(np.hypot(np.diff(xs), np.diff(ys)) / 0.5, 2)[:20])
for key in ("CO_ug_m3", "PM25_ug_m3", "NO2_ug_m3"):
    vals = np.array([float(r[key]) for r in rows])
    print(key, "max", vals.max(), "at t", ts[vals.argmax()], "min", vals.min())
print("last point", xs[-1], ys[-1], zs[-1])
print("points", list(zip(ts[::20], xs[::20], ys[::20], zs[::20])))

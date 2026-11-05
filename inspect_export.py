import json
import sys
from pathlib import Path

import numpy as np

root = Path(r"\\wsl.localhost\Ubuntu-22.04\home\plato\OpenFOAM\plato-14\run\greenAirDrone_multispecies")
exp = root / "results" / "residential_fire" / "export"
meta = json.loads((exp / "metadata.json").read_text())
print("keys:", sorted(meta.keys()))
print("species:", list(meta["species"]))
print("domain:", meta["domain_m"])
print("source:", meta["source_box_m"])
print("times:", meta["times_s"])
print("grid:", meta["grid_shape_nz_ny_nx"])
for t in ("0", "30"):
    d = np.load(exp / f"fields_t{t}.npz")
    print(f"--- t={t} keys={d.files}")
    for k in d.files:
        a = d[k]
        if a.ndim == 1:
            print(f"  {k}: shape={a.shape} dtype={a.dtype} min={a.min():.6g} max={a.max():.6g}")
        else:
            print(f"  {k}: shape={a.shape} dtype={a.dtype} min={a.min():.6g} max={a.max():.6g}")

with open(exp / "probes.csv") as f:
    print("probes header:", f.readline().strip())
    for _ in range(3):
        print("  ", f.readline().strip())
with open(exp / "timeseries.csv") as f:
    print("timeseries header:", f.readline().strip())
    for _ in range(4):
        print("  ", f.readline().strip())
print("planes:", sorted(p.name for p in (exp / "planes").iterdir())[:20])

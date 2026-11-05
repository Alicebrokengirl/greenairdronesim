from __future__ import annotations

import csv
import json
import math
import os
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.environ.get("GREENAIR_DATA") or (ROOT / "data")).expanduser()
if not DATA_ROOT.is_absolute():
    DATA_ROOT = ROOT / DATA_ROOT
DATA_ROOT = DATA_ROOT.resolve()
CAPTURES_DIR = Path(
    os.environ.get("GREENAIR_CAPTURES") or (ROOT / "greenair" / "captures")
).expanduser().resolve()
ISAAC_STATUS = CAPTURES_DIR / "status.json"

SCENARIO_META = {
    "industrial_fire": {
        "title": "Industrial fire",
        "model_run": "industrial_fire",
        "category": "Industry",
        "accent": "#ff8a3d",
        "context": "Fire at an industrial site with plastics and stored materials.",
        "aliases": [],
    },
    "urban_infrastructure_fire": {
        "title": "Urban infrastructure fire",
        "model_run": "residential_fire",
        "category": "Urban",
        "accent": "#ff5c7a",
        "context": "Fire in a residential building after infrastructure damage (wood and furniture fuel).",
        "aliases": ["residential_fire"],
    },
    "debris_dust": {
        "title": "Debris dust",
        "model_run": "demolition_release",
        "category": "Destruction",
        "accent": "#c08bff",
        "context": "Dust and fine particulate release after structural destruction.",
        "aliases": ["demolition_release"],
    },
}

SPECIES_LABEL = {
    "CO": "CO",
    "NO2": "NO2",
    "SO2": "SO2",
    "PM25": "PM2.5",
    "PM10": "PM10",
    "VOC": "VOC",
    "HCl": "HCl",
    "HCHO": "HCHO",
    "HCN": "HCN",
    "BENZENE": "Benzene",
}

_cache_meta = {}
_cache_fields = {}
_cache_max = 6


def _dir(sid):
    return DATA_ROOT / sid


def available_scenarios():
    out = []
    for sid in SCENARIO_META:
        meta_path = _dir(sid) / "export" / "metadata.json"
        if meta_path.exists():
            out.append(sid)
        else:
            for alias in SCENARIO_META[sid].get("aliases", []):
                if (_dir(alias) / "export" / "metadata.json").exists():
                    out.append(sid)
                    break
    return out


def _export_dir(sid):
    cand = _dir(sid) / "export"
    if (cand / "metadata.json").exists():
        return cand
    for alias in SCENARIO_META.get(sid, {}).get("aliases", []):
        alt = _dir(alias) / "export"
        if (alt / "metadata.json").exists():
            return alt
    return cand


def metadata(sid):
    if sid not in _cache_meta:
        path = _export_dir(sid) / "metadata.json"
        _cache_meta[sid] = json.loads(path.read_text(encoding="utf-8"))
    return _cache_meta[sid]


def _mtime(path):
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _read_csv(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _measurement_path(sid):
    for base in (DATA_ROOT / sid, _export_dir(sid).parent):
        p = base / "drone_measurements.csv"
        if p.exists():
            return p
    return DATA_ROOT / sid / "drone_measurements.csv"


def measurements(sid):
    rows = _read_csv(_measurement_path(sid))
    meta = metadata(sid)
    species = [s for s in meta["species"] if f"{s}_ug_m3" in (rows[0] if rows else {})]
    out = []
    for r in rows:
        vals = {}
        avail = {}
        for s in species:
            raw = r.get(f"{s}_ug_m3")
            ok = (r.get(f"{s}_available") or "").lower() == "true"
            if raw in (None, ""):
                vals[s] = None
                avail[s] = False
            else:
                vals[s] = float(raw)
                avail[s] = ok
        out.append(
            {
                "t": float(r["sim_time_s"]),
                "x": float(r["x_m"]),
                "y": float(r["y_m"]),
                "z": float(r["z_m"]),
                "available": (r.get("available") or "").lower() == "true",
                "reason": r.get("reason") or "",
                "values": vals,
                "species_available": avail,
            }
        )
    return {"rows": out, "species": species}


def timeseries(sid):
    rows = _read_csv(_export_dir(sid) / "timeseries.csv")
    if not rows:
        return {"times": [], "series": {}}
    species = [s for s in metadata(sid)["species"] if f"{s}_max_ug_m3" in rows[0]]
    times = [float(r["time_s"]) for r in rows]
    series = {}
    for s in species:
        series[s] = {
            "max": [float(r.get(f"{s}_max_ug_m3") or 0.0) for r in rows],
            "mean": [float(r.get(f"{s}_mean_ug_m3") or 0.0) for r in rows],
            "stored_kg": [float(r.get(f"{s}_stored_kg") or 0.0) for r in rows],
            "outlet_kg_s": [float(r.get(f"{s}_outlet_kg_s") or 0.0) for r in rows],
        }
    return {"times": times, "series": series, "species": species}


def _load_fields(sid, t):
    meta = metadata(sid)
    times = [float(x) for x in meta["times_s"]]
    idx = int(np.argmin(np.abs(np.asarray(times) - float(t))))
    key = (sid, idx)
    if key in _cache_fields:
        return _cache_fields[key], times[idx]
    path = _export_dir(sid) / f"fields_t{times[idx]:g}.npz"
    with np.load(path) as npz:
        data = {k: np.array(npz[k], copy=True) for k in npz.files}
    if len(_cache_fields) >= _cache_max:
        _cache_fields.pop(next(iter(_cache_fields)))
    _cache_fields[key] = data
    return data, times[idx]


def _downsample(a, max_cells=110):
    h, w = a.shape
    fy = max(1, math.ceil(h / max_cells))
    fx = max(1, math.ceil(w / max_cells))
    if fy == 1 and fx == 1:
        return a
    hh = (h // fy) * fy
    ww = (w // fx) * fx
    return a[:hh, :ww].reshape(hh // fy, fy, ww // fx, fx).max(axis=(1, 3))


_axes_cache = {}


def axes(sid):
    if sid in _axes_cache:
        return _axes_cache[sid]
    exp = _export_dir(sid)
    first = sorted(exp.glob("fields_t*.npz"))[0]
    with np.load(first) as npz:
        payload = {
            "x": [round(float(v), 3) for v in npz["x"]],
            "y": [round(float(v), 3) for v in npz["y"]],
            "z": [round(float(v), 3) for v in npz["z"]],
        }
    _axes_cache[sid] = payload
    return payload


def _stats(values):
    vals = values[np.isfinite(values)]
    vals = vals[vals > 0]
    if vals.size == 0:
        return {"min": 0.0, "max": 0.0, "mean": 0.0, "p50": 0.0, "p95": 0.0}
    return {
        "min": float(np.min(vals)),
        "max": float(np.max(vals)),
        "mean": float(np.mean(vals)),
        "p50": float(np.percentile(vals, 50)),
        "p95": float(np.percentile(vals, 95)),
    }


def slice_data(sid, species, t, axis="z", index=None):
    meta = metadata(sid)
    if species not in meta["species"]:
        species = next(iter(meta["species"]))
    data, t_exact = _load_fields(sid, t)
    arr = np.asarray(data[species], dtype=np.float64) * 1e9
    xs = np.asarray(data["x"], dtype=np.float64)
    ys = np.asarray(data["y"], dtype=np.float64)
    zs = np.asarray(data["z"], dtype=np.float64)
    nz, ny, nx = arr.shape

    if axis == "y":
        j = int(np.clip(int(index if index is not None else ny // 2), 0, ny - 1))
        plane = arr[:, j, :]
        horiz, vert, coord = xs, zs, float(ys[j])
    elif axis == "x":
        i = int(np.clip(int(index if index is not None else nx // 2), 0, nx - 1))
        plane = arr[:, :, i]
        horiz, vert, coord = ys, zs, float(xs[i])
    else:
        k = int(np.clip(int(index if index is not None else nz // 2), 0, nz - 1))
        plane = arr[k, :, :]
        horiz, vert, coord = xs, ys, float(zs[k])

    small = _downsample(plane)
    return {
        "scenario": sid,
        "species": species,
        "display": SPECIES_LABEL.get(species, species),
        "time": t_exact,
        "axis": axis,
        "index": int(index if index is not None else 0),
        "coord": coord,
        "unit": "ug/m3",
        "shape": [int(small.shape[0]), int(small.shape[1])],
        "values": np.round(small, 4).tolist(),
        "stats": _stats(plane),
        "horizontal": {
            "name": "x" if axis != "x" else "y",
            "values": [round(float(v), 2) for v in (horiz[:: max(1, len(horiz) // 12)])],
            "min": float(horiz.min()),
            "max": float(horiz.max()),
        },
        "vertical": {
            "name": "z" if axis != "z" else "y",
            "values": [round(float(v), 2) for v in (vert[:: max(1, len(vert) // 10)])],
            "min": float(vert.min()),
            "max": float(vert.max()),
        },
        "axes": {
            "x": [round(float(v), 2) for v in xs],
            "y": [round(float(v), 2) for v in ys],
            "z": [round(float(v), 2) for v in zs],
        },
    }


def scenario_summary(sid):
    meta = metadata(sid)
    extra = SCENARIO_META.get(sid, {})
    exp = _export_dir(sid)
    fields = sorted(exp.glob("fields_t*.npz"))
    meas = measurements(sid)
    final = meta["summary"][-1] if meta.get("summary") else {}
    maxima = {}
    for s in meta["species"]:
        item = final.get(s, {})
        maxima[s] = {
            "display": SPECIES_LABEL.get(s, s),
            "ug_m3": float(item.get("max_kg_m3", 0.0)) * 1e9,
            "location_m": item.get("max_location_m"),
            "stored_kg": float(item.get("stored_kg", 0.0)),
            "provenance": meta["species"][s].get("provenance", ""),
            "phase": meta["species"][s].get("phase", ""),
            "rate_kg_s": meta["species"][s].get("rate_kg_s"),
        }
    times = [float(x) for x in meta["times_s"]]
    update = max(
        [_mtime(exp / "metadata.json"), _mtime(exp / "timeseries.csv"), _mtime(_measurement_path(sid))]
        + [_mtime(p) for p in fields[:1]]
    )
    return {
        "id": sid,
        "title": extra.get("title", sid),
        "model_run": extra.get("model_run", meta.get("scenario", sid)),
        "category": extra.get("category", ""),
        "accent": extra.get("accent", "#38e0c8"),
        "context": extra.get("context", meta.get("description", "")),
        "description": meta.get("description", ""),
        "kind": meta.get("kind", ""),
        "solver": meta.get("solver", ""),
        "openfoam_version": meta.get("openfoam_version", ""),
        "domain": meta.get("domain_m", {}),
        "grid_shape": meta.get("grid_shape_nz_ny_nx", []),
        "mesh_cells": meta.get("mesh_cells"),
        "wind": meta.get("wind", {}),
        "source_box": meta.get("source_box_m"),
        "duration_s": times[-1] if times else 0.0,
        "times": times,
        "frame_count": len(times),
        "species": [
            {
                "id": s,
                "label": SPECIES_LABEL.get(s, s),
                "phase": meta["species"][s].get("phase", ""),
                "provenance": meta["species"][s].get("provenance", ""),
                "rate_kg_s": meta["species"][s].get("rate_kg_s"),
            }
            for s in meta["species"]
        ],
        "maxima": maxima,
        "checks": meta.get("checks", {}),
        "limitations": meta.get("limitations", []),
        "parameter_warning": meta.get("parameter_warning", ""),
        "measurements": len(meas["rows"]),
        "fields_present": len(fields) == len(times) and len(fields) > 0,
        "last_update": update,
        "status": "computed" if len(fields) == len(times) and fields else "partial",
        "files": {
            "metadata": str(exp / "metadata.json"),
            "export_dir": str(exp),
        },
    }


def isaac_status():
    if not ISAAC_STATUS.exists():
        return {"connected": False, "state": "Not connected", "last_seen": None}
    try:
        payload = json.loads(ISAAC_STATUS.read_text(encoding="utf-8"))
        age = time.time() - float(payload.get("wall_time", 0.0))
        fresh = age < 15.0
        return {
            "connected": fresh,
            "state": "Connected" if fresh else "Not connected",
            "age_s": round(age, 1),
            "last_seen": payload.get("wall_time"),
            "t": payload.get("sim_time"),
            "fps": payload.get("fps"),
            "scenario": payload.get("scenario"),
            "paused": payload.get("paused"),
        }
    except Exception:
        return {"connected": False, "state": "Not connected", "last_seen": None}


def overview():
    ids = available_scenarios()
    cards = []
    all_meas = 0
    last = 0.0
    for sid in ids:
        s = scenario_summary(sid)
        cards.append(s)
        all_meas += s["measurements"]
        last = max(last, s["last_update"])
    missing = [sid for sid in SCENARIO_META if sid not in ids]
    return {
        "product": "GreenAirDrone",
        "scenario_count": len(ids),
        "computed_count": sum(1 for c in cards if c["status"] == "computed"),
        "measurement_count": all_meas,
        "last_update": last,
        "scenarios": cards,
        "missing_scenarios": missing,
        "isaac": isaac_status(),
        "generated_at": time.time(),
    }

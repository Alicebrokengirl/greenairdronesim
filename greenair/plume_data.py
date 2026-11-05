"""Offline reader and visual sampling for the OpenFOAM concentration export.

The module has no Isaac/omni imports, so the interpolation and particle
sampling can be tested without starting Kit.  Values are model output
(passive scalars), not physical measurements.
"""
from __future__ import annotations

import bisect
import csv
import json
from pathlib import Path

import numpy as np

NOISE_FLOOR = 1e-12

_COLOR_STOPS = np.array(
    [
        [0.60, 0.66, 0.74],
        [0.22, 0.58, 0.92],
        [0.05, 0.82, 0.85],
        [0.45, 0.92, 0.50],
        [1.00, 0.88, 0.18],
        [1.00, 0.48, 0.04],
    ],
    dtype=np.float64,
)


def srgb_to_linear(rgb):
    rgb = np.asarray(rgb, dtype=np.float64)
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(rgb):
    rgb = np.asarray(rgb, dtype=np.float64)
    return np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * rgb ** (1 / 2.4) - 0.055)


def color_for_norm(norm):
    """Map 0..1 to a linear-RGB smoke/heat colour."""
    norm = np.clip(np.asarray(norm, dtype=np.float64), 0.0, 1.0)
    stops = _COLOR_STOPS
    x = norm * (len(stops) - 1)
    i = np.clip(np.floor(x).astype(int), 0, len(stops) - 2)
    f = (x - i)[..., None]
    rgb = stops[i] * (1.0 - f) + stops[i + 1] * f
    return srgb_to_linear(rgb)


class PlumeData:
    def __init__(self, export_dir):
        self.export_dir = Path(export_dir)
        meta_path = self.export_dir / "metadata.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"metadata.json not found: {meta_path}")
        self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.species = list(self.meta["species"].keys())
        self.times = np.asarray(self.meta["times_s"], dtype=np.float64)
        self.domain = self.meta["domain_m"]
        self.source_box = self.meta.get("source_box_m")
        self._snapshots = {}
        self._timeseries = self._read_timeseries()

        first = self._snapshot(self.times[0])
        self.x = np.asarray(first["x"], dtype=np.float64)
        self.y = np.asarray(first["y"], dtype=np.float64)
        self.z = np.asarray(first["z"], dtype=np.float64)
        self.shape = (self.z.size, self.y.size, self.x.size)
        self.dx = np.gradient(self.x)
        self.dy = np.gradient(self.y)
        self.dz = np.gradient(self.z)

        self._max_ug = {}
        last = self._snapshot(self.times[-1])
        for s in self.species:
            if s in last:
                self._max_ug[s] = float(np.max(last[s])) * 1e9
        self._particles = None

    # ------------------------------------------------------------------ data
    def _snapshot(self, t):
        t = float(t)
        close = self.times[np.argmin(np.abs(self.times - t))]
        key = f"{close:g}"
        if key not in self._snapshots:
            path = self.export_dir / f"fields_t{key}.npz"
            if not path.exists():
                raise FileNotFoundError(path)
            with np.load(path) as npz:
                self._snapshots[key] = {k: np.array(npz[k], copy=True) for k in npz.files}
        return self._snapshots[key]

    def _read_timeseries(self):
        path = self.export_dir / "timeseries.csv"
        rows = {}
        if not path.exists():
            return rows
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = float(row["time_s"])
                rows[t] = row
        return rows

    def time_bracket(self, t):
        t = float(t)
        t0, t1 = float(self.times[0]), float(self.times[-1])
        if t < t0 - 1e-9 or t > t1 + 1e-9:
            return None
        if t <= t0:
            return t0, t0, 0.0
        if t >= t1:
            return t1, t1, 0.0
        j = bisect.bisect_right(self.times, t) - 1
        a, b = float(self.times[j]), float(self.times[j + 1])
        return a, b, (t - a) / (b - a)

    def _axis(self, axis, values):
        lo, hi = axis[0], axis[-1]
        d_lo = axis[1] - axis[0]
        d_hi = axis[-1] - axis[-2]
        valid = (values >= lo - 0.5 * d_lo) & (values <= hi + 0.5 * d_hi)
        i = np.clip(np.searchsorted(axis, values) - 1, 0, axis.size - 2)
        w = (values - axis[i]) / (axis[i + 1] - axis[i])
        return i, i + 1, np.clip(w, 0.0, 1.0), valid

    def _field_values(self, points, t, species):
        points = np.asarray(points, dtype=np.float64)
        values = {s: np.zeros(points.shape[0], dtype=np.float64) for s in species}
        bracket = self.time_bracket(t)
        if bracket is None:
            return values, np.zeros(points.shape[0], dtype=bool)
        ta, tb, wt = bracket
        sa = self._snapshot(ta)
        sb = sa if ta == tb else self._snapshot(tb)

        i0, i1, wx, vx = self._axis(self.x, points[:, 0])
        j0, j1, wy, vy = self._axis(self.y, points[:, 1])
        k0, k1, wz, vz = self._axis(self.z, points[:, 2])
        valid = vx & vy & vz

        for s in species:
            if s not in sa:
                continue
            a = np.asarray(sa[s], dtype=np.float64)
            va = self._trilinear(a, i0, i1, j0, j1, k0, k1, wx, wy, wz)
            if ta != tb and s in sb:
                b = np.asarray(sb[s], dtype=np.float64)
                vb = self._trilinear(b, i0, i1, j0, j1, k0, k1, wx, wy, wz)
                va = va * (1.0 - wt) + vb * wt
            va = np.where(valid, va, 0.0)
            va = np.where(va < 0.0, 0.0, va)
            values[s] = va
        return values, valid

    @staticmethod
    def _trilinear(a, i0, i1, j0, j1, k0, k1, wx, wy, wz):
        c000 = a[k0, j0, i0]
        c001 = a[k0, j0, i1]
        c010 = a[k0, j1, i0]
        c011 = a[k0, j1, i1]
        c100 = a[k1, j0, i0]
        c101 = a[k1, j0, i1]
        c110 = a[k1, j1, i0]
        c111 = a[k1, j1, i1]
        c00 = c000 * (1 - wx) + c001 * wx
        c01 = c010 * (1 - wx) + c011 * wx
        c10 = c100 * (1 - wx) + c101 * wx
        c11 = c110 * (1 - wx) + c111 * wx
        c0 = c00 * (1 - wy) + c01 * wy
        c1 = c10 * (1 - wy) + c11 * wy
        return c0 * (1 - wz) + c1 * wz

    def sample(self, points, t, species=None):
        """Return (dict species -> kg/m3, valid mask). Outside domain = 0."""
        species = self.species if species is None else list(species)
        return self._field_values(points, t, [s for s in species if s in self.species])

    # ------------------------------------------------------------- statistics
    def max_ug(self, species):
        return self._max_ug.get(species, 0.0)

    def timeseries_value(self, species, field, t):
        """Interpolate a column such as CO_max_ug_m3 from timeseries.csv."""
        if not self._timeseries:
            return None
        key = f"{species}_{field}"
        times = sorted(self._timeseries)
        vals = []
        for tt in times:
            raw = self._timeseries[tt].get(key)
            vals.append(float(raw) if raw not in (None, "") else np.nan)
        vals = np.asarray(vals, dtype=np.float64)
        ok = np.isfinite(vals)
        if not ok.any():
            return None
        return float(np.interp(float(t), np.asarray(times)[ok], vals[ok]))

    # --------------------------------------------------------------- particles
    def generate_particles(
        self,
        count=18000,
        t=30.0,
        threshold_fraction=0.002,
        gamma=0.45,
        jitter_fraction=0.44,
        seed=7,
        weight_species=("CO", "PM25", "SO2"),
    ):
        """Deterministic importance sampling of the visible plume envelope.

        Positions are fixed; colours/opacities are recomputed from the field
        each frame.  This is a visualisation of the Eulerian field, not a
        particle-transport model.
        """
        snap = self._snapshot(t)
        w = np.zeros(self.shape, dtype=np.float64)
        for s in weight_species:
            if s not in snap:
                continue
            m = float(np.max(snap[s]))
            if m > 0:
                w += np.asarray(snap[s], dtype=np.float64) / m
        if w.max() <= 0:
            raise ValueError("particle sampling field is empty")
        w /= w.max()
        idx = np.flatnonzero(w.ravel() > threshold_fraction)
        if idx.size == 0:
            raise ValueError("no cells above the plume threshold")
        p = np.power(w.ravel()[idx], gamma)
        p /= p.sum()
        rng = np.random.default_rng(seed)
        picked = rng.choice(idx, size=int(count), replace=True, p=p)
        k, j, i = np.unravel_index(picked, self.shape)
        ux = rng.random(count) - 0.5
        uy = rng.random(count) - 0.5
        uz = rng.random(count) - 0.5
        x = self.x[i] + ux * self.dx[i] * 2.0 * jitter_fraction
        y = self.y[j] + uy * self.dy[j] * 2.0 * jitter_fraction
        z = self.z[k] + uz * self.dz[k] * 2.0 * jitter_fraction
        z = np.clip(z, 0.15, None)
        self._particles = np.column_stack([x, y, z]).astype(np.float64)
        return self._particles

    def particle_colors(self, positions, t, species, vmin_ug=10.0, min_scale=0.18, max_scale=0.85):
        values, valid = self.sample(positions, t, [species])
        c = values.get(species, np.zeros(len(positions))) * 1e9
        vmax = max(self.max_ug(species), vmin_ug * 10.0)
        lo, hi = np.log10(vmin_ug), np.log10(vmax)
        norm = np.clip((np.log10(np.maximum(c, vmin_ug)) - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
        rgb = color_for_norm(norm)
        scale = min_scale + (max_scale - min_scale) * norm ** 1.5
        hide = (~valid) | (c <= vmin_ug * 0.999)
        scale = np.where(hide, 0.0, scale)
        return rgb.astype(np.float32), scale.astype(np.float32), c, hide

    # ------------------------------------------------------------------ legend
    def legend_norm(self, species, count=24):
        vmin = 10.0
        vmax = max(self.max_ug(species), vmin * 10.0)
        vals = np.logspace(np.log10(vmin), np.log10(vmax), count)
        return vals, color_for_norm(np.linspace(0.0, 1.0, count))

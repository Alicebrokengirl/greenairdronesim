"""Drone trajectory from the measured demo flight (CSV) or a fallback path."""
from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np


class DroneTrajectory:
    def __init__(self, csv_path=None, loop=True):
        self.loop = bool(loop)
        self.t = np.array([0.0, 60.0])
        self.p = np.array([[10.0, 0.0, 5.0], [88.0, 0.0, 8.0]])
        if csv_path and Path(csv_path).exists():
            self._load(Path(csv_path))
        self.duration = float(self.t[-1] - self.t[0])

    def _load(self, path):
        ts, xs, ys, zs = [], [], [], []
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ts.append(float(row["sim_time_s"]))
                xs.append(float(row["x_m"]))
                ys.append(float(row["y_m"]))
                zs.append(float(row["z_m"]))
        order = np.argsort(ts)
        self.t = np.asarray(ts, dtype=np.float64)[order]
        self.p = np.column_stack(
            [np.asarray(xs)[order], np.asarray(ys)[order], np.asarray(zs)[order]]
        ).astype(np.float64)

    def wrap_time(self, t):
        t = float(t)
        if t <= self.t[-1]:
            return max(t, self.t[0])
        if not self.loop:
            return self.t[-1]
        span = self.t[-1] - self.t[0]
        return self.t[0] + math.fmod(t - self.t[0], span)

    def position(self, t):
        t = self.wrap_time(t)
        return np.array(
            [np.interp(t, self.t, self.p[:, i]) for i in range(3)], dtype=np.float64
        )

    def velocity(self, t, dt=0.25):
        a = self.position(t - dt)
        b = self.position(t + dt)
        return (b - a) / (2.0 * dt)

    def yaw_deg(self, t):
        v = self.velocity(t)
        if abs(v[0]) + abs(v[1]) < 1e-6:
            return 0.0
        return math.degrees(math.atan2(float(v[1]), float(v[0])))

    def speed(self, t):
        return float(np.linalg.norm(self.velocity(t)))

    def at(self, t):
        pos = self.position(t)
        yaw = self.yaw_deg(t)
        speed = self.speed(t)
        return pos, yaw, speed

    def sample_series(self, step=0.5):
        n = int(round(self.duration / step)) + 1
        ts = np.linspace(self.t[0], self.t[-1], n)
        return ts, np.column_stack([self.position(t) for t in ts])

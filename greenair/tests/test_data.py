import os
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
DATA = Path(os.environ.get("GREENAIR_DATA") or (REPO_ROOT / "data")).expanduser()
if not DATA.is_absolute():
    DATA = REPO_ROOT / DATA
DATA = DATA.resolve()
sys.path.insert(0, str(ROOT))

from plume_data import PlumeData
from trajectory import DroneTrajectory


class PlumeDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = PlumeData(DATA / "industrial_fire" / "export")

    def test_snapshot_at_grid_center(self):
        p = np.array([[self.data.x[10], self.data.y[20], self.data.z[5]]])
        vals, valid = self.data.sample(p, 30.0, ["CO"])
        snap = self.data._snapshot(30.0)
        self.assertTrue(valid[0])
        self.assertAlmostEqual(vals["CO"][0], float(snap["CO"][5, 20, 10]), places=12)

    def test_time_interpolation(self):
        p = np.array([[self.data.x[10], self.data.y[20], self.data.z[5]]])
        a = self.data._snapshot(0.0)["CO"][5, 20, 10]
        b = self.data._snapshot(5.0)["CO"][5, 20, 10]
        vals, valid = self.data.sample(p, 2.5, ["CO"])
        self.assertTrue(valid[0])
        self.assertAlmostEqual(vals["CO"][0], 0.5 * (float(a) + float(b)), places=12)

    def test_outside_domain_is_unavailable_and_zero(self):
        p = np.array([[-10.0, 0.0, 5.0], [50.0, 0.0, 60.0]])
        vals, valid = self.data.sample(p, 30.0, ["CO"])
        self.assertFalse(valid.any())
        self.assertTrue(np.all(vals["CO"] == 0.0))

    def test_particles_and_colors(self):
        pts = self.data.generate_particles(count=2500, t=30.0)
        self.assertEqual(pts.shape, (2500, 3))
        self.assertTrue(np.all(pts[:, 2] >= 0.15))
        rgb, scale, conc, hide = self.data.particle_colors(pts, 30.0, "CO")
        self.assertEqual(rgb.shape, (2500, 3))
        self.assertTrue(np.all(scale >= 0.0))
        self.assertTrue(np.all(scale <= 0.86))

    def test_time_outside_window(self):
        p = np.array([[50.0, 0.0, 8.0]])
        vals, valid = self.data.sample(p, 500.0, ["CO"])
        self.assertFalse(valid[0])
        self.assertEqual(vals["CO"][0], 0.0)

    def test_timeseries(self):
        self.assertIsNotNone(self.data.timeseries_value("CO", "max_ug_m3", 30.0))
        self.assertGreater(self.data.max_ug("CO"), 1000.0)


class TrajectoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.traj = DroneTrajectory(DATA / "industrial_fire" / "drone_measurements.csv")

    def test_endpoints(self):
        p0 = self.traj.position(0.0)
        p1 = self.traj.position(60.0)
        self.assertAlmostEqual(p0[0], 10.0)
        self.assertAlmostEqual(p1[0], 88.0)

    def test_loop_and_yaw(self):
        p = self.traj.position(65.0)
        self.assertAlmostEqual(p[0], self.traj.position(5.0)[0], places=6)
        self.assertTrue(np.isfinite(self.traj.yaw_deg(12.0)))


if __name__ == "__main__":
    unittest.main()

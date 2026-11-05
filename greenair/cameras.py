"""Camera director for the industrial visualisation."""
from __future__ import annotations

import math

import numpy as np
from pxr import Gf, UsdGeom

FOCAL_MM = 24.0
H_APERTURE = 20.955
V_APERTURE = 11.787


def look_at_matrix(eye, target, up=(0, 0, 1)):
    eye = np.asarray(eye, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    up = np.asarray(up, dtype=np.float64)
    f = target - eye
    n = np.linalg.norm(f)
    if n < 1e-9:
        f = np.array([1.0, 0, 0])
    else:
        f = f / n
    r = np.cross(f, up)
    n = np.linalg.norm(r)
    if n < 1e-9:
        r = np.array([1.0, 0, 0])
    else:
        r = r / n
    u = np.cross(r, f)
    m = Gf.Matrix4d(
        r[0], u[0], -f[0], 0,
        r[1], u[1], -f[1], 0,
        r[2], u[2], -f[2], 0,
        eye[0], eye[1], eye[2], 1,
    )
    return m


class CameraRig:
    modes = ("chase", "orbit", "ground", "top")

    def __init__(self, stage, path="/World/Cameras/Main"):
        self.stage = stage
        self.path = path
        self.cam = UsdGeom.Camera.Define(stage, path)
        self.cam.CreateFocalLengthAttr(FOCAL_MM)
        self.cam.CreateHorizontalApertureAttr(H_APERTURE)
        self.cam.CreateVerticalApertureAttr(V_APERTURE)
        self.cam.CreateClippingRangeAttr(Gf.Vec2f(0.1, 3000.0))
        self.xform = UsdGeom.Xformable(self.cam.GetPrim())
        self.xform.AddTransformOp()
        self.mode = "chase"
        self.eye = None
        self.target = None
        self.initialized = False

    def hfov_deg(self):
        return 2.0 * math.degrees(math.atan(H_APERTURE * 0.5 / FOCAL_MM))

    def vfov_deg(self):
        return 2.0 * math.degrees(math.atan(V_APERTURE * 0.5 / FOCAL_MM))

    def set_mode(self, mode):
        if mode in self.modes:
            self.mode = mode

    def cycle(self):
        i = self.modes.index(self.mode)
        self.mode = self.modes[(i + 1) % len(self.modes)]

    def _desired(self, t, drone_pos, yaw_deg):
        p = np.asarray(drone_pos, dtype=np.float64)
        yaw = math.radians(float(yaw_deg))
        fwd = np.array([math.cos(yaw), math.sin(yaw), 0.0])
        right = np.array([-math.sin(yaw), math.cos(yaw), 0.0])
        if self.mode == "chase":
            # wide elevated tracking camera, well outside the smoke envelope
            eye = p + np.array([-42.0, -52.0, 28.0])
            target = p + np.array([10.0, 0.0, 4.0])
            return eye, target
        if self.mode == "orbit":
            ang = math.radians(-115.0 + t * 2.4)
            c = np.array([55.0, 0.0, 9.0])
            eye = c + np.array([math.cos(ang) * 70.0, math.sin(ang) * 70.0, 25.0])
            target = np.array([52.0, 0.0, 8.0])
            return eye, target
        if self.mode == "ground":
            eye = np.array([4.0, -36.0, 3.6])
            target = np.array([42.0, 0.0, 9.0])
            sway = 0.12 * math.sin(t * 0.7)
            return eye + np.array([sway, 0, 0.05 * math.sin(t * 1.3)]), target
        if self.mode == "top":
            eye = np.array([54.0, -8.0, 92.0])
            target = np.array([52.0, 0.0, 6.0])
            return eye, target
        return np.array([110.0, -78.0, 40.0]), np.array([50.0, 0.0, 8.0])

    def update(self, t, drone_pos, yaw_deg, dt=1 / 60, snap=False):
        eye, target = self._desired(t, drone_pos, yaw_deg)
        if self.eye is None or snap or not self.initialized:
            self.eye = eye
            self.target = target
            self.initialized = True
        else:
            alpha = 1.0 - math.exp(-max(dt, 1e-3) * 2.6)
            self.eye = self.eye * (1 - alpha) + eye * alpha
            self.target = self.target * (1 - alpha) + target * alpha
        self.xform.GetTransformOp().Set(look_at_matrix(self.eye, self.target))
        return self.eye, self.target

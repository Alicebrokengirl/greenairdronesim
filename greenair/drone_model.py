"""A compact procedural quadcopter for the visualisation scene."""
from __future__ import annotations

import math

from pxr import Gf, Sdf, UsdGeom, UsdShade


class DroneModel:
    def __init__(self, stage, path="/World/Drone", scale=1.0):
        self.stage = stage
        self.path = path
        self.scale = float(scale)
        self.spin = 0.0
        self.last_yaw = None
        self.root = UsdGeom.Xform.Define(stage, path).GetPrim()
        self._build()
        self._x = UsdGeom.Xformable(self.root)
        self._x.AddTranslateOp()
        self._x.AddRotateXYZOp()

    def _mat(self, name, color, rough=0.5, metal=0.4, emissive=None):
        path = f"/World/DroneLooks/{name}"
        mat = UsdShade.Material.Define(self.stage, path)
        sh = UsdShade.Shader.Define(self.stage, path + "/Shader")
        sh.CreateIdAttr("UsdPreviewSurface")
        sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
        sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(rough)
        sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metal)
        if emissive:
            sh.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*emissive))
        mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
        return mat

    def _cube(self, name, size, pos, mat, rot=None):
        c = UsdGeom.Cube.Define(self.stage, f"{self.path}/{name}")
        c.CreateSizeAttr(1.0)
        x = UsdGeom.Xformable(c.GetPrim())
        x.AddTranslateOp().Set(Gf.Vec3d(*pos))
        x.AddScaleOp().Set(Gf.Vec3f(*size))
        if rot:
            x.AddRotateXYZOp().Set(Gf.Vec3f(*rot))
        UsdShade.MaterialBindingAPI.Apply(c.GetPrim()).Bind(mat)
        return c

    def _cyl(self, name, radius, height, pos, mat, rot=None, axis="Z"):
        c = UsdGeom.Cylinder.Define(self.stage, f"{self.path}/{name}")
        c.CreateRadiusAttr(float(radius))
        c.CreateHeightAttr(float(height))
        c.CreateAxisAttr(axis)
        x = UsdGeom.Xformable(c.GetPrim())
        x.AddTranslateOp().Set(Gf.Vec3d(*pos))
        if rot:
            x.AddRotateXYZOp().Set(Gf.Vec3f(*rot))
        UsdShade.MaterialBindingAPI.Apply(c.GetPrim()).Bind(mat)
        return c

    def _sphere(self, name, radius, pos, mat):
        s = UsdGeom.Sphere.Define(self.stage, f"{self.path}/{name}")
        s.CreateRadiusAttr(float(radius))
        UsdGeom.Xformable(s.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(*pos))
        UsdShade.MaterialBindingAPI.Apply(s.GetPrim()).Bind(mat)
        return s

    def _build(self):
        carbon = self._mat("Carbon", (0.035, 0.04, 0.045), 0.35, 0.55)
        body_blue = self._mat("BodyBlue", (0.03, 0.20, 0.36), 0.28, 0.65)
        silver = self._mat("Silver", (0.52, 0.55, 0.58), 0.25, 0.9)
        black = self._mat("Black", (0.01, 0.012, 0.014), 0.5, 0.3)
        led_r = self._mat("LedRed", (1.0, 0.05, 0.02), 0.3, 0.0, (1.0, 0.03, 0.01))
        led_g = self._mat("LedGreen", (0.05, 1.0, 0.12), 0.3, 0.0, (0.02, 1.0, 0.08))
        lens = self._mat("Lens", (0.01, 0.015, 0.02), 0.08, 0.2, (0.02, 0.06, 0.10))

        self._cube("Body", (1.15, 0.72, 0.26), (0, 0, 0), body_blue)
        self._cube("BodyTop", (0.82, 0.52, 0.16), (-0.05, 0, 0.17), carbon)
        self._cube("Belly", (0.64, 0.44, 0.10), (0, 0, -0.17), carbon)
        self._cube("Nose", (0.32, 0.44, 0.16), (0.58, 0, -0.02), carbon)

        rotor_pos = [(0.76, 0.62), (0.76, -0.62), (-0.76, 0.62), (-0.76, -0.62)]
        self.rotors = []
        self.leds = []
        for i, (x, y) in enumerate(rotor_pos):
            ang = math.degrees(math.atan2(y, x))
            self._cube(f"Arm{i}", (0.98, 0.105, 0.075), (x * 0.48, y * 0.48, -0.03), carbon, rot=(0, 0, ang))
            self._cyl(f"Motor{i}", 0.135, 0.20, (x, y, 0.02), silver)
            self._cyl(f"RotorHub{i}", 0.055, 0.07, (x, y, 0.14), black)
            # rotor group: two blades spin around Z
            group = UsdGeom.Xform.Define(self.stage, f"{self.path}/Rotor{i}").GetPrim()
            gx = UsdGeom.Xformable(group)
            gx.AddTranslateOp().Set(Gf.Vec3d(x, y, 0.16))
            self._cube(f"Rotor{i}/BladeA", (0.76, 0.085, 0.018), (0, 0, 0), black)
            self._cube(f"Rotor{i}/BladeB", (0.085, 0.76, 0.018), (0, 0, 0), black)
            self.rotors.append((group, ang))
            if y > 0:
                self._sphere(f"Led{i}", 0.055, (x * 0.55, y * 0.55, 0.10), led_r)
            else:
                self._sphere(f"Led{i}", 0.055, (x * 0.55, y * 0.55, 0.10), led_g)

        # skids
        for i, y in enumerate((-0.32, 0.32)):
            self._cube(f"Skid{i}", (0.10, 1.12, 0.055), (0, y, -0.40), carbon)
            self._cube(f"SkidLeg{i}", (0.09, 0.09, 0.30), (0.24, y * 0.8, -0.29), carbon)
            self._cube(f"SkidLegB{i}", (0.09, 0.09, 0.30), (-0.24, y * 0.8, -0.29), carbon)
        # gimbal
        self._sphere("Gimbal", 0.13, (0.50, 0, -0.24), carbon)
        self._cyl("GimbalLens", 0.075, 0.16, (0.64, 0, -0.24), lens, rot=(0, 90, 0))
        self._cube("Antenna", (0.02, 0.02, 0.34), (-0.42, 0.12, 0.30), silver, rot=(12, 0, 0))
        self._sphere("NavTop", 0.035, (-0.12, 0, 0.29), led_g)

        if self.scale != 1.0:
            self._xform_scale = UsdGeom.Xformable(self.root).AddScaleOp().Set(Gf.Vec3f(self.scale))

    def update(self, position, yaw_deg, speed=0.0, dt=1 / 60, yaw_rate=0.0):
        self._x.GetTranslateOp().Set(Gf.Vec3d(float(position[0]), float(position[1]), float(position[2])))
        pitch = max(-7.0, min(7.0, -speed * 2.2))
        roll = max(-8.0, min(8.0, yaw_rate * 0.35))
        self._x.GetRotateXYZOp().Set(Gf.Vec3f(pitch, roll, float(yaw_deg)))
        self.spin += (dt * 2400.0) % 360.0
        for group, offset in self.rotors:
            gx = UsdGeom.Xformable(group)
            op = gx.GetRotateZOp()
            if not op:
                op = gx.AddRotateZOp()
            op.Set((self.spin + offset) % 360.0)

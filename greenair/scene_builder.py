"""Procedural industrial site for the GreenAirDrone Isaac Sim scene."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from pxr import Gf, Sdf, UsdGeom, UsdLux, UsdShade


class SceneBuilder:
    def __init__(self, stage, asset_dir):
        self.stage = stage
        self.asset_dir = Path(asset_dir)
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        self.mats = {}
        self.dynamic = {"flames": [], "beacons": [], "fire_light": None, "vents": []}

    # ------------------------------------------------------------- primitives
    def material(
        self,
        name,
        color,
        roughness=0.65,
        metallic=0.0,
        opacity=1.0,
        emissive=None,
        clearcoat=0.0,
    ):
        if name in self.mats:
            return self.mats[name]
        path = f"/World/Looks/{name}"
        mat = UsdShade.Material.Define(self.stage, path)
        sh = UsdShade.Shader.Define(self.stage, path + "/Shader")
        sh.CreateIdAttr("UsdPreviewSurface")
        sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
        sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(float(roughness))
        sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(float(metallic))
        sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(float(opacity))
        sh.CreateInput("clearcoat", Sdf.ValueTypeNames.Float).Set(float(clearcoat))
        if emissive is not None:
            sh.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*emissive))
        mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
        self.mats[name] = mat
        return mat

    def cube(self, path, size, pos, mat, rot=None, parent=None):
        prim_path = path if parent is None else f"{parent}/{path.lstrip('/')}"
        c = UsdGeom.Cube.Define(self.stage, prim_path)
        c.CreateSizeAttr(1.0)
        x = UsdGeom.Xformable(c.GetPrim())
        x.AddTranslateOp().Set(Gf.Vec3d(*pos))
        x.AddScaleOp().Set(Gf.Vec3f(*size))
        if rot:
            x.AddRotateXYZOp().Set(Gf.Vec3f(*rot))
        UsdShade.MaterialBindingAPI.Apply(c.GetPrim()).Bind(mat)
        return c

    def cylinder(self, path, radius, height, pos, mat, axis="Z", segments=32):
        c = UsdGeom.Cylinder.Define(self.stage, path)
        c.CreateRadiusAttr(float(radius))
        c.CreateHeightAttr(float(height))
        c.CreateAxisAttr(axis)
        c.CreateExtentAttr([Gf.Vec3f(-radius, -radius, -height / 2), Gf.Vec3f(radius, radius, height / 2)])
        x = UsdGeom.Xformable(c.GetPrim())
        x.AddTranslateOp().Set(Gf.Vec3d(*pos))
        UsdShade.MaterialBindingAPI.Apply(c.GetPrim()).Bind(mat)
        return c

    def sphere(self, path, radius, pos, mat, scale=(1, 1, 1)):
        s = UsdGeom.Sphere.Define(self.stage, path)
        s.CreateRadiusAttr(float(radius))
        x = UsdGeom.Xformable(s.GetPrim())
        x.AddTranslateOp().Set(Gf.Vec3d(*pos))
        x.AddScaleOp().Set(Gf.Vec3f(*scale))
        UsdShade.MaterialBindingAPI.Apply(s.GetPrim()).Bind(mat)
        return s

    def cone(self, path, radius, height, pos, mat, rot=None):
        c = UsdGeom.Cone.Define(self.stage, path)
        c.CreateRadiusAttr(float(radius))
        c.CreateHeightAttr(float(height))
        x = UsdGeom.Xformable(c.GetPrim())
        x.AddTranslateOp().Set(Gf.Vec3d(*pos))
        x.AddScaleOp().Set(Gf.Vec3f(1, 1, 1))
        if rot:
            x.AddRotateXYZOp().Set(Gf.Vec3f(*rot))
        UsdShade.MaterialBindingAPI.Apply(c.GetPrim()).Bind(mat)
        return c

    # ------------------------------------------------------------------- build
    def build(self):
        stage = self.stage
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        world = UsdGeom.Xform.Define(stage, "/World").GetPrim()

        concrete = self.material("Concrete", (0.32, 0.33, 0.32), roughness=0.92)
        asphalt = self.material("Asphalt", (0.055, 0.06, 0.062), roughness=0.88)
        grass = self.material("Grass", (0.10, 0.14, 0.085), roughness=0.98)
        steel = self.material("Steel", (0.38, 0.41, 0.44), roughness=0.32, metallic=0.85)
        dark_steel = self.material("DarkSteel", (0.10, 0.115, 0.125), roughness=0.42, metallic=0.72)
        rust = self.material("Rust", (0.34, 0.17, 0.08), roughness=0.92, metallic=0.2)
        wall = self.material("Wall", (0.52, 0.54, 0.52), roughness=0.82)
        wall_blue = self.material("WallBlue", (0.14, 0.25, 0.33), roughness=0.7, metallic=0.25)
        roof = self.material("Roof", (0.15, 0.17, 0.18), roughness=0.7, metallic=0.3)
        white = self.material("White", (0.76, 0.77, 0.74), roughness=0.7)
        red = self.material("Red", (0.55, 0.075, 0.055), roughness=0.62)
        orange = self.material("Orange", (0.72, 0.24, 0.045), roughness=0.62)
        blue = self.material("Blue", (0.045, 0.20, 0.42), roughness=0.55)
        yellow = self.material("Yellow", (0.78, 0.58, 0.05), roughness=0.55)
        glass = self.material(
            "GlassLit", (0.02, 0.03, 0.04), roughness=0.15, metallic=0.1,
            emissive=(0.35, 0.52, 0.65),
        )
        lamp = self.material(
            "Lamp", (1.0, 0.92, 0.72), roughness=0.2, emissive=(1.0, 0.78, 0.42)
        )
        flame_mat = self.material(
            "Flame", (1.0, 0.22, 0.02), roughness=0.4, opacity=0.88,
            emissive=(1.0, 0.20, 0.02),
        )
        flame_core = self.material(
            "FlameCore", (1.0, 0.78, 0.15), roughness=0.4, opacity=0.92,
            emissive=(1.0, 0.62, 0.10),
        )
        scorch = self.material("Scorch", (0.025, 0.022, 0.02), roughness=0.98)
        tree_mat = self.material("Foliage", (0.055, 0.105, 0.055), roughness=1.0)
        trunk = self.material("Trunk", (0.16, 0.10, 0.06), roughness=1.0)

        # ---------------------------------------------------------- terrain
        self.cube("/World/Terrain", (420, 300, 0.3), (55, 0, -0.23), grass)
        self.cube("/World/SitePad", (96, 52, 0.10), (50, 0, 0.02), concrete)
        # service roads
        self.cube("/World/RoadSouth", (190, 8, 0.06), (50, -13, 0.09), asphalt)
        self.cube("/World/RoadNorth", (190, 7, 0.06), (50, 15, 0.09), asphalt)
        self.cube("/World/RoadCross", (9, 56, 0.06), (12, 0, 0.10), asphalt)
        for i, x in enumerate(np.arange(-10, 130, 6.0)):
            self.cube(f"/World/RoadMarks/M{i}", (2.6, 0.18, 0.02), (x, -13, 0.13), white)
        for i, y in enumerate((-24, -18, 18, 24)):
            self.cube(f"/World/PadLines/L{i}", (86, 0.12, 0.015), (50, y, 0.08), white)

        # --------------------------------------------------------- buildings
        self._hall("/World/HallA", (68, -19.6), (36, 12, 8.5), wall, roof, glass, south=True)
        self._hall("/World/HallB", (70, 19.6), (28, 14, 7.2), wall_blue, roof, glass, south=False)
        self._hall("/World/Admin", (25, 19.5), (10, 12, 5.6), white, roof, glass, south=False)
        self.cube("/World/HallA/Door", (3.4, 0.3, 4.2), (58, -25.72, 2.1), dark_steel)
        self.cube("/World/HallA/Dock", (7, 4.0, 0.7), (58, -27.2, 0.45), concrete)
        self.cube("/World/Admin/Door", (2.4, 0.3, 3.1), (25, 13.42, 1.55), glass)

        # roof equipment
        for i, (x, y) in enumerate([(52, -19), (60, -21), (76, -18), (82, -22)]):
            self.cube(f"/World/HallA/HVAC{i}", (4, 3, 1.6), (x, y, 9.3), dark_steel)
            self.cylinder(f"/World/HallA/Vent{i}", 0.5, 1.4, (x + 1.2, y, 10.6), steel)
        for i, x in enumerate((58, 68, 78)):
            self.cube(f"/World/HallB/HVAC{i}", (4.5, 3.5, 1.4), (x, 18, 11.4), white)

        # ------------------------------------------------------------ tanks
        for i, (x, y, r, h, m) in enumerate(
            [(44, 19, 4.4, 11.5, white), (54, 19, 4.4, 11.5, steel), (64, 18.5, 3.4, 9.0, rust)]
        ):
            base = f"/World/Tanks/T{i}"
            self.cylinder(base, r, h, (x, y, h / 2), m)
            self.cylinder(base + "/Rim", r * 1.03, 0.35, (x, y, h - 0.15), dark_steel)
            self.sphere(base + "/Dome", r, (x, y, h), m, scale=(1, 1, 0.28))
            self.cylinder(base + "/Pipe", 0.22, 3.4, (x + r + 0.5, y, 1.7), steel)
            self.cube(base + "/Ladder", (0.6, 0.12, h), (x - r - 0.18, y + 0.5, h / 2), dark_steel)
            for z in np.arange(1.0, h, 1.2):
                self.cube(f"{base}/LadderRung{int(z*10)}", (0.7, 0.1, 0.08), (x - r - 0.18, y + 0.5, z), dark_steel)
        # bund wall
        self.cube("/World/Tanks/BundS", (29, 0.45, 1.0), (54, 13.4, 0.5), concrete)
        self.cube("/World/Tanks/BundN", (29, 0.45, 1.0), (54, 24.4, 0.5), concrete)

        # ---------------------------------------------------------- chimney
        cx, cy = 82, 18
        self.cylinder("/World/Chimney", 1.55, 30, (cx, cy, 15), white)
        for z in (6, 16, 26):
            self.cylinder(f"/World/Chimney/Band{z}", 1.6, 1.4, (cx, cy, z), red)
        self.cylinder("/World/Chimney/Cap", 1.75, 0.6, (cx, cy, 30.1), dark_steel)
        for z in (4, 12, 20):
            self.sphere(f"/World/Chimney/Beacon{z}", 0.16, (cx, cy + 1.5, z), lamp)
            self.dynamic["beacons"].append(f"/World/Chimney/Beacon{z}")

        # ------------------------------------------------------- pipe rack
        for i, x in enumerate(np.arange(20, 44, 6.0)):
            self.cube(f"/World/PipeRack/Post{i}", (0.35, 0.35, 5.6), (x, 10.5, 2.8), steel)
            self.cube(f"/World/PipeRack/Beam{i}", (0.4, 3.2, 0.3), (x, 11.2, 5.4), steel)
        for i, (y, z, mat) in enumerate(((10.2, 5.9, steel), (10.5, 6.35, white), (11.4, 5.9, rust))):
            self.cylinder(f"/World/PipeRack/Pipe{i}", 0.24, 25, (32, y, z), mat, axis="X")
        self.cylinder("/World/PipeRack/Riser", 0.28, 5.0, (19.8, 10.2, 3.0), steel)

        # -------------------------------------------------------- containers
        colors = [red, blue, orange, white]
        for i, (x, y, z, mat) in enumerate(
            [
                (46, -20.5, 1.3, red), (52, -20.5, 1.3, blue),
                (52, -20.5, 3.95, orange), (86, -7, 1.3, blue),
                (86, 1, 1.3, orange), (86, 8, 1.3, red),
            ]
        ):
            self._container(f"/World/Containers/C{i}", (x, y, z), mat)
        for i, (x, y) in enumerate([(40, -12), (42.5, -12), (41, -15)]):
            self.cylinder(f"/World/Barrels/B{i}", 0.42, 1.1, (x, y, 0.62), yellow if i % 2 else red)

        # ------------------------------------------------------------- fence
        self._fence()

        # ------------------------------------------------------------- source
        self.cube("/World/Source/Scorch", (13, 11, 0.05), (35, 0, 0.10), scorch)
        self.cylinder("/World/Source/Tank", 2.9, 4.6, (35, 0, 2.4), rust)
        self.cylinder("/World/Source/TankRim", 3.0, 0.45, (35, 0, 4.7), dark_steel)
        self.sphere("/World/Source/TankDome", 2.9, (35, 0, 4.6), rust, scale=(1, 1, 0.2))
        self.cube("/World/Source/Wreck", (7.5, 1.7, 1.7), (31.5, -2.5, 0.95), dark_steel, rot=(0, 8, 14))
        self.cube("/World/Source/Cab", (2.2, 1.9, 2.2), (28.4, -2.5, 1.3), rust, rot=(0, 0, 14))
        for i, (dx, dy, dz, r, h) in enumerate(
            [(0, 0, 6.2, 1.9, 4.0), (-1.1, 0.5, 5.7, 1.2, 3.1), (1.2, -0.6, 5.6, 1.3, 3.3), (0.3, 1.1, 5.9, 0.9, 2.6)]
        ):
            path = f"/World/Source/Flame{i}"
            self.cone(path, r, h, (35 + dx, dy, dz + h / 2 - 0.5), flame_mat if i else flame_core)
            self.dynamic["flames"].append(path)
        # a warm glow that also lights the wreck
        light = UsdLux.SphereLight.Define(self.stage, "/World/Source/FireLight")
        light.CreateIntensityAttr(9000)
        light.CreateRadiusAttr(2.5)
        light.CreateColorAttr(Gf.Vec3f(1.0, 0.32, 0.07))
        UsdGeom.Xformable(light.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(35, 0, 6.0))
        self.dynamic["fire_light"] = "/World/Source/FireLight"

        # --------------------------------------------------------- props
        for i, (x, y, z, mat) in enumerate(
            [(18, -20, 0.55, yellow), (19.2, -20.4, 0.55, blue), (18.6, -21.2, 1.55, red)]
        ):
            self.cube(f"/World/Props/Crate{i}", (1.1, 1.1, 1.1), (x, y, z), mat)
        for i, (x, y) in enumerate(((8, -20), (8, 20), (92, -20), (92, 20))):
            self._light_pole(f"/World/LightPoles/P{i}", x, y, lamp)

        # ------------------------------------------------------ trees/context
        rng = np.random.default_rng(12)
        for i in range(22):
            side = -1 if i % 2 == 0 else 1
            x = 2 + i * 4.6 + rng.uniform(-1.2, 1.2)
            y = side * (34 + rng.uniform(-5, 5))
            h = rng.uniform(5.5, 9.5)
            self.cylinder(f"/World/Trees/T{i}/Trunk", 0.28, h * 0.45, (x, y, h * 0.22), trunk)
            self.cone(f"/World/Trees/T{i}/Crown", 2.0, h, (x, y, h * 0.55), tree_mat)
        for i, (x, y, sx, sy, h) in enumerate(
            [(118, -34, 18, 12, 13), (132, 26, 14, 20, 17), (142, -10, 20, 14, 11), (104, 40, 12, 10, 9)]
        ):
            self.cube(f"/World/Distant/B{i}", (sx, sy, h), (x, y, h / 2), roof)
            self.cube(f"/World/Distant/B{i}/Top", (sx + 1, sy + 1, 0.6), (x, y, h + 0.3), dark_steel)
        # distant chimneys
        for i, (x, y, h) in enumerate(((120, -22, 34), (136, -6, 28))):
            self.cylinder(f"/World/Distant/Stack{i}", 1.6, h, (x, y, h / 2), white)
            self.cylinder(f"/World/Distant/Stack{i}/Band", 1.65, 2.0, (x, y, h * 0.55), red)

        # ------------------------------------------------------------ lights
        dome = UsdLux.DomeLight.Define(self.stage, "/World/Lights/Dome")
        sky = self._sky_texture()
        if sky:
            dome.CreateTextureFileAttr(str(sky))
            dome.CreateTextureFormatAttr("latlong")
            dome.CreateIntensityAttr(1.6)
        else:
            dome.CreateColorAttr(Gf.Vec3f(0.42, 0.55, 0.78))
            dome.CreateIntensityAttr(320)

        sun = UsdLux.DistantLight.Define(self.stage, "/World/Lights/Sun")
        sun.CreateIntensityAttr(1050)
        sun.CreateAngleAttr(0.55)
        sun.CreateColorAttr(Gf.Vec3f(1.0, 0.90, 0.76))
        UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-42, 24, 18))

        fill = UsdLux.DistantLight.Define(self.stage, "/World/Lights/Fill")
        fill.CreateIntensityAttr(180)
        fill.CreateAngleAttr(4.0)
        fill.CreateColorAttr(Gf.Vec3f(0.55, 0.68, 0.95))
        UsdGeom.Xformable(fill.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-20, -35, 210))

        return world, self.dynamic

    # --------------------------------------------------------------- helpers
    def _hall(self, path, center, size, wall_mat, roof_mat, glass_mat, south=True):
        x, y = center
        sx, sy, sz = size
        self.cube(path, (sx, sy, sz), (x, y, sz / 2), wall_mat)
        self.cube(path + "/Roof", (sx + 0.8, sy + 0.8, 0.6), (x, y, sz + 0.3), roof_mat)
        face_y = y + (sy / 2 + 0.05) * (-1 if south else 1)
        for i in range(5):
            wx = x - sx / 2 + 5 + i * (sx - 10) / 4
            self.cube(f"{path}/Window{i}", (3.2, 0.15, 2.2), (wx, face_y, sz * 0.58), glass_mat)
        self.cube(path + "/Stripe", (sx + 0.2, 0.2, 0.9), (x, face_y, 1.1), self.material("Stripe", (0.04, 0.12, 0.18), 0.6))
        # roof ridge / vents
        self.cube(path + "/Ridge", (sx, 1.2, 0.5), (x, y, sz + 0.7), roof_mat)

    def _container(self, path, pos, mat):
        x, y, z = pos
        sx, sy, sz = 6.0, 2.45, 2.55
        self.cube(path, (sx, sy, sz), (x, y, z), mat)
        self.cube(path + "/FrameT", (sx + 0.12, sy + 0.12, 0.16), (x, y, z + sz / 2), dark := self.material("ContFrame", (0.08, 0.08, 0.08), 0.5))
        self.cube(path + "/FrameB", (sx + 0.12, sy + 0.12, 0.16), (x, y, z - sz / 2), dark)
        for i in range(5):
            self.cube(f"{path}/Rib{i}", (0.10, sy + 0.08, sz * 0.9), (x - sx / 2 + 0.6 + i * 1.2, y, z), dark)

    def _fence(self):
        post_mat = self.material("FencePost", (0.21, 0.23, 0.22), 0.55, 0.6)
        rail_mat = self.material("FenceRail", (0.32, 0.34, 0.32), 0.5, 0.7)
        for i, x in enumerate(np.arange(4, 97, 5.0)):
            self.cube(f"/World/Fence/S{i}", (0.16, 0.16, 3.2), (x, -25.6, 1.6), post_mat)
            self.cube(f"/World/Fence/N{i}", (0.16, 0.16, 3.2), (x, 25.6, 1.6), post_mat)
        for j, y in enumerate(np.arange(-20, 21, 5.0)):
            self.cube(f"/World/Fence/W{j}", (0.16, 0.16, 3.2), (4, y, 1.6), post_mat)
            self.cube(f"/World/Fence/E{j}", (0.16, 0.16, 3.2), (96, y, 1.6), post_mat)
        self.cube("/World/Fence/SouthRail", (92, 0.08, 0.08), (50, -25.6, 2.9), rail_mat)
        self.cube("/World/Fence/NorthRail", (92, 0.08, 0.08), (50, 25.6, 2.9), rail_mat)
        self.cube("/World/Fence/SouthMesh", (92, 0.04, 2.2), (50, -25.6, 1.6), rail_mat)
        self.cube("/World/Fence/NorthMesh", (92, 0.04, 2.2), (50, 25.6, 1.6), rail_mat)

    def _light_pole(self, path, x, y, lamp_mat):
        self.cylinder(path, 0.16, 9.0, (x, y, 4.5), self.material("Pole", (0.12, 0.13, 0.13), 0.5, 0.6))
        self.cube(path + "/Arm", (2.2, 0.16, 0.16), (x - 1.0, y, 9.0), self.material("Pole", (0.12, 0.13, 0.13), 0.5, 0.6))
        self.cube(path + "/Head", (0.9, 0.45, 0.22), (x - 2.0, y, 8.9), lamp_mat)

    def _sky_texture(self):
        path = self.asset_dir / "sky.png"
        if path.exists():
            return path
        try:
            from PIL import Image, ImageFilter

            w, h = 2048, 1024
            yy = np.linspace(0.0, 1.0, h)[:, None]
            top = np.array([0.055, 0.13, 0.34])
            mid = np.array([0.30, 0.48, 0.70])
            horizon = np.array([0.74, 0.72, 0.66])
            t = yy
            img = np.zeros((h, w, 3), dtype=np.float64)
            lower = t < 0.55
            f = (t / 0.55)[..., None]
            img[:] = top * (1 - f) + mid * f
            f2 = ((t - 0.55) / 0.45)[..., None]
            img = np.where(lower, img, mid * (1 - f2) + horizon * f2)
            # soft cloud bands
            rng = np.random.default_rng(4)
            noise = rng.normal(0, 1, (h // 8, w // 8, 3))
            noise = np.asarray(Image.fromarray(((noise - noise.min()) / (noise.ptp() + 1e-9) * 255).astype(np.uint8)))
            noise_img = Image.fromarray((noise.mean(axis=2)).astype(np.uint8)).resize((w, h), Image.BICUBIC)
            noise_img = noise_img.filter(ImageFilter.GaussianBlur(28))
            cloud = np.asarray(noise_img, dtype=np.float64) / 255.0
            cloud = np.clip((cloud - 0.52) * 2.4, 0, 1)[..., None]
            img = img * (1.0 - 0.26 * cloud) + np.array([0.86, 0.87, 0.90]) * (0.26 * cloud)
            # warm glow near horizon
            glow = np.exp(-((t - 0.57) ** 2) / (2 * 0.09**2))
            img = img + np.array([0.18, 0.10, 0.02]) * glow
            img = np.clip(img, 0, 1)
            Image.fromarray((img * 255).astype(np.uint8)).save(path)
            return path
        except Exception:
            return None

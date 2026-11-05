import time
from pathlib import Path

from isaacsim import SimulationApp

app = SimulationApp({"headless": False, "width": 1280, "height": 720, "hide_ui": True})

import omni.usd
from pxr import Gf, Sdf, UsdGeom, UsdLux, UsdShade
from isaacsim.core.utils.viewports import set_camera_view
from omni.kit.viewport.utility import get_active_viewport

stage = omni.usd.get_context().get_stage()
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
UsdGeom.SetStageMetersPerUnit(stage, 1.0)

world = UsdGeom.Xform.Define(stage, "/World").GetPrim()


def material(name, color, rough=0.6, metal=0.0, opacity=1.0, emissive=None):
    path = f"/World/Looks/{name}"
    mat = UsdShade.Material.Define(stage, path)
    sh = UsdShade.Shader.Define(stage, path + "/Shader")
    sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(rough)
    sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metal)
    sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(opacity)
    if emissive:
        sh.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*emissive))
    mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return mat


def cube(path, size, pos, mat, rot=None):
    c = UsdGeom.Cube.Define(stage, path)
    c.CreateSizeAttr(1.0)
    x = UsdGeom.Xformable(c.GetPrim())
    x.AddTranslateOp().Set(Gf.Vec3d(*pos))
    x.AddScaleOp().Set(Gf.Vec3f(*size))
    if rot:
        x.AddRotateXYZOp().Set(Gf.Vec3f(*rot))
    UsdShade.MaterialBindingAPI.Apply(c.GetPrim()).Bind(mat)
    return c


ground_mat = material("Ground", (0.16, 0.17, 0.16), rough=0.95)
steel = material("Steel", (0.42, 0.45, 0.48), rough=0.35, metal=0.8)
wall = material("Wall", (0.55, 0.57, 0.56), rough=0.8)
roof = material("Roof", (0.23, 0.26, 0.28), rough=0.75)
accent = material("Accent", (0.05, 0.35, 0.55), rough=0.5, metal=0.3)

cube("/World/Ground", (300, 200, 0.2), (50, 0, -0.11), ground_mat)
cube("/World/BuildingA", (34, 22, 9), (56, -14, 4.5), wall)
cube("/World/BuildingA/roof", (35, 23, 0.6), (56, -14, 9.3), roof)
cube("/World/BuildingB", (24, 16, 6), (78, 12, 3), wall)
cube("/World/Tank", (10, 10, 12), (50, 14, 6), steel)
cube("/World/Box1", (6, 2.4, 2.6), (70, -2, 1.3), accent)
cube("/World/Box2", (6, 2.4, 2.6), (70, 1, 1.3), material("Orange", (0.75, 0.25, 0.06), rough=0.6))

dome = UsdLux.DomeLight.Define(stage, "/World/Dome")
dome.CreateIntensityAttr(350)
dome.CreateColorAttr(Gf.Vec3f(0.55, 0.68, 0.9))

sun = UsdLux.DistantLight.Define(stage, "/World/Sun")
sun.CreateIntensityAttr(2800)
sun.CreateAngleAttr(0.6)
sun.CreateColorAttr(Gf.Vec3f(1.0, 0.93, 0.82))
UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-38, 25, 0))

cam = UsdGeom.Camera.Define(stage, "/World/Camera")
cam.CreateFocalLengthAttr(24)
set_camera_view((118, -78, 46), (48, 0, 9), "/World/Camera")
viewport = get_active_viewport()
viewport.camera_path = "/World/Camera"

captures = Path(r"C:\isaac\captures")
captures.mkdir(parents=True, exist_ok=True)
for _ in range(45):
    app.update()
    time.sleep(0.01)

from omni.kit.viewport.utility import capture_viewport_to_file

out = captures / "test_scene.png"
capture_viewport_to_file(viewport, file_path=str(out), is_hdr=False)
for _ in range(90):
    app.update()
    time.sleep(0.02)
print("capture exists:", out.exists(), out.stat().st_size if out.exists() else 0, flush=True)
time.sleep(0.5)
app.close()

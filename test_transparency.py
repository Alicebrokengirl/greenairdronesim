import time
from pathlib import Path

from isaacsim import SimulationApp

app = SimulationApp({"headless": False, "width": 960, "height": 540, "hide_ui": True})
import carb
import omni.usd
from omni.kit.viewport.utility import capture_viewport_to_file, get_active_viewport
from pxr import Gf, Sdf, UsdGeom, UsdLux, UsdShade

s = carb.settings.get_settings()
for k in ("/rtx/raying/fractionalCutoutOpacity", "/rtx/raytracing/fractionalCutoutOpacity"):
    s.set(k, True)
s.set("/rtx/translucency/enabled", True)

stage = omni.usd.get_context().get_stage()
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
UsdGeom.SetStageMetersPerUnit(stage, 1.0)
UsdGeom.Xform.Define(stage, "/World")


def mat(name, color, opacity):
    p = f"/World/Looks/{name}"
    m = UsdShade.Material.Define(stage, p)
    sh = UsdShade.Shader.Define(stage, p + "/Shader")
    sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.6)
    sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(opacity)
    m.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return m


red = mat("Red", (0.8, 0.05, 0.05), 1.0)
glass = mat("Glass", (0.1, 0.5, 0.9), 0.2)
gray = mat("Gray", (0.5, 0.5, 0.5), 1.0)

g = UsdGeom.Cube.Define(stage, "/World/Ground")
g.CreateSizeAttr(1)
gx = UsdGeom.Xformable(g.GetPrim())
gx.AddTranslateOp().Set(Gf.Vec3d(0, 0, -0.05))
gx.AddScaleOp().Set(Gf.Vec3f(8, 8, 0.1))
UsdShade.MaterialBindingAPI.Apply(g.GetPrim()).Bind(gray)

for name, x, m in (("Red", -1.0, red), ("Glass", 0.0, glass)):
    sp = UsdGeom.Sphere.Define(stage, f"/World/{name}")
    sp.CreateRadiusAttr(0.6)
    UsdGeom.Xformable(sp.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(x, 0, 0.6))
    UsdShade.MaterialBindingAPI.Apply(sp.GetPrim()).Bind(m)

# a cube behind the glass sphere
c = UsdGeom.Cube.Define(stage, "/World/Back")
c.CreateSizeAttr(1)
cx = UsdGeom.Xformable(c.GetPrim())
cx.AddTranslateOp().Set(Gf.Vec3d(0, 1.5, 0.8))
cx.AddScaleOp().Set(Gf.Vec3f(1.2, 0.1, 1.2))
UsdShade.MaterialBindingAPI.Apply(c.GetPrim()).Bind(red)

d = UsdLux.DomeLight.Define(stage, "/World/Dome")
d.CreateIntensityAttr(800)
sun = UsdLux.DistantLight.Define(stage, "/World/Sun")
sun.CreateIntensityAttr(1500)
UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-35, 20, 0))

cam = UsdGeom.Camera.Define(stage, "/World/Cam")
cam.CreateFocalLengthAttr(24)
from isaacsim.core.utils.viewports import set_camera_view

set_camera_view((0, -6, 3), (0, 0, 0.6), "/World/Cam")
vp = get_active_viewport()
vp.camera_path = "/World/Cam"
for _ in range(60):
    app.update()
    time.sleep(0.02)
out = Path(r"C:\isaac\captures\transparency.png")
out.parent.mkdir(exist_ok=True)
capture_viewport_to_file(vp, file_path=str(out), is_hdr=False)
for _ in range(40):
    app.update()
    time.sleep(0.02)
print("exists", out.exists(), out.stat().st_size if out.exists() else 0)
app.close()

import time
from pathlib import Path

from isaacsim import SimulationApp

app = SimulationApp({"headless": False, "width": 960, "height": 540, "hide_ui": True})
import carb
import omni.usd
from omni.kit.viewport.utility import capture_viewport_to_file, get_active_viewport
from pxr import Gf, Sdf, UsdGeom, UsdLux, UsdShade, Vt

s = carb.settings.get_settings()
s.set("/rtx/raytracing/fractionalCutoutOpacity", True)
s.set("/rtx/translucency/enabled", True)
stage = omni.usd.get_context().get_stage()
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
UsdGeom.Xform.Define(stage, "/World")

p = "/World/Looks/Glass"
m = UsdShade.Material.Define(stage, p)
sh = UsdShade.Shader.Define(stage, p + "/Shader")
sh.CreateIdAttr("UsdPreviewSurface")
sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.1, 0.4, 0.9))
sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.4)
sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.2)
m.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")

proto = UsdGeom.Sphere.Define(stage, "/World/PI/Proto")
proto.CreateRadiusAttr(0.7)
UsdShade.MaterialBindingAPI.Apply(proto.GetPrim()).Bind(m)
pi = UsdGeom.PointInstancer.Define(stage, "/World/PI")
pi.CreatePrototypesRel().AddTarget(proto.GetPath())
pi.CreateProtoIndicesAttr(Vt.IntArray([0, 0, 0]))
pi.CreatePositionsAttr(Vt.Vec3fArray([Gf.Vec3f(-1.8, 0, 0.7), Gf.Vec3f(0, 0, 0.7), Gf.Vec3f(1.8, 0, 0.7)]))
pi.CreateScalesAttr(Vt.Vec3fArray([Gf.Vec3f(1, 1, 1)] * 3))

red = UsdShade.Material.Define(stage, "/World/Looks/Red")
r = UsdShade.Shader.Define(stage, "/World/Looks/Red/Shader")
r.CreateIdAttr("UsdPreviewSurface")
r.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.8, 0.05, 0.03))
red.CreateSurfaceOutput().ConnectToSource(r.ConnectableAPI(), "surface")
c = UsdGeom.Cube.Define(stage, "/World/Back")
c.CreateSizeAttr(1)
cx = UsdGeom.Xformable(c.GetPrim())
cx.AddTranslateOp().Set(Gf.Vec3d(0, 1.2, 1.0))
cx.AddScaleOp().Set(Gf.Vec3f(4, 0.1, 1.5))
UsdShade.MaterialBindingAPI.Apply(c.GetPrim()).Bind(red)

d = UsdLux.DomeLight.Define(stage, "/World/Dome")
d.CreateIntensityAttr(900)
sun = UsdLux.DomeLight.Define(stage, "/World/Sun")
sun.CreateIntensityAttr(500)
cam = UsdGeom.Camera.Define(stage, "/World/Cam")
from isaacsim.core.utils.viewports import set_camera_view

set_camera_view((0, -6, 2.2), (0, 0, 0.7), "/World/Cam")
vp = get_active_viewport()
vp.camera_path = "/World/Cam"
for _ in range(60):
    app.update()
    time.sleep(0.02)
out = Path(r"C:\isaac\captures\instancer_transparency.png")
capture_viewport_to_file(vp, file_path=str(out), is_hdr=False)
for _ in range(30):
    app.update()
    time.sleep(0.02)
app.close()

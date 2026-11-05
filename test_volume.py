import time
from pathlib import Path

from isaacsim import SimulationApp

app = SimulationApp({"headless": False, "width": 960, "height": 540, "hide_ui": True})
import carb
import omni.usd
from omni.kit.viewport.utility import capture_viewport_to_file, get_active_viewport
from pxr import Gf, Sdf, UsdGeom, UsdLux, UsdShade

s = carb.settings.get_settings()
s.set("/app/viewport/grid/enabled", False)
s.set("/app/viewport/axis/enabled", False)
s.set("/persistent/app/viewport/displayOptions", 0)
s.set("/rtx/pathtracing/ptvol/enabled", True)
stage = omni.usd.get_context().get_stage()
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
UsdGeom.Xform.Define(stage, "/World")

mat_path = "/World/Looks/Vol"
m = UsdShade.Material.Define(stage, mat_path)
sh = UsdShade.Shader.Define(stage, mat_path + "/Shader")
sh.CreateImplementationSourceAttr(UsdShade.Tokens.sourceAsset)
sh.SetSourceAsset("OmniVolumeDensity.mdl", "mdl")
sh.SetSourceAssetSubIdentifier("OmniVolumeDensity", "mdl")
sh.CreateInput("volume_density_texture", Sdf.ValueTypeNames.Asset).Set(r"C:\isaac\captures\test_volume.vdb")
sh.CreateInput("volume_albedo", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.75, 0.8, 1.0))
sh.CreateInput("volume_density_scale", Sdf.ValueTypeNames.Float).Set(3.0)
sh.CreateInput("directional_bias", Sdf.ValueTypeNames.Float).Set(0.2)
for out in ("mdl:surface", "mdl:volume", "mdl:displacement"):
    m.CreateOutput(out, Sdf.ValueTypeNames.Token).ConnectToSource(sh.ConnectableAPI(), "out")

mesh = UsdGeom.Mesh.Define(stage, "/World/Vol")
mesh.CreatePointsAttr([(-1, -1, -1), (1, -1, -1), (-1, -1, 1), (1, -1, 1),
                       (-1, 1, -1), (1, 1, -1), (1, 1, 1), (-1, 1, 1)])
mesh.CreateFaceVertexCountsAttr([4] * 6)
mesh.CreateFaceVertexIndicesAttr([0, 1, 3, 2, 0, 4, 5, 1, 1, 5, 6, 3,
                                  2, 3, 6, 7, 0, 2, 7, 4, 4, 7, 6, 5])
mesh.CreateExtentAttr([(-1, -1, -1), (1, 1, 1)])
nrm = [(-1, 0, 0), (-1, 0, 0), (-1, 0, 0), (-1, 0, 0)] * 6
mesh.CreateNormalsAttr(nrm)
mesh.SetNormalsInterpolation('faceVarying')
mesh.GetPrim().CreateAttribute("subdivisionScheme", Sdf.ValueTypeNames.Token).Set("none")
mesh.GetPrim().CreateAttribute("primvars:isVolume", Sdf.ValueTypeNames.Bool).Set(True)
UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(m)

red = UsdShade.Material.Define(stage, "/World/Looks/Red")
rs = UsdShade.Shader.Define(stage, "/World/Looks/Red/Shader")
rs.CreateIdAttr("UsdPreviewSurface")
rs.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(1, 0, 0))
red.CreateSurfaceOutput().ConnectToSource(rs.ConnectableAPI(), "surface")
rc = UsdGeom.Cube.Define(stage, "/World/RedCube")
rc.CreateSizeAttr(1.0)
UsdGeom.Xformable(rc.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(2.5, 0, 0))
UsdShade.MaterialBindingAPI.Apply(rc.GetPrim()).Bind(red)

d = UsdLux.DomeLight.Define(stage, "/World/Dome")
d.CreateIntensityAttr(1200)
sun = UsdLux.DistantLight.Define(stage, "/World/Sun")
sun.CreateIntensityAttr(2500)
sun.CreateAngleAttr(1.0)

cam = UsdGeom.Camera.Define(stage, "/World/Cam")
cam.CreateFocalLengthAttr(24)
from isaacsim.core.utils.viewports import set_camera_view
vp = get_active_viewport()
vp.camera_path = "/World/Cam"
vp.set_hd_engine("rtx", "PathTracing")
print("RENDERMODE", vp.hydra_engine, vp.render_mode, flush=True)
set_camera_view((4.5, -4.5, 3.0), (0, 0, 0), "/World/Cam", vp)
print("CAM", vp.camera_path, cam.ComputeLocalToWorldTransform(0).ExtractTranslation(), flush=True)
for i in range(120):
    set_camera_view((4.5, -4.5, 3.0), (0, 0, 0), "/World/Cam", vp)
    app.update()
    time.sleep(0.03)
print("CAM2", cam.ComputeLocalToWorldTransform(0).ExtractTranslation(), flush=True)
stage.GetRootLayer().Export(r"C:\isaac\captures\test_volume.usda")
out = Path(r"C:\isaac\captures\test_volume.png")
capture_viewport_to_file(vp, file_path=str(out), is_hdr=False)
for _ in range(30):
    app.update()
    time.sleep(0.03)
app.close()


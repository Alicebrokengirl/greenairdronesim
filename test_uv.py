import time
from pathlib import Path

from isaacsim import SimulationApp

app = SimulationApp({"headless": False, "width": 960, "height": 540, "hide_ui": True})
import omni.usd
from omni.kit.viewport.utility import capture_viewport_to_file, get_active_viewport
from pxr import Gf, Sdf, UsdGeom, UsdLux, UsdShade, Vt

stage = omni.usd.get_context().get_stage()
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
UsdGeom.Xform.Define(stage, "/World")
texfile = "C:/isaac/greenair/assets/smoke_sprite_12.png"


def make_mat(path, opacity_from_tex=True, opacity=1.0):
    mat = UsdShade.Material.Define(stage, path)
    sh = UsdShade.Shader.Define(stage, path + "/Shader")
    sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1.0)
    sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    if opacity_from_tex:
        sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.8, 0.2, 0.1))
        reader = UsdShade.Shader.Define(stage, path + "/stReader")
        reader.CreateIdAttr("UsdPrimvarReader_float2")
        reader.CreateInput("varname", Sdf.ValueTypeNames.String).Set("st")
        tex = UsdShade.Shader.Define(stage, path + "/tex")
        tex.CreateIdAttr("UsdUVTexture")
        tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(texfile))
        tex.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("clamp")
        tex.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("clamp")
        tex.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("raw")
        tex.CreateInput("st", Sdf.ValueTypeNames.TexCoord2f).ConnectToSource(reader.ConnectableAPI(), "result")
        sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).ConnectToSource(tex.ConnectableAPI(), "a")
    else:
        sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.2, 0.4, 0.8))
        sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(opacity)
    mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return mat


def make_card(path, mat, x):
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr([Gf.Vec3f(-1, -1, 0), Gf.Vec3f(1, -1, 0), Gf.Vec3f(1, 1, 0), Gf.Vec3f(-1, 1, 0)])
    mesh.CreateFaceVertexCountsAttr([4])
    mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    mesh.CreateDoubleSidedAttr(True)
    pv = UsdGeom.PrimvarsAPI(mesh.GetPrim()).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying)
    pv.Set(Vt.Vec2fArray([(0, 0), (1, 0), (1, 1), (0, 1)]))
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(mat)
    xf = UsdGeom.Xformable(mesh.GetPrim())
    xf.AddTranslateOp().Set(Gf.Vec3d(x, 0, 1.3))
    xf.AddScaleOp().Set(Gf.Vec3f(1.3, 1.3, 1.3))
    return mesh

m1 = make_mat("/World/Looks/A")
make_card("/World/CardStatic", m1, -1.6)
mp = make_mat("/World/Looks/B")
proto = make_card("/World/PI/Proto", mp, 0)
xfp = UsdGeom.Xformable(proto.GetPrim())
xfp.GetTranslateOp().Set(Gf.Vec3d(0, 0, 0))
pi = UsdGeom.PointInstancer.Define(stage, "/World/PI")
pi.CreatePrototypesRel().AddTarget(proto.GetPath())
pi.CreateProtoIndicesAttr(Vt.IntArray([0, 0]))
pi.CreatePositionsAttr(Vt.Vec3fArray([Gf.Vec3f(1.6, 0, 1.3), Gf.Vec3f(3.5, 0, 1.3)]))
pi.CreateScalesAttr(Vt.Vec3fArray([Gf.Vec3f(1.3), Gf.Vec3f(1.3)]))

UsdGeom.Cube.Define(stage, "/World/Back").CreateSizeAttr(1)
from pxr import UsdGeom as UG
c = stage.GetPrimAtPath("/World/Back")
cx = UsdGeom.Xformable(c)
cx.AddTranslateOp().Set(Gf.Vec3d(0, 3, 1.5))
cx.AddScaleOp().Set(Gf.Vec3f(10, 0.1, 3))
d = UsdLux.DomeLight.Define(stage, "/World/Dome"); d.CreateIntensityAttr(800)
from isaacsim.core.utils.viewports import set_camera_view

cam = UsdGeom.Camera.Define(stage, "/World/Cameras/Main")
cam.CreateFocalLengthAttr(24.0)
cam.CreateHorizontalApertureAttr(20.955)
cam.CreateVerticalApertureAttr(11.787)
vp = get_active_viewport()
vp.camera_path = "/World/Cameras/Main"
set_camera_view((0, -6, 2.2), (0.4, 0, 1.4), "/World/Cameras/Main", vp)
for _ in range(60):
    app.update(); time.sleep(0.02)
out = Path(r"C:\isaac\captures\uv_test.png")
capture_viewport_to_file(vp, file_path=str(out), is_hdr=False)
for _ in range(30):
    app.update(); time.sleep(0.02)
app.close()

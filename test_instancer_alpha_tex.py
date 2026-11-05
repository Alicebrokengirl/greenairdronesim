import os
import time
from pathlib import Path

import numpy as np
from PIL import Image

from isaacsim import SimulationApp

OUT_DIR = Path(r"C:\isaac\captures")
OUT_DIR.mkdir(parents=True, exist_ok=True)

tex = OUT_DIR / "sprite_radial.png"
N = 128
yy, xx = np.mgrid[0:N, 0:N]
cx = cy = (N - 1) / 2.0
r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (N / 2.0)
alpha = np.clip(1.0 - r, 0.0, 1.0) ** 1.6
rgba = np.zeros((N, N, 4), dtype=np.uint8)
rgba[..., 0] = 255
rgba[..., 1] = 60
rgba[..., 2] = 0
rgba[..., 3] = (alpha * 255).astype(np.uint8)
Image.fromarray(rgba, "RGBA").save(tex)

app = SimulationApp({"headless": False, "width": 960, "height": 540, "hide_ui": True})
try:
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

    look = "/World/Looks/Sprite"
    m = UsdShade.Material.Define(stage, look)
    sh = UsdShade.Shader.Define(stage, look + "/Shader")
    sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1.0)
    sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    tex_reader = UsdShade.Shader.Define(stage, look + "/Tex")
    tex_reader.CreateIdAttr("UsdUVTexture")
    tex_reader.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(str(tex).replace("\\", "/"))
    tex_reader.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("clamp")
    tex_reader.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("clamp")
    out_rgb = tex_reader.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    out_a = tex_reader.CreateOutput("a", Sdf.ValueTypeNames.Float)
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(out_rgb)
    sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).ConnectToSource(out_a)
    st_reader = UsdShade.Shader.Define(stage, look + "/ST")
    st_reader.CreateIdAttr("UsdPrimvarReader_float2")
    st_reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    tex_reader.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(
        st_reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)
    )
    m.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")

    proto_path = "/World/PI/Proto"
    proto = UsdGeom.Mesh.Define(stage, proto_path)
    seg = 24
    pts = [Gf.Vec3f(0, 0, 0)]
    sts = [Gf.Vec2f(0.5, 0.5)]
    for k in range(seg):
        a = 2.0 * np.pi * k / seg
        x = np.cos(a)
        y = np.sin(a)
        pts.append(Gf.Vec3f(x, y, 0.0))
        sts.append(Gf.Vec2f(0.5 + 0.5 * x, 0.5 + 0.5 * y))
    counts = [3] * seg
    idx = []
    for k in range(seg):
        n = (k + 1) % seg
        idx.extend([0, 1 + k, 1 + n])
    proto.CreatePointsAttr(pts)
    proto.CreateFaceVertexCountsAttr(counts)
    proto.CreateFaceVertexIndicesAttr(idx)
    proto.CreateNormalsAttr([Gf.Vec3f(0, 0, 1)] * len(pts))
    proto.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
    st_attr = UsdGeom.PrimvarsAPI(proto.GetPrim()).CreatePrimvar(
        "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex
    )
    st_attr.Set(Vt.Vec2fArray(sts))
    proto.CreateDoubleSidedAttr(True)
    UsdShade.MaterialBindingAPI.Apply(proto.GetPrim()).Bind(m)

    pi = UsdGeom.PointInstancer.Define(stage, "/World/PI")
    pi.CreatePrototypesRel().AddTarget(proto_path)
    pi.CreateProtoIndicesAttr(Vt.IntArray([0, 0, 0]))
    pi.CreatePositionsAttr(
        Vt.Vec3fArray([Gf.Vec3f(-2.2, 0, 0), Gf.Vec3f(0, 0, 0), Gf.Vec3f(2.2, 0, 0)])
    )
    pi.CreateScalesAttr(Vt.Vec3fArray([Gf.Vec3f(1.4, 1.4, 1.4)] * 3))
    pi.CreateOrientationsAttr(Vt.QuathArray([Gf.Quath(1, 0, 0, 0)] * 3))

    d = UsdLux.DomeLight.Define(stage, "/World/Dome")
    d.CreateIntensityAttr(300)

    dk = UsdShade.Material.Define(stage, "/World/Looks/Dark")
    dks = UsdShade.Shader.Define(stage, "/World/Looks/Dark/Shader")
    dks.CreateIdAttr("UsdPreviewSurface")
    dks.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.02, 0.02, 0.03))
    dk.CreateSurfaceOutput().ConnectToSource(dks.ConnectableAPI(), "surface")
    bp = UsdGeom.Cube.Define(stage, "/World/Backdrop")
    bp.CreateSizeAttr(1)
    bpx = UsdGeom.Xformable(bp.GetPrim())
    bpx.AddTranslateOp().Set(Gf.Vec3d(0, 0, -0.6))
    bpx.AddScaleOp().Set(Gf.Vec3f(14, 14, 0.02))
    UsdShade.MaterialBindingAPI.Apply(bp.GetPrim()).Bind(dk)

    cam = UsdGeom.Camera.Define(stage, "/World/Cam")
    from isaacsim.core.utils.viewports import set_camera_view

    set_camera_view((0, 0, 18.0), (0, 0, 0), "/World/Cam")
    vp = get_active_viewport()
    vp.camera_path = "/World/Cam"
    for _ in range(70):
        app.update()
        time.sleep(0.02)
    capture_viewport_to_file(vp, file_path=str(OUT_DIR / "instancer_alpha_tex.png"), is_hdr=False)
    for _ in range(40):
        app.update()
        time.sleep(0.02)
finally:
    try:
        app.close()
    except Exception:
        pass
    os._exit(0)

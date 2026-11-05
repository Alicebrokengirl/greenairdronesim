import time
from pathlib import Path

from isaacsim import SimulationApp

app = SimulationApp({"headless": False, "width": 960, "height": 540, "hide_ui": True})
import carb
import omni.usd
from omni.kit.viewport.utility import capture_viewport_to_file, get_active_viewport
from pxr import Gf, UsdGeom

s = carb.settings.get_settings()
s.set("/app/viewport/grid/enabled", False)
s.set("/app/viewport/axis/enabled", False)
s.set("/persistent/app/viewport/displayOptions", 0)

ctx = omni.usd.get_context()
ctx.open_stage(r"C:\isaac\captures\vol_sample2.usda")
for _ in range(10):
    app.update()
    time.sleep(0.03)
stage = ctx.get_stage()
print("STAGE", stage.GetDefaultPrim(), flush=True)

cam = UsdGeom.Camera.Define(stage, "/World/TestCam")
cam.CreateFocalLengthAttr(24)
from isaacsim.core.utils.viewports import set_camera_view
vp = get_active_viewport()
vp.camera_path = "/World/TestCam"
vp.set_hd_engine("rtx", "PathTracing")
print("RENDERMODE", vp.hydra_engine, vp.render_mode, flush=True)
for i in range(150):
    set_camera_view((160, -160, 110), (0, 0, 0), "/World/TestCam", vp)
    app.update()
    time.sleep(0.03)
out = Path(r"C:\isaac\captures\vol_sample2.png")
capture_viewport_to_file(vp, file_path=str(out), is_hdr=False)
for _ in range(30):
    app.update()
    time.sleep(0.03)
app.close()


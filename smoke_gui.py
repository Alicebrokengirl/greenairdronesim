import time

from isaacsim import SimulationApp

app = SimulationApp(
    {
        "headless": False,
        "width": 960,
        "height": 600,
        "hide_ui": False,
    }
)
print("SimulationApp started", flush=True)

import omni.usd
from pxr import UsdGeom

stage = omni.usd.get_context().get_stage()
UsdGeom.Xform.Define(stage, "/World")
UsdGeom.Cube.Define(stage, "/World/Test")
for _ in range(30):
    app.update()
    time.sleep(0.05)
print("rendered 30 frames", flush=True)
app.close()

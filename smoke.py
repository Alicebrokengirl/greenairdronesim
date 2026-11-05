from isaacsim import SimulationApp

app = SimulationApp({"headless": True, "width": 640, "height": 480})
print("SimulationApp started", flush=True)

import omni.usd
import omni.ui  # noqa: F401
from pxr import Gf, Usd, UsdGeom, UsdLux, UsdShade, Vt  # noqa: F401

stage = omni.usd.get_context().get_stage()
print("stage:", stage, flush=True)
UsdGeom.Xform.Define(stage, "/World")
UsdGeom.Cube.Define(stage, "/World/Test")
print("pxr ok", flush=True)
print("version:", app.__version__ if hasattr(app, "__version__") else "n/a", flush=True)
app.close()

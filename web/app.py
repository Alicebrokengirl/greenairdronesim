from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import core

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
CAPTURES = Path(
    os.environ.get("GREENAIR_CAPTURES") or (ROOT.parent / "greenair" / "captures")
).expanduser().resolve()

app = FastAPI(title="GreenAirDrone", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def ensure_charset(request, call_next):
    response = await call_next(request)
    ctype = response.headers.get("content-type", "")
    if ctype and "charset" not in ctype and (
        ctype.startswith("text/") or ctype in ("application/javascript", "application/json")
    ):
        response.headers["content-type"] = f"{ctype}; charset=utf-8"
    return response


def _no_cache(payload):
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/overview")
def api_overview():
    return _no_cache(core.overview())


@app.get("/api/scenarios")
def api_scenarios():
    return _no_cache(
        {
            "scenarios": [core.scenario_summary(s) for s in core.available_scenarios()],
            "missing": [s for s in core.SCENARIO_META if s not in core.available_scenarios()],
        }
    )


@app.get("/api/scenario/{sid}")
def api_scenario(sid: str):
    if sid not in core.available_scenarios():
        raise HTTPException(404, "unknown scenario")
    return _no_cache(core.scenario_summary(sid))


@app.get("/api/scenario/{sid}/timeseries")
def api_timeseries(sid: str):
    if sid not in core.available_scenarios():
        raise HTTPException(404, "unknown scenario")
    return _no_cache(core.timeseries(sid))


@app.get("/api/scenario/{sid}/measurements")
def api_measurements(sid: str):
    if sid not in core.available_scenarios():
        raise HTTPException(404, "unknown scenario")
    return _no_cache(core.measurements(sid))


@app.get("/api/scenario/{sid}/axes")
def api_axes(sid: str):
    if sid not in core.available_scenarios():
        raise HTTPException(404, "unknown scenario")
    return _no_cache(core.axes(sid))


@app.get("/api/scenario/{sid}/slice")
def api_slice(
    sid: str,
    species: str = Query("CO"),
    t: float = Query(60.0),
    axis: str = Query("z", pattern="^[xyz]$"),
    index: int | None = Query(None),
):
    if sid not in core.available_scenarios():
        raise HTTPException(404, "unknown scenario")
    return _no_cache(core.slice_data(sid, species, t, axis, index))


@app.get("/api/isaac/status")
def api_isaac():
    return _no_cache(core.isaac_status())


@app.post("/api/isaac/scenario/{sid}")
def api_isaac_scenario(sid: str):
    if sid not in core.available_scenarios():
        raise HTTPException(404, "unknown scenario")
    cmd = CAPTURES / "switch_scenario.txt"
    cmd.parent.mkdir(parents=True, exist_ok=True)
    cmd.write_text(sid, encoding="utf-8")
    state = core.isaac_status()
    return {"requested": sid, "connected": bool(state.get("connected"))}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


if __name__ == "__main__":
    import logging

    import uvicorn

    handler = logging.FileHandler(ROOT / "server_run.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)
    logging.getLogger("uvicorn.error").info("Starting GreenAirDrone web server")
    uvicorn.run(app, host="127.0.0.1", port=8080, log_config=None, access_log=False)

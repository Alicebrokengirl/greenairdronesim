"""Launch the GreenAirDrone Isaac Sim visualisation.

Run from this directory with a Python that has Isaac Sim installed:

    python app.py
    python app.py --still 5,20,40 --out captures

Paths are resolved relative to the repository root, so the project can be
cloned anywhere. Set GREENAIR_DATA to use a data folder outside the repo.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent


def _resolve_under_repo(value):
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def prepare_config(config):
    """Resolve repo-relative data paths for any checkout location."""
    scenario = str(config.get("scenario") or "industrial_fire")
    data_root = _resolve_under_repo(
        os.environ.get("GREENAIR_DATA") or config.get("data_root") or "data"
    )

    export_dir = config.get("export_dir")
    export_dir = (
        Path(export_dir).expanduser()
        if export_dir and Path(export_dir).is_absolute()
        else data_root / scenario / "export"
    )
    trajectory_csv = config.get("trajectory_csv")
    trajectory_csv = (
        Path(trajectory_csv).expanduser()
        if trajectory_csv and Path(trajectory_csv).is_absolute()
        else data_root / scenario / "drone_measurements.csv"
    )

    config["scenario"] = scenario
    config["data_root"] = str(data_root)
    config["export_dir"] = str(export_dir.resolve())
    config["trajectory_csv"] = str(trajectory_csv.resolve())
    config.setdefault("captures_dir", str(ROOT / "captures"))
    return config


def parse_args():
    p = argparse.ArgumentParser(description="GreenAirDrone Isaac Sim scene")
    p.add_argument("--config", default=str(ROOT / "config.yaml"))
    p.add_argument("--scenario", default=None, help="override scenario folder under data_root")
    p.add_argument("--camera", default=None, choices=["chase", "orbit", "ground", "top"])
    p.add_argument("--still", default=None, help="comma-separated data times; render and exit")
    p.add_argument("--out", default=str(ROOT / "captures"), help="still/capture output folder")
    p.add_argument("--exit-after", type=float, default=0.0, help="wall-clock seconds, 0 = run until closed")
    p.add_argument("--no-loop", action="store_true")
    p.add_argument("--no-hud", action="store_true")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--width", type=int, default=None)
    p.add_argument("--height", type=int, default=None)
    return p.parse_args()


def main():
    args = parse_args()
    os.environ.setdefault("OMNI_KIT_ACCEPT_EULA", "YES")
    os.environ.setdefault("OMNI_KIT_PRIVACY_CONSENT", "YES")

    import yaml

    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    if args.scenario:
        config["scenario"] = args.scenario
    config = prepare_config(config)
    if args.camera:
        config.setdefault("cameras", {})["start"] = args.camera

    export_dir = Path(config["export_dir"])
    if not (export_dir / "metadata.json").exists():
        raise SystemExit(
            f"[greenair] scenario data not found: {export_dir}\n"
            "Place the data folder next to greenair/ or set GREENAIR_DATA."
        )

    width = int(args.width or config.get("window", {}).get("width", 1280))
    height = int(args.height or config.get("window", {}).get("height", 720))
    simulation_app = None
    try:
        from isaacsim import SimulationApp

        simulation_app = SimulationApp(
            {
                "headless": bool(args.headless),
                "width": width,
                "height": height,
                "hide_ui": bool(config.get("window", {}).get("hide_ui", True)),
                "extra_args": [
                    f"--/app/window/width={width}",
                    f"--/app/window/height={height}",
                    f"--/app/renderer/resolution/width={width}",
                    f"--/app/renderer/resolution/height={height}",
                ],
            }
        )

        import omni.usd

        context = omni.usd.get_context()
        if context.get_stage() is None:
            context.new_stage()
        from mission import GreenAirMission

        mission = GreenAirMission(simulation_app, config, args)
        mission.start_clock()
        if args.still:
            times = [float(x.strip()) for x in args.still.split(",") if x.strip()]
            mission.capture_stills(times, args.out)
            mission.close()
        else:
            mission.run()
    except Exception:
        import traceback

        traceback.print_exc()
        if simulation_app is not None:
            try:
                simulation_app.close()
            except Exception:
                pass
        sys.exit(1)


if __name__ == "__main__":
    main()

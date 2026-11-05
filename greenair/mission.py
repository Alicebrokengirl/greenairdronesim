"""Runtime mission loop: scene, field sampling, drone, cameras and HUD."""
from __future__ import annotations

import json
import math
import os
import time
from collections import deque
from pathlib import Path

import carb
import numpy as np
import omni.usd
from omni.kit.viewport.utility import capture_viewport_to_file, get_active_viewport
from pxr import Gf, UsdGeom

from cameras import CameraRig, FOCAL_MM, H_APERTURE, V_APERTURE
from drone_model import DroneModel
from hud import HUD
from plume_data import NOISE_FLOOR, PlumeData
from plume_visual import PlumeVisual
from scene_builder import SceneBuilder
from trajectory import DroneTrajectory

SENSOR_SPECIES = ("CO", "NO2", "SO2", "PM25", "PM10", "VOC", "HCl", "BENZENE")
SCENARIOS = (
    ("industrial_fire", "INDUSTRIAL FIRE"),
    ("urban_infrastructure_fire", "URBAN INFRASTRUCTURE FIRE"),
    ("debris_dust", "DEBRIS DUST"),
)
SCENARIO_LABELS = dict(SCENARIOS)


class GreenAirMission:
    def __init__(self, app, config, args):
        self.app = app
        self.cfg = config
        self.args = args
        self.root = Path(__file__).resolve().parent
        self.captures_dir = Path(
            os.environ.get("GREENAIR_CAPTURES")
            or config.get("captures_dir")
            or (self.root / "captures")
        ).expanduser().resolve()
        self.asset_dir = self.root / "assets"
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        self.running = True
        self.paused = False
        self.show_hud = bool(config.get("hud", {}).get("show", True)) and not args.no_hud
        self.last_wall = time.perf_counter()
        self.last_sim = None
        self.last_yaw = None
        self.sim_t = float(config["mission"].get("data_time_start", 0.0))
        self.start_t = self.sim_t
        self.end_t = float(config["mission"].get("data_time_end", 60.0))
        self.speed = float(config["mission"].get("speed", 1.0))
        self.loop = bool(config["mission"].get("loop", True)) and not args.no_loop
        self.hold = float(config["mission"].get("hold_at_end_s", 3.0))
        self._status_wall = time.perf_counter()
        self._status_t = None
        self._end_dwell = 0.0
        self._key_sub = None
        self._status_path = self.captures_dir / "status.json"
        self._status_path.parent.mkdir(parents=True, exist_ok=True)
        self.scenario_id = str(config.get("scenario", "industrial_fire"))
        self.scenario_label = SCENARIO_LABELS.get(
            self.scenario_id, self.scenario_id.replace("_", " ").upper()
        )
        self._frame_times = deque(maxlen=1200)
        self._status_write = 0.0
        self._source_x = 35.0
        self._cycle_index = 0

        self._configure_render()
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            raise RuntimeError("no USD stage")
        self.stage = stage

        self.builder = SceneBuilder(stage, self.asset_dir)
        self.scene, self.dynamic = self.builder.build()

        export_dir = Path(config["export_dir"])
        self.data = PlumeData(export_dir)
        traj_csv = config.get("trajectory_csv")
        self.trajectory = DroneTrajectory(traj_csv, loop=self.loop)
        self._source_x = 35.0
        self._move_source(self._source_center())

        self.plume = PlumeVisual(stage, self.data, config, self.asset_dir)
        self.plume.build()

        self.drone = DroneModel(stage, scale=float(config.get("drone", {}).get("scale", 1.0)))
        self.camera = CameraRig(stage)
        self.camera.set_mode(config.get("cameras", {}).get("start", "chase"))

        self.hud = None
        if self.show_hud:
            self.hud = HUD(
                stage, self.camera.path, FOCAL_MM, H_APERTURE, V_APERTURE, self.asset_dir
            )
        self.hud_visible = self.show_hud

        self.viewport = get_active_viewport()
        if self.viewport:
            self.viewport.camera_path = self.camera.path
            try:
                self.viewport.resolution = (int(self.cfg["window"]["width"]), int(self.cfg["window"]["height"]))
            except Exception:
                pass
        try:
            from omni.appwindow import get_default_app_window

            win = get_default_app_window()
            if win is not None:
                win.set_window_size(
                    int(self.cfg["window"]["width"]), int(self.cfg["window"]["height"])
                )
        except Exception:
            pass

        self._install_keys()
        self._apply(float(self.start_t), 1 / 60, snap=True)
        self._warmup()

    # ------------------------------------------------------------------ setup
    def _configure_render(self):
        try:
            s = carb.settings.get_settings()
            settings = {
                "/app/viewport/grid/enabled": False,
                "/app/viewport/axis/enabled": False,
                "/persistent/app/viewport/displayOptions": 0,
                "/rtx/shadows/enabled": True,
                "/rtx/ambientOcclusion/enabled": True,
                "/rtx/reflections/enabled": True,
                "/rtx/dlss/enabled": True,
                "/rtx/dlss/execMode": 1,
                "/rtx/post/tonemap/filmIso": 100.0,
                "/rtx/raytracing/fractionalCutoutOpacity": True,
                "/rtx/pathtracing/fractionalCutoutOpacity": True,
            }
            for k, v in settings.items():
                try:
                    s.set(k, v)
                except Exception:
                    pass
        except Exception as exc:
            print(f"[greenair] render settings warning: {exc}", flush=True)

    def _warmup(self):
        for _ in range(animation_frames := 45):
            self.app.update()
            time.sleep(0.01)
        print(f"[greenair] warmup {animation_frames} frames", flush=True)

    def _install_keys(self):
        try:
            import carb.input
            from omni.appwindow import get_default_app_window

            self._carb_input = carb.input
            self._input = carb.input.acquire_input_interface()
            self._keyboard = get_default_app_window().get_keyboard()
            self._key_sub = self._input.subscribe_to_keyboard_events(
                self._keyboard, self._on_key
            )
            print("[greenair] keyboard: 1 chase / 2 orbit / 3 ground / 4 top / C camera cycle / 5 scene cycle / 7-9 scenario / H hud / SPACE pause / R restart / ESC quit", flush=True)
        except Exception as exc:
            print(f"[greenair] keyboard unavailable: {exc}", flush=True)

    # ------------------------------------------------------------------- time
    def _advance_time(self):
        now = time.perf_counter()
        real_dt = min(max(now - self.last_wall, 0.0), 0.08)
        self.last_wall = now
        if self.paused:
            return 0.0
        dt = real_dt * self.speed
        if self.sim_t >= self.end_t:
            self._end_dwell += dt
            if self.loop and self._end_dwell >= self.hold:
                self._end_dwell = 0.0
                if bool(self.cfg["mission"].get("cycle_scenarios", False)):
                    self._cycle_next()
                else:
                    self.sim_t = self.start_t
                    self.last_sim = None
                    self.last_yaw = None
                    self.plume.last_color_t = None
            return 0.0
        self.sim_t = min(self.sim_t + dt, self.end_t)
        return dt

    def _display_t(self):
        return min(max(self.sim_t, self.start_t), self.end_t)

    def _apply(self, t, dt, snap=False):
        pos, yaw, speed = self.trajectory.at(t)
        yaw_rate = 0.0
        if self.last_yaw is not None and dt > 1e-5:
            dy = (yaw - self.last_yaw + 180.0) % 360.0 - 180.0
            yaw_rate = dy / dt
        self.last_yaw = yaw
        self.drone.update(pos, yaw, speed, dt=dt, yaw_rate=yaw_rate)
        self.camera.update(t, pos, yaw, dt=dt, snap=snap)
        if self.viewport is not None:
            try:
                from isaacsim.core.utils.viewports import set_camera_view

                set_camera_view(self.camera.eye, self.camera.target, self.camera.path, self.viewport)
            except Exception as exc:
                print(f"[greenair] camera view warning: {exc}", flush=True)
        self.plume.update(t, dt=dt, eye=self.camera.eye)
        sensor = self._sample_sensor(pos, t)
        state = {
            "t": t,
            "duration": self.end_t - self.start_t,
            "sensor": sensor,
            "drone_xyz": tuple(float(x) for x in pos),
            "camera": self.camera.mode,
            "speed": speed,
            "wind_ms": self._wind_speed(),
            "vmax_ug": self.data.max_ug("CO"),
            "scenario_id": self.scenario_id,
            "scenario_label": self.scenario_label,
        }
        if self.hud and self.hud_visible:
            self.hud.render(state, force=snap)
        self._flicker_fire(t)
        self._status(t, pos, sensor)

    def _wind_speed(self):
        try:
            return float(self.data.meta.get("wind", {}).get("speed_m_s", 10.0))
        except Exception:
            return 10.0

    def _source_center(self):
        try:
            pts = np.asarray(self.data.source_box, dtype=np.float64).reshape(-1, 3)
            return float((pts[:, 0].min() + pts[:, 0].max()) * 0.5)
        except Exception:
            return 35.0

    def _move_source(self, target_x):
        delta = float(target_x) - float(self._source_x)
        if abs(delta) < 1e-6:
            self._source_x = float(target_x)
            return
        root = self.stage.GetPrimAtPath("/World/Source")
        if root:
            for prim in root.GetChildren():
                try:
                    xf = UsdGeom.Xformable(prim)
                    if not xf:
                        continue
                    for op in xf.GetOrderedXformOps():
                        if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                            v = op.Get()
                            if v is not None:
                                op.Set(Gf.Vec3d(v[0] + delta, v[1], v[2]))
                except Exception:
                    continue
        self._source_x = float(target_x)

    def _poll_command(self):
        path = self.captures_dir / "switch_scenario.txt"
        try:
            if not path.exists():
                return
            sid = path.read_text(encoding="utf-8").strip()
            if not sid or sid == self.scenario_id:
                return
            if self.switch_scenario(sid):
                path.write_text(self.scenario_id, encoding="utf-8")
        except OSError:
            pass

    def switch_scenario(self, sid):
        if sid not in SCENARIO_LABELS:
            return False
        if sid != self.scenario_id:
            root = Path(self.cfg.get("data_root") or (self.root.parent / "data"))
            export = root / sid / "export"
            csv_path = root / sid / "drone_measurements.csv"
            if not (export / "metadata.json").exists():
                print(f"[greenair] scenario missing: {sid}", flush=True)
                return False
            try:
                data = PlumeData(export)
                traj = DroneTrajectory(str(csv_path), loop=self.loop)
                self.plume.set_data(data)
            except Exception as exc:
                print(f"[greenair] scenario switch failed: {exc}", flush=True)
                return False
            self.data = data
            self.trajectory = traj
            self.scenario_id = sid
            self.scenario_label = SCENARIO_LABELS[sid]
            self.cfg["scenario"] = sid
            self.cfg["export_dir"] = str(export)
            self.cfg["trajectory_csv"] = str(csv_path)
            self._move_source(self._source_center())
            print(f"[greenair] scenario -> {sid}", flush=True)
        self.sim_t = self.start_t
        self._end_dwell = 0.0
        self.last_sim = None
        self.last_yaw = None
        self.paused = False
        self.plume.last_color_t = None
        self._status_wall = 0.0
        self._status_write = 0.0
        try:
            path = self.captures_dir / "switch_scenario.txt"
            path.write_text(self.scenario_id, encoding="utf-8")
        except OSError:
            pass
        return True

    def _cycle_next(self):
        ids = [s[0] for s in SCENARIOS]
        try:
            idx = ids.index(self.scenario_id)
        except ValueError:
            idx = -1
        nxt = ids[(idx + 1) % len(ids)]
        if not self.switch_scenario(nxt):
            self.sim_t = self.start_t
            self.last_sim = None
            self.last_yaw = None
            self.plume.last_color_t = None

    def _sample_sensor(self, pos, t):
        values, valid = self.data.sample([pos], t, SENSOR_SPECIES)
        out = {}
        flags = []
        for s in SENSOR_SPECIES:
            kg = float(values.get(s, np.zeros(1))[0])
            if 0.0 < kg < NOISE_FLOOR:
                flags.append(f"{s}:noise-floor")
                kg = 0.0
            out[s] = kg * 1e9
        available = bool(valid[0]) and (self.start_t - 1e-9 <= t <= self.end_t + 1e-9)
        return {
            "available": available,
            "values": out,
            "flags": flags,
        }

    def _flicker_fire(self, t):
        light = self.dynamic.get("fire_light")
        if light:
            try:
                prim = self.stage.GetPrimAtPath(light)
                from pxr import UsdLux

                attr = UsdLux.SphereLight(prim).GetIntensityAttr()
                base = 9000.0 * (1.0 + 0.10 * math.sin(t * 13.1) + 0.06 * math.sin(t * 31.7 + 1.3))
                attr.Set(base)
            except Exception:
                pass
        for i, path in enumerate(self.dynamic.get("flames", [])):
            prim = self.stage.GetPrimAtPath(path)
            if not prim:
                continue
            x = UsdGeom.Xformable(prim)
            scale = 1.0 + 0.12 * math.sin(t * (7.3 + i * 1.7) + i * 1.9)
            op = x.GetScaleOp()
            if op:
                op.Set(Gf.Vec3f(scale, scale, 0.85 + 0.2 * scale))

    def _avg_fps(self, now, window):
        if not self._frame_times:
            return 0.0
        cutoff = now - window
        n = 0
        oldest = now
        for ts in reversed(self._frame_times):
            if ts < cutoff:
                break
            n += 1
            oldest = ts
        span = max(now - max(oldest, cutoff), 1e-3)
        return min(n / span, 240.0)

    def _write_status(self, t, fps):
        payload = {
            "wall_time": time.time(),
            "sim_time": round(float(t), 3),
            "fps": round(float(fps), 2),
            "frame_ms": round(1000.0 / max(fps, 1e-3), 2),
            "paused": bool(self.paused),
            "camera": self.camera.mode,
            "scenario": self.scenario_id,
            "scenario_label": self.scenario_label,
        }
        try:
            tmp = self._status_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            tmp.replace(self._status_path)
        except OSError:
            pass

    def _status(self, t, pos, sensor):
        now = time.perf_counter()
        self._frame_times.append(now)
        if now - self._status_write >= 1.0:
            self._status_write = now
            self._write_status(t, self._avg_fps(now, 3.0))
        if now - self._status_wall < 5.0:
            return
        self._status_wall = now
        fps = self._avg_fps(now, 5.0)
        co = sensor["values"].get("CO", 0.0) if sensor["available"] else None
        print(
            f"[greenair] t={t:5.1f}s pos=({pos[0]:5.1f},{pos[1]:5.1f},{pos[2]:4.1f}) "
            f"CO={co if co is not None else '--'} ug/m3 cam={self.camera.mode} "
            f"fps_avg={fps:4.1f} scenario={self.scenario_id}",
            flush=True,
        )

    # ------------------------------------------------------------------- loop
    def run(self):
        while self.running:
            if hasattr(self.app, "is_running") and not self.app.is_running():
                break
            dt = self._advance_time()
            t = self._display_t()
            self._apply(t, dt if dt > 0 else 1 / 60)
            self.app.update()
            self._poll_command()
            if self.args.exit_after and time.perf_counter() - self._t0 > self.args.exit_after:
                break
        self.close()

    def capture_stills(self, times, out_dir):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        vp = get_active_viewport()
        for t in times:
            self.sim_t = float(t)
            self.camera.initialized = False
            self._apply(float(t), 1 / 60, snap=True)
            try:
                world = self.camera.cam.ComputeLocalToWorldTransform(0)
                print(
                    f"[greenair] camera eye={tuple(round(v,2) for v in self.camera.eye)} "
                    f"target={tuple(round(v,2) for v in self.camera.target)} "
                    f"world={tuple(round(v,2) for v in world.ExtractTranslation())} "
                    f"viewport={self.viewport.camera_path if self.viewport else None}",
                    flush=True,
                )
            except Exception as exc:
                print(f"[greenair] camera debug: {exc}", flush=True)
            for _ in range(8):
                self.app.update()
                time.sleep(0.015)
            path = out_dir / f"still_{int(t):03d}s.png"
            capture_viewport_to_file(vp, file_path=str(path), is_hdr=False)
            for _ in range(25):
                self.app.update()
                time.sleep(0.01)
            print(f"[greenair] captured {path} ({path.stat().st_size if path.exists() else 0} bytes)", flush=True)

    def start_clock(self):
        self._t0 = time.perf_counter()
        self.last_wall = time.perf_counter()

    # ------------------------------------------------------------------- input
    def _on_key(self, event):
        try:
            if event.type != self._carb_input.KeyboardEventType.KEY_PRESS:
                return True
            key = event.input
            K = self._carb_input.KeyboardInput
            digit = int(str(key).split("_")[-1]) if str(key).split("_")[-1].isdigit() else None
            if digit in (1, 2, 3, 4):
                self.camera.set_mode(("chase", "orbit", "ground", "top")[digit - 1])
            elif key == K.C:
                self.camera.cycle()
            elif digit in (7, 8, 9):
                idx = digit - 7
                if 0 <= idx < len(SCENARIOS):
                    self.switch_scenario(SCENARIOS[idx][0])
            elif key in (K.KEY_5, K.NUMPAD_5):
                self._cycle_next()
            elif key == K.H:
                self.hud_visible = not self.hud_visible
                prim = self.stage.GetPrimAtPath(f"{self.camera.path}/HUD")
                if prim:
                    imageable = UsdGeom.Imageable(prim)
                    imageable.MakeVisible() if self.hud_visible else imageable.MakeInvisible()
            elif key == K.SPACE:
                self.paused = not self.paused
            elif key == K.R:
                self.sim_t = self.start_t
                self.last_yaw = None
                self.plume.last_color_t = None
            elif key in (K.ESCAPE, K.Q):
                self.running = False
            return True
        except Exception as exc:
            if not getattr(self, "_key_error_logged", False):
                self._key_error_logged = True
                print(f"[greenair] key handler error: {exc!r}", flush=True)
            return True

    def close(self):
        try:
            if self._key_sub is not None:
                self._input.unsubscribe_to_keyboard_events(self._keyboard, self._key_sub)
        except Exception:
            pass
        try:
            self.app.close()
        except Exception:
            pass







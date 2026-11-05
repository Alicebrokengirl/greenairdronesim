"""Screen-space HUD rendered as camera-attached geometry.

This is deliberately geometry rather than an omni.ui window: the overlay is
then part of the render, so viewport captures and movie output include it.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pxr import Gf, Sdf, UsdGeom, UsdShade

from plume_data import color_for_norm, linear_to_srgb

W, H = 1280, 720
HUD_SCALE = 2
HUD_KEEP = 24
FONT_DIR = Path(os.environ.get("WINDIR") or os.environ.get("SystemRoot") or r"C:\Windows") / "Fonts"


def _font(name, size):
    for candidate in (name, "segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(str(FONT_DIR / candidate), size)
        except Exception:
            continue
    return ImageFont.load_default()


class _ScaledDraw:
    """Proxy that maps the 1280x720 layout onto a supersampled canvas."""

    def __init__(self, draw, k):
        self._d = draw
        self._k = k

    def _pts(self, pts):
        k = self._k
        return [(float(x) * k, float(y) * k) for x, y in pts]

    def _box(self, box):
        k = self._k
        return [float(v) * k for v in box]

    def _kw(self, kw):
        if kw.get("width") is not None:
            kw["width"] = max(1, int(round(float(kw["width"]) * self._k)))
        if kw.get("radius") is not None:
            kw["radius"] = float(kw["radius"]) * self._k
        return kw

    def line(self, pts, **kw):
        self._d.line(self._pts(pts), **self._kw(kw))

    def text(self, pos, text, **kw):
        self._d.text((float(pos[0]) * self._k, float(pos[1]) * self._k), text, **self._kw(kw))

    def rectangle(self, box, **kw):
        self._d.rectangle(self._box(box), **self._kw(kw))

    def rounded_rectangle(self, box, **kw):
        self._d.rounded_rectangle(self._box(box), **self._kw(kw))

    def ellipse(self, box, **kw):
        self._d.ellipse(self._box(box), **self._kw(kw))

    def polygon(self, pts, **kw):
        self._d.polygon(self._pts(pts), **self._kw(kw))


class HUD:
    def __init__(self, stage, camera_path, focal_mm, h_aperture, v_aperture, asset_dir):
        self.stage = stage
        self.asset_dir = Path(asset_dir)
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        k = HUD_SCALE
        self.font_title = _font("segoeuib.ttf", 34 * k)
        self.font_sub = _font("consola.ttf", 16 * k)
        self.font_label = _font("consola.ttf", 15 * k)
        self.font_value = _font("consolab.ttf", 31 * k)
        self.font_small = _font("consola.ttf", 13 * k)
        self.font_big = _font("bahnschrift.ttf", 22 * k)
        self.gen = 0
        self.last_draw = -1e9
        self.tex = None
        self._build(camera_path, focal_mm, h_aperture, v_aperture)

    def _build(self, camera_path, focal_mm, h_aperture, v_aperture):
        half_w = math.tan(math.atan(h_aperture * 0.5 / focal_mm)) * 1.0
        half_h = math.tan(math.atan(v_aperture * 0.5 / focal_mm)) * 1.0
        half_w *= 1.002
        half_h *= 1.002

        anchor = UsdGeom.Xform.Define(self.stage, f"{camera_path}/HUD")
        ax = UsdGeom.Xformable(anchor.GetPrim())
        ax.AddTranslateOp().Set(Gf.Vec3d(0, 0, -1.0))
        ax.AddScaleOp().Set(Gf.Vec3f(half_w, half_h, 1.0))

        mesh = UsdGeom.Mesh.Define(self.stage, f"{camera_path}/HUD/Quad")
        mesh.CreatePointsAttr(
            [
                Gf.Vec3f(-1, -1, 0),
                Gf.Vec3f(1, -1, 0),
                Gf.Vec3f(1, 1, 0),
                Gf.Vec3f(-1, 1, 0),
            ]
        )
        mesh.CreateFaceVertexCountsAttr([4])
        mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
        mesh.CreateNormalsAttr([Gf.Vec3f(0, 0, 1)] * 4)
        mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
        mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
        mesh.CreateDoubleSidedAttr(True)
        st = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar(
            "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex
        )
        st.Set([Gf.Vec2f(0, 0), Gf.Vec2f(1, 0), Gf.Vec2f(1, 1), Gf.Vec2f(0, 1)])

        mat = UsdShade.Material.Define(self.stage, "/World/HUDLooks/HUD")
        sh = UsdShade.Shader.Define(self.stage, "/World/HUDLooks/HUD/Shader")
        sh.CreateIdAttr("UsdPreviewSurface")
        sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0, 0, 0))
        sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1.0)
        sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
        sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(1.0)

        reader = UsdShade.Shader.Define(self.stage, "/World/HUDLooks/HUD/stReader")
        reader.CreateIdAttr("UsdPrimvarReader_float2")
        reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)

        tex = UsdShade.Shader.Define(self.stage, "/World/HUDLooks/HUD/Texture")
        tex.CreateIdAttr("UsdUVTexture")
        tex.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("clamp")
        tex.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("clamp")
        tex.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("sRGB")
        tex.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
        tex.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        tex.CreateOutput("a", Sdf.ValueTypeNames.Float)
        sh.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
            tex.ConnectableAPI(), "rgb"
        )
        sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).ConnectToSource(tex.ConnectableAPI(), "a")
        mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(mat)
        self.tex = tex

        img = Image.new("RGBA", (W * HUD_SCALE, H * HUD_SCALE), (0, 0, 0, 0))
        self._publish(img)

    def _publish(self, img):
        if img.size != (W, H):
            img = img.resize((W, H), Image.LANCZOS)
        self.gen += 1
        path = self.asset_dir / f"hud_live_{self.gen:06d}.png"
        img.save(path, compress_level=1)
        self.tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(path.as_posix())
        if self.gen % 8 == 0:
            keep = sorted(
                self.asset_dir.glob("hud_live_*.png"), key=lambda p: p.stat().st_mtime
            )[:-HUD_KEEP]
            for old in keep:
                try:
                    old.unlink()
                except OSError:
                    pass

    def _draw_blank(self, d):
        c = (170, 225, 235, 120)
        for x, y, dx, dy in (
            (24, 24, 1, 1), (W - 24, 24, -1, 1), (24, H - 24, 1, -1), (W - 24, H - 24, -1, -1)
        ):
            d.line([(x, y), (x + dx * 30, y)], fill=c, width=2)
            d.line([(x, y), (x, y + dy * 30)], fill=c, width=2)

    def render(self, state, force=False):
        t = float(state.get("t", 0.0))
        if t + 1e-6 < self.last_draw:
            self.last_draw = -1e9
        if not force and (t - self.last_draw) < 0.3:
            return
        self.last_draw = t
        img = Image.new("RGBA", (W * HUD_SCALE, H * HUD_SCALE), (0, 0, 0, 0))
        d = _ScaledDraw(ImageDraw.Draw(img), HUD_SCALE)
        self._draw_blank(d)
        self._top_left(d, state)
        self._top_right(d, state)
        self._legend(d, state)
        self._bottom_right(d, state)
        self._center(d)
        self._publish(img)

    # ---------------------------------------------------------------- pieces
    def _panel(self, d, box, fill=(7, 12, 18, 170), outline=(94, 198, 214, 95)):
        d.rounded_rectangle(box, radius=10, fill=fill, outline=outline, width=1)

    def _top_left(self, d, state):
        label = str(state.get("scenario_label", "INDUSTRIAL FIRE")).upper()
        self._panel(d, (28, 30, 520, 124))
        d.rectangle((28, 30, 34, 124), fill=(52, 214, 196, 235))
        d.text((50, 40), "GREENAIRDRONE", font=self.font_title, fill=(232, 246, 246, 245))
        d.text(
            (51, 82),
            f"{label}  /  ISAAC SIM 5.1",
            font=self.font_sub,
            fill=(96, 220, 206, 240),
        )
        d.text(
            (51, 103),
            "OpenFOAM passive-scalar model - not measured data",
            font=self.font_small,
            fill=(166, 182, 188, 225),
        )

    def _top_right(self, d, state):
        self._panel(d, (W - 390, 30, W - 28, 190))
        d.text((W - 372, 42), "DRONE VIRTUAL SENSOR", font=self.font_label, fill=(146, 196, 210, 240))
        sensor = state.get("sensor", {})
        valid = sensor.get("available", False)
        rows = [("CO", "CO"), ("PM2.5", "PM25"), ("SO2", "SO2")]
        y = 70
        for label, key in rows:
            d.text((W - 372, y + 7), label, font=self.font_label, fill=(190, 204, 208, 240))
            val = sensor.get("values", {}).get(key) if valid else None
            if val is None:
                txt = "---"
                col = (150, 160, 165, 220)
            else:
                txt = self._fmt(val)
                col = (245, 249, 246, 250)
            d.text((W - 250, y), txt, font=self.font_value, fill=col)
            d.text((W - 66, y + 9), "ug/m3", font=self.font_small, fill=(125, 188, 198, 230))
            y += 38
        d.text(
            (W - 372, 166),
            f"position  {state.get('drone_xyz', (0,0,0))[0]:5.1f}  {state.get('drone_xyz', (0,0,0))[1]:5.1f}  {state.get('drone_xyz', (0,0,0))[2]:5.1f} m",
            font=self.font_small,
            fill=(152, 170, 176, 230),
        )

    def _legend(self, d, state):
        box = (28, H - 320, 300, H - 30)
        self._panel(d, box)
        d.text((46, H - 306), "CO CONCENTRATION", font=self.font_label, fill=(150, 205, 214, 240))
        d.text((46, H - 286), "vertical plume slice / log scale", font=self.font_small, fill=(140, 158, 166, 220))
        x0, y0, x1, y1 = 46, H - 262, 82, H - 92
        steps = y1 - y0
        for i in range(steps):
            c = color_for_norm(1.0 - i / max(steps - 1, 1))
            rgb = np.clip(linear_to_srgb(c) * 255, 0, 255).astype(int)
            d.line([(x0, y0 + i), (x1, y0 + i)], fill=(int(rgb[0]), int(rgb[1]), int(rgb[2]), 245))
        d.rectangle((x0, y0, x1, y1), outline=(190, 210, 214, 130), width=1)
        vmin = 10.0
        vmax = max(float(state.get("vmax_ug", 10000.0)), 1000.0)
        ticks = [10, 100, 1000, 10000]
        ticks = [v for v in ticks if v <= vmax * 1.15]
        if vmax not in ticks:
            ticks.append(vmax)
        for v in ticks:
            frac = (math.log10(v) - math.log10(vmin)) / max(math.log10(vmax) - math.log10(vmin), 1e-9)
            yy = y1 - frac * (y1 - y0)
            d.line([(x1, yy), (x1 + 6, yy)], fill=(200, 218, 220, 180), width=1)
            label = f"{v:,.0f}" if v < 10000 else f"{v/1000:,.0f}k"
            d.text((x1 + 12, yy - 8), label, font=self.font_small, fill=(196, 210, 214, 235))
        d.text((46, H - 82), "ug/m3   field maximum", font=self.font_small, fill=(140, 160, 166, 220))
        d.text((46, H - 62), f"{vmax:,.0f}", font=self.font_big, fill=(238, 244, 242, 245))
        d.text((46, H - 42), "COLOR = log10(CO), 10 ug/m3 floor", font=self.font_small, fill=(140, 160, 166, 215))

    def _bottom_right(self, d, state):
        self._panel(d, (W - 390, H - 178, W - 28, H - 30))
        t = float(state.get("t", 0.0))
        dur = max(float(state.get("duration", 60.0)), 1e-6)
        frac = min(max(t / dur, 0.0), 1.0)
        d.text((W - 372, H - 164), "MISSION TIME", font=self.font_label, fill=(146, 196, 210, 240))
        mm = int(t // 60)
        ss = int(t % 60)
        d.text((W - 372, H - 142), f"T+ {mm:02d}:{ss:02d}", font=self.font_big, fill=(238, 244, 242, 245))
        d.text((W - 240, H - 140), f"/ {int(dur//60):02d}:{int(dur%60):02d}", font=self.font_small, fill=(150, 170, 176, 230))
        bx0, bx1 = W - 372, W - 48
        d.rectangle((bx0, H - 112, bx1, H - 107), fill=(40, 52, 58, 220))
        d.rectangle((bx0, H - 112, bx0 + (bx1 - bx0) * frac, H - 107), fill=(52, 214, 196, 240))
        cam = str(state.get("camera", "chase")).upper()
        spd = float(state.get("speed", 0.0))
        d.text((W - 372, H - 96), f"CAM  {cam}", font=self.font_label, fill=(196, 211, 214, 240))
        d.text((W - 210, H - 96), f"SPD  {spd:4.1f} m/s", font=self.font_label, fill=(196, 211, 214, 240))
        d.text((W - 372, H - 72), f"WIND  {state.get('wind_ms', 5.0):.1f} m/s  ->", font=self.font_small, fill=(146, 166, 172, 230))
        sid = str(state.get("scenario_id", "industrial_fire")).replace("_", " ").upper()
        d.text((W - 372, H - 52), f"SCENARIO  {sid}", font=self.font_small, fill=(146, 166, 172, 230))
        d.ellipse((W - 78, H - 62, W - 64, H - 48), fill=(236, 70, 46, 235))
        d.text((W - 56, H - 62), "SIM", font=self.font_small, fill=(236, 220, 214, 240))

    def _center(self, d):
        c = (210, 235, 238, 95)
        d.line([(W // 2 - 12, H // 2), (W // 2 - 4, H // 2)], fill=c, width=1)
        d.line([(W // 2 + 4, H // 2), (W // 2 + 12, H // 2)], fill=c, width=1)
        d.line([(W // 2, H // 2 - 12), (W // 2, H // 2 - 4)], fill=c, width=1)
        d.line([(W // 2, H // 2 + 4), (W // 2, H // 2 + 12)], fill=c, width=1)

    @staticmethod
    def _fmt(v):
        if v is None:
            return "---"
        if abs(v) >= 10000:
            return f"{v:,.0f}"
        if abs(v) >= 100:
            return f"{v:,.1f}"
        return f"{v:,.2f}"

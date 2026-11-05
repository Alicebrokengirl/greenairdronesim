"""Volume-like plume visualisation built from the Eulerian concentration field."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from pxr import Gf, Sdf, UsdGeom, UsdShade, Vt


class PlumeVisual:
    def __init__(self, stage, data, config, asset_dir):
        self.stage = stage
        self.data = data
        self.config = config
        self.asset_dir = Path(asset_dir)
        self.positions = None
        self.last_color_t = None
        self.embers = None
        self.ember_vel = None
        self.ember_rng = np.random.default_rng(23)
        self.billboard_eye = None
        self.bins = 20
        self.emissive_scale = float(self.config["plume"].get("emissive_scale", 0.08))
        self.sprite_tag = f"_e{int(self.emissive_scale * 1000)}_s20"

    # ------------------------------------------------------------ sprite sheet
    @staticmethod
    def _fbm(size, seed, octaves=4):
        """Cheap fractal value noise in 0..1, used to break up sprite discs."""
        from PIL import Image

        rng = np.random.default_rng(seed)
        acc = np.zeros((size, size), dtype=np.float64)
        amp = 0.5
        total = 0.0
        for o in range(octaves):
            n = 2 ** (o + 1)
            g = (rng.random((n, n)) * 255.0).astype(np.uint8)
            up = Image.fromarray(g).resize((size, size), Image.BICUBIC)
            acc += amp * np.asarray(up, dtype=np.float64) / 255.0
            total += amp
            amp *= 0.5
        acc /= total
        lo, hi = float(acc.min()), float(acc.max())
        return (acc - lo) / max(hi - lo, 1e-9)

    def _sprite_texture(self, bin_index, variant, rgb_linear, alpha_scale, size=128, softness=1.0):
        """Write (once) a soft radial RGBA sprite tinted for one colour bin."""
        from PIL import Image
        from plume_data import linear_to_srgb

        path = self.asset_dir / f"sprite_b{bin_index:02d}_v{variant}{self.sprite_tag}.png"
        emit_path = self.asset_dir / f"sprite_e{bin_index:02d}_v{variant}{self.sprite_tag}.png"
        if path.exists() and emit_path.exists():
            return path, emit_path
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        yy, xx = np.mgrid[0:size, 0:size]
        c = (size - 1) / 2.0
        r2 = ((xx - c) ** 2 + (yy - c) ** 2) / (size / 2.0) ** 2
        sigma2 = 0.20
        alpha = np.exp(-r2 / sigma2)
        floor = math.exp(-1.0 / sigma2)
        alpha = np.clip((alpha - floor) / (1.0 - floor), 0.0, 1.0) ** softness
        noise = self._fbm(size, seed=bin_index * 101 + variant * 17 + 3)
        alpha = alpha * (0.30 + 0.70 * noise)
        alpha = np.clip(alpha * float(alpha_scale), 0.0, 1.0)
        rgb = np.asarray(rgb_linear, dtype=np.float64)
        srgb = np.clip(linear_to_srgb(rgb), 0.0, 1.0)
        rgba = np.zeros((size, size, 4), dtype=np.uint8)
        rgba[..., 0] = int(round(srgb[0] * 255.0))
        rgba[..., 1] = int(round(srgb[1] * 255.0))
        rgba[..., 2] = int(round(srgb[2] * 255.0))
        rgba[..., 3] = (alpha * 255.0).astype(np.uint8)
        Image.fromarray(rgba, "RGBA").save(path)

        # A dim version of the same colour, reused as an emissive tint so the
        # plume stays legible even under low scene light. Alpha is irrelevant
        # here because the surface only shows where the diffuse alpha is > 0.
        rgb_srgb_tex = np.clip(linear_to_srgb(rgb * self.emissive_scale), 0.0, 1.0)
        emit = np.zeros((size, size, 4), dtype=np.uint8)
        emit[..., 0] = int(round(rgb_srgb_tex[0] * 255.0))
        emit[..., 1] = int(round(rgb_srgb_tex[1] * 255.0))
        emit[..., 2] = int(round(rgb_srgb_tex[2] * 255.0))
        emit[..., 3] = 255
        Image.fromarray(emit, "RGBA").save(emit_path)
        return path, emit_path

    def _texture_reader(self, path, name):
        tex = UsdShade.Shader.Define(self.stage, path)
        tex.CreateIdAttr("UsdUVTexture")
        tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(str(name).replace("\\", "/"))
        tex.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("sRGB")
        tex.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("clamp")
        tex.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("clamp")
        st = UsdShade.Shader.Define(self.stage, path + "/ST")
        st.CreateIdAttr("UsdPrimvarReader_float2")
        st.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        tex.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(
            st.CreateOutput("result", Sdf.ValueTypeNames.Float2)
        )
        return tex

    def _sprite_material(self, name, texture_path, emit_texture_path):
        path = f"/World/PlumeLooks/{name}"
        mat = UsdShade.Material.Define(self.stage, path)
        sh = UsdShade.Shader.Define(self.stage, path + "/Shader")
        sh.CreateIdAttr("UsdPreviewSurface")
        sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1.0)
        sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
        sh.CreateInput("specularColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.0))
        tex = self._texture_reader(path + "/Tex", texture_path)
        sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
            tex.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        )
        sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).ConnectToSource(
            tex.CreateOutput("a", Sdf.ValueTypeNames.Float)
        )
        emit = self._texture_reader(path + "/Emit", emit_texture_path)
        sh.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
            emit.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        )
        mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
        return mat

    # ----------------------------------------------------------- sprite disc
    @staticmethod
    def _disc_geometry(segments=48):
        points = [Gf.Vec3f(0.0, 0.0, 0.0)]
        sts = [Gf.Vec2f(0.5, 0.5)]
        for s in range(segments):
            a = 2.0 * math.pi * s / segments
            x = math.cos(a)
            y = math.sin(a)
            points.append(Gf.Vec3f(x, y, 0.0))
            sts.append(Gf.Vec2f(0.5 + 0.5 * x, 0.5 + 0.5 * y))
        counts = [3] * segments
        indices = []
        for s in range(segments):
            n = (s + 1) % segments
            indices.extend([0, 1 + s, 1 + n])
        return points, sts, counts, indices

    def _make_disc_proto(self, path, mat):
        mesh = UsdGeom.Mesh.Define(self.stage, path)
        points, sts, counts, indices = self._disc_geometry()
        mesh.CreatePointsAttr(points)
        mesh.CreateFaceVertexCountsAttr(counts)
        mesh.CreateFaceVertexIndicesAttr(indices)
        mesh.CreateDoubleSidedAttr(True)
        mesh.CreateNormalsAttr([Gf.Vec3f(0.0, 0.0, 1.0)] * len(points))
        mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
        st_attr = UsdGeom.PrimvarsAPI(mesh.GetPrim()).CreatePrimvar(
            "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex
        )
        st_attr.Set(Vt.Vec2fArray(sts))
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(mat)
        return mesh

    def build(self):
        cfg = self.config["plume"]
        species = cfg.get("color_species", "CO")
        count = int(cfg.get("particles", 18000))
        sample_t = float(cfg.get("sample_time_s", 30.0))
        self.positions = self.data.generate_particles(
            count=count,
            t=sample_t,
            threshold_fraction=float(cfg.get("threshold_fraction", 0.002)),
            gamma=float(cfg.get("gamma", 0.45)),
            seed=int(cfg.get("seed", 7)),
            weight_species=tuple(cfg.get("weight_species", ["CO", "PM25", "SO2"])),
        )
        self.count = self.positions.shape[0]
        self.species = species

        # Each particle is a single camera-facing sprite whose RGB encodes the
        # local concentration and whose alpha carries a soft radial falloff.
        # Texture alpha is the one per-texel transparency path RTX honours for
        # instanced prototypes, so one sprite per particle beats stacking discs.
        from plume_data import color_for_norm

        alpha_min = float(cfg.get("opacity_min", 0.06))
        alpha_max = float(cfg.get("opacity_max", 0.35))
        self.variants = int(cfg.get("sprite_variants", 6))
        rng = np.random.default_rng(int(cfg.get("seed", 7)) + 991)
        self.variant_of = rng.integers(0, self.variants, size=self.count).astype(np.int32)
        proto_paths = []
        for i in range(self.bins):
            frac = (i + 0.5) / self.bins
            rgb = color_for_norm(frac)
            amp = alpha_min + (alpha_max - alpha_min) * frac ** 0.8
            for v in range(self.variants):
                tex, emit = self._sprite_texture(i, v, rgb, amp)
                mat = self._sprite_material(f"SpriteB{i:02d}V{v}", tex, emit)
                path = f"/World/Plume/Proto{i}_{v}"
                self._make_disc_proto(path, mat)
                proto_paths.append(path)

        pos = Vt.Vec3fArray.FromNumpy(np.ascontiguousarray(self.positions, dtype=np.float32))
        identity = Vt.QuathArray([Gf.Quath(1.0, 0.0, 0.0, 0.0)] * self.count)
        self.instancer = UsdGeom.PointInstancer.Define(self.stage, "/World/Plume/Instancer")
        self.instancer.CreatePrototypesRel().SetTargets(proto_paths)
        self.instancer.CreateProtoIndicesAttr(Vt.IntArray([0] * self.count))
        self.instancer.CreatePositionsAttr(pos)
        self.instancer.CreateScalesAttr(Vt.Vec3fArray([Gf.Vec3f(0.01)] * self.count))
        self.instancer.CreateOrientationsAttr(identity)

        # embers give the source motion and a warm focal point
        n_embers = int(cfg.get("embers", 500))
        self.embers = self._seed_embers(n_embers)
        self.ember_vel = np.zeros_like(self.embers)
        ember_mat = self._solid_material(
            "Ember", (1.0, 0.36, 0.04), opacity=0.95, emissive=(1.0, 0.24, 0.02)
        )
        eproto = UsdGeom.Sphere.Define(self.stage, "/World/Plume/EmberProto")
        eproto.CreateRadiusAttr(0.09)
        UsdShade.MaterialBindingAPI.Apply(eproto.GetPrim()).Bind(ember_mat)
        ei = UsdGeom.PointInstancer.Define(self.stage, "/World/Plume/Embers")
        ei.CreatePrototypesRel().AddTarget("/World/Plume/EmberProto")
        ei.CreateProtoIndicesAttr(Vt.IntArray([0] * n_embers))
        ei.CreatePositionsAttr(
            Vt.Vec3fArray.FromNumpy(np.ascontiguousarray(self.embers, dtype=np.float32))
        )
        ei.GetScalesAttr().Set(Vt.Vec3fArray([Gf.Vec3f(1)] * n_embers))
        self.ember_instancer = ei
        self._update_instancer(float(self.config["mission"].get("start_time_s", 0.0)))

    def _solid_material(self, name, color, opacity=1.0, emissive=None, rough=0.9):
        path = f"/World/PlumeLooks/{name}"
        mat = UsdShade.Material.Define(self.stage, path)
        sh = UsdShade.Shader.Define(self.stage, path + "/Shader")
        sh.CreateIdAttr("UsdPreviewSurface")
        sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
        sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(rough)
        sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
        sh.CreateInput("specularColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.0))
        sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(opacity)
        if emissive:
            sh.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*emissive))
        mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
        return mat

    def _source_bounds(self):
        src = self.data.source_box
        if src is None:
            return np.array([30.0, -6.0, 0.0]), np.array([40.0, 6.0, 10.0])
        box = np.asarray(src, dtype=np.float64).reshape(-1)
        if box.size == 6:
            return box[:3], box[3:]
        pts = np.asarray(src, dtype=np.float64).reshape(-1, 3)
        return pts.min(axis=0), pts.max(axis=0)

    def _seed_embers(self, count):
        lo, hi = self._source_bounds()
        n = int(count)
        rng = self.ember_rng
        return np.column_stack(
            [
                rng.uniform(lo[0] + 1.0, hi[0] - 1.0, n),
                rng.uniform(lo[1] + 1.0, hi[1] - 1.0, n),
                rng.uniform(lo[2] + 3.0, hi[2] + 1.0, n),
            ]
        )

    def _reset_embers(self):
        self.embers = self._seed_embers(len(self.embers))

    def _orient_billboards(self, eye):
        if eye is None or self.positions is None:
            return
        eye = np.asarray(eye, dtype=np.float32).reshape(1, 3)
        d = eye - self.positions.astype(np.float32)
        n = np.maximum(np.linalg.norm(d, axis=1), 1e-6)
        z = d / n[:, None]
        dot = np.clip(z[:, 2], -1.0, 1.0)
        axis = np.column_stack(
            (-z[:, 1], z[:, 0], np.zeros(z.shape[0], dtype=np.float32))
        )
        denom = np.sqrt(np.maximum(2.0 * (1.0 + dot), 1e-8))
        qw = np.sqrt(np.maximum(0.5 * (1.0 + dot), 0.0))
        qx = axis[:, 0] / denom
        qy = axis[:, 1] / denom
        qz = np.zeros(z.shape[0], dtype=np.float32)
        flip = dot <= -0.9999
        if flip.any():
            qw[flip] = 0.0
            qx[flip] = 1.0
            qy[flip] = 0.0
        # Vt.QuathArray.FromNumpy expects columns ordered (i, j, k, real);
        # building the array in NumPy avoids a ~90k-element Python loop per frame.
        qnp = np.empty((z.shape[0], 4), dtype=np.float16)
        qnp[:, 0] = qx
        qnp[:, 1] = qy
        qnp[:, 2] = qz
        qnp[:, 3] = qw
        quats = Vt.QuathArray.FromNumpy(qnp)
        attr = self.instancer.GetOrientationsAttr()
        if attr:
            attr.Set(quats)

    def update(self, t, dt=0.0, eye=None):
        if self.positions is None:
            return
        dt = max(0.0, min(float(dt), 0.2))
        # embers rise, drift with the wind and wrap back into the fire
        if dt > 0:
            v = self.ember_vel
            v[:, 2] += dt * 1.4
            v[:, 0] += dt * (1.1 + 0.25 * np.sin(t * 1.7 + self.embers[:, 1] * 0.2))
            v[:, 1] += dt * 0.28 * np.sin(t * 1.1 + self.embers[:, 0] * 0.15)
            v *= 1.0 - 0.9 * dt
            self.embers += v * dt
            dead = (
                (self.embers[:, 2] > 26)
                | (self.embers[:, 0] > 74)
                | (self.embers[:, 1] < -26)
                | (self.embers[:, 1] > 26)
            )
            if dead.any():
                self.embers[dead] = self._seed_embers(int(dead.sum()))
                self.ember_vel[dead] = 0.0
        self.ember_instancer.GetPositionsAttr().Set(
            Vt.Vec3fArray.FromNumpy(np.ascontiguousarray(self.embers, dtype=np.float32))
        )
        self._orient_billboards(eye)
        self._update_instancer(t)

    def _update_instancer(self, t):
        cfg = self.config["plume"]
        # 10 Hz is plenty for a slowly varying Eulerian field
        if self.last_color_t is not None and abs(t - self.last_color_t) < 0.1:
            return
        self.last_color_t = t
        rgb, scale, conc, hide = self.data.particle_colors(
            self.positions,
            t,
            self.species,
            vmin_ug=float(cfg.get("min_ug_m3", 10.0)),
            min_scale=float(cfg.get("min_scale", 0.18)),
            max_scale=float(cfg.get("max_scale", 0.85)),
        )
        base_scale = np.asarray(scale, dtype=np.float32)
        vmin = float(cfg.get("min_ug_m3", 10.0))
        vmax = max(self.data.max_ug(self.species), vmin * 10.0)
        norm = np.clip(
            (np.log10(np.maximum(conc, vmin)) - math.log10(vmin))
            / max(math.log10(vmax) - math.log10(vmin), 1e-9),
            0.0,
            1.0,
        )
        bins = np.minimum((norm * self.bins).astype(np.int32), self.bins - 1)
        bins = np.where(hide, 0, bins).astype(np.int32)
        proto = bins * self.variants + self.variant_of
        self.instancer.GetProtoIndicesAttr().Set(Vt.IntArray.FromNumpy(proto))
        scaled = np.repeat(base_scale[:, None], 3, axis=1)
        self.instancer.GetScalesAttr().Set(Vt.Vec3fArray.FromNumpy(scaled))

    def set_data(self, data):
        cfg = self.config["plume"]
        self.data = data
        self.positions = data.generate_particles(
            count=int(cfg.get("particles", 18000)),
            t=float(cfg.get("sample_time_s", 30.0)),
            threshold_fraction=float(cfg.get("threshold_fraction", 0.002)),
            gamma=float(cfg.get("gamma", 0.45)),
            seed=int(cfg.get("seed", 7)),
            weight_species=tuple(cfg.get("weight_species", ["CO", "PM25", "SO2"])),
        )
        self.count = self.positions.shape[0]
        if len(self.variant_of) != self.count:
            rng = np.random.default_rng(int(cfg.get("seed", 7)) + 991)
            self.variant_of = rng.integers(0, self.variants, size=self.count).astype(np.int32)
            self.instancer.GetOrientationsAttr().Set(
                Vt.QuathArray([Gf.Quath(1.0, 0.0, 0.0, 0.0)] * self.count)
            )
        self.instancer.GetPositionsAttr().Set(
            Vt.Vec3fArray.FromNumpy(np.ascontiguousarray(self.positions, dtype=np.float32))
        )
        self.ember_rng = np.random.default_rng(23)
        self.embers = self._seed_embers(len(self.embers))
        self.ember_vel = np.zeros_like(self.embers)
        self.ember_instancer.GetPositionsAttr().Set(
            Vt.Vec3fArray.FromNumpy(np.ascontiguousarray(self.embers, dtype=np.float32))
        )
        self.billboard_eye = None
        self.last_color_t = None
        self._update_instancer(float(self.config["mission"].get("data_time_start", 0.0)))

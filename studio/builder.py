# -*- coding: utf-8 -*-
"""Esquema de parâmetros e construtor procedural do avatar (esqueleto, malhas, blendshapes)."""
import math
import random
import re
from types import SimpleNamespace

from .parts import sanitize_parts, build_part_meshes
from .geometry import (Mesh, Skeleton, add, sub, mul, norm, lerp, clamp, smooth, rot_x, rot_y, rot_z,
                       add_ellipsoid, add_torus, add_rings, Ring, Chain, axis_chain, body_tube, profile)

# --------------------------------------------------------------------------- esquema (fonte única da UI/CLI)

def _opt(*pairs):
    return [list(p) for p in pairs]

SCHEMA = [
    {"group": "Identidade", "items": [
        {"key": "name", "label": "Nome do avatar", "type": "text", "default": "MeuAvatar"},
        {"key": "seed", "label": "Semente de variação", "type": "int", "min": 0, "max": 9999, "default": 7},
    ]},
    {"group": "Corpo", "items": [
        {"key": "height", "label": "Altura (m)", "type": "range", "min": 0.9, "max": 2.1, "step": 0.01, "default": 1.62},
        {"key": "head_size", "label": "Tamanho da cabeça", "type": "range", "min": 0.8, "max": 1.5, "step": 0.01, "default": 1.18},
        {"key": "eye_size", "label": "Tamanho dos olhos", "type": "range", "min": 0.7, "max": 1.5, "step": 0.01, "default": 1.12},
        {"key": "shoulder_width", "label": "Largura dos ombros", "type": "range", "min": 0.7, "max": 1.3, "step": 0.01, "default": 1.0},
        {"key": "hip_width", "label": "Largura do quadril", "type": "range", "min": 0.8, "max": 1.3, "step": 0.01, "default": 1.0},
        {"key": "waist", "label": "Cintura", "type": "range", "min": 0.8, "max": 1.2, "step": 0.01, "default": 1.0},
        {"key": "bust", "label": "Busto", "type": "range", "min": 0.0, "max": 1.0, "step": 0.01, "default": 0.3},
        {"key": "limb_thickness", "label": "Grossura dos membros", "type": "range", "min": 0.8, "max": 1.3, "step": 0.01, "default": 1.0},
        {"key": "leg_ratio", "label": "Comprimento das pernas", "type": "range", "min": 0.85, "max": 1.25, "step": 0.01, "default": 1.05},
        {"key": "arm_ratio", "label": "Comprimento dos braços", "type": "range", "min": 0.85, "max": 1.2, "step": 0.01, "default": 1.0},
        {"key": "fingers", "label": "Dedos com ossos (gestos do VRChat)", "type": "bool", "default": True},
    ]},
    {"group": "Cabelo, orelhas e cauda", "items": [
        {"key": "hair_style", "label": "Cabelo", "type": "select", "default": "long",
         "options": _opt(("short", "Curto"), ("bob", "Chanel"), ("long", "Longo"), ("ponytail", "Rabo de cavalo"),
                         ("twintails", "Maria-chiquinha"), ("spiky", "Espetado"), ("bald", "Sem cabelo"))},
        {"key": "ears", "label": "Orelhas", "type": "select", "default": "human",
         "options": _opt(("human", "Humanas"), ("elf", "Élficas"), ("cat", "Gato"), ("fox", "Raposa"), ("bunny", "Coelho"))},
        {"key": "tail", "label": "Cauda", "type": "select", "default": "none",
         "options": _opt(("none", "Nenhuma"), ("cat", "Gato"), ("fox", "Raposa"), ("dog", "Cachorro"))},
    ]},
    {"group": "Roupas e acessórios", "items": [
        {"key": "top", "label": "Parte de cima", "type": "select", "default": "hoodie",
         "options": _opt(("hoodie", "Moletom com capuz"), ("tshirt", "Camiseta"), ("longsleeve", "Manga longa"), ("tank", "Regata"), ("none", "Nenhuma"))},
        {"key": "bottom", "label": "Parte de baixo", "type": "select", "default": "skirt",
         "options": _opt(("pants", "Calça"), ("shorts", "Shorts"), ("skirt", "Saia"), ("none", "Nenhuma"))},
        {"key": "shoes", "label": "Calçado", "type": "select", "default": "sneakers",
         "options": _opt(("sneakers", "Tênis"), ("boots", "Botas"), ("none", "Descalço"))},
        {"key": "glasses", "label": "Óculos", "type": "bool", "default": False},
        {"key": "headphones", "label": "Fones de ouvido", "type": "bool", "default": False},
        {"key": "beanie", "label": "Gorro", "type": "bool", "default": False},
    ]},
    {"group": "Cores", "items": [
        {"key": "skin", "label": "Pele", "type": "color", "default": "#f3cdb6"},
        {"key": "hair", "label": "Cabelo", "type": "color", "default": "#49345f"},
        {"key": "eyes", "label": "Olhos", "type": "color", "default": "#72aee8"},
        {"key": "top_color", "label": "Parte de cima", "type": "color", "default": "#e9e1f3"},
        {"key": "bottom_color", "label": "Parte de baixo", "type": "color", "default": "#51415f"},
        {"key": "shoes_color", "label": "Calçado", "type": "color", "default": "#ee91b8"},
        {"key": "accent", "label": "Detalhes", "type": "color", "default": "#f5b5d1"},
    ]},
    {"group": "Exportação", "items": [
        {"key": "detail", "label": "Qualidade da malha", "type": "select", "default": "3",
         "options": _opt(("1", "Leve"), ("2", "Normal"), ("3", "Alto — recomendado"), ("4", "Ultra — mais polígonos"))},
        {"key": "merge_meshes", "label": "Juntar tudo em 1 malha (melhor desempenho, sem alternar roupas)", "type": "bool", "default": False},
    ]},
]

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def make_spec(data=None):
    """Valida/normaliza um dicionário de parâmetros e devolve SimpleNamespace."""
    data = data or {}
    out = {}
    for grp in SCHEMA:
        for it in grp["items"]:
            k, t, dflt = it["key"], it["type"], it["default"]
            v = data.get(k, dflt)
            try:
                if t == "range":
                    v = clamp(float(v), it["min"], it["max"])
                elif t == "int":
                    v = int(clamp(int(float(v)), it["min"], it["max"]))
                elif t == "bool":
                    v = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "sim", "on")
                elif t == "select":
                    v = str(v)
                    if v not in [o[0] for o in it["options"]]:
                        v = dflt
                elif t == "color":
                    v = str(v)
                    if not _HEX.match(v):
                        v = dflt
                elif t == "text":
                    v = re.sub(r"[^\w\- ]", "", str(v), flags=re.UNICODE).strip()[:40] or dflt
            except (TypeError, ValueError):
                v = dflt
            out[k] = v
    out["detail"] = int(out["detail"])
    out["parts"] = sanitize_parts(data.get("parts", []))
    return SimpleNamespace(**out)


def spec_to_dict(spec, strip_obj=False):
    d = {k: v for k, v in vars(spec).items()}
    if strip_obj:
        d["parts"] = [{k: v for k, v in p.items() if k != "obj"} for p in d.get("parts", [])]
    return d


def random_spec(seed=None):
    rng = random.Random(seed)
    skins = ["#fbe3d4", "#f3cdb6", "#efc3a3", "#d9a07c", "#b97a55", "#8c5a3c", "#6b4330"]
    hairs = ["#2b2b33", "#6b3f2a", "#d9b36a", "#e8e8ef", "#c2506b", "#4a6fd1", "#3fae8f", "#8e5bd6", "#f07a3a", "#ff8fb8"]
    eyes = ["#3aa7e0", "#6bbf59", "#e0763a", "#8e5bd6", "#e9546b", "#caa24a", "#4b5563", "#2fb5a8"]
    cloth = ["#f4f1ea", "#2f3a5c", "#e9546b", "#2e7d6b", "#f0c14b", "#7a4bd1", "#24262d", "#4ab0e8", "#e07a3a"]
    d = {}
    for grp in SCHEMA:
        for it in grp["items"]:
            if it["type"] == "select" and it["key"] != "detail":
                d[it["key"]] = rng.choice([o[0] for o in it["options"]])
    d.update(
        name="Avatar%04d" % rng.randint(0, 9999), seed=rng.randint(0, 9999),
        height=round(rng.uniform(1.25, 1.85), 2), head_size=round(rng.uniform(0.95, 1.3), 2),
        eye_size=round(rng.uniform(0.85, 1.35), 2), shoulder_width=round(rng.uniform(0.85, 1.15), 2),
        hip_width=round(rng.uniform(0.9, 1.2), 2), waist=round(rng.uniform(0.9, 1.1), 2),
        bust=round(rng.uniform(0.0, 0.8), 2), limb_thickness=round(rng.uniform(0.9, 1.15), 2),
        leg_ratio=round(rng.uniform(0.95, 1.15), 2), arm_ratio=round(rng.uniform(0.95, 1.1), 2),
        skin=rng.choice(skins), hair=rng.choice(hairs), eyes=rng.choice(eyes),
        top_color=rng.choice(cloth), bottom_color=rng.choice(cloth), shoes_color=rng.choice(cloth),
        accent=rng.choice(cloth + hairs),
        glasses=rng.random() < 0.2, headphones=rng.random() < 0.2, beanie=rng.random() < 0.12,
        fingers=True, merge_meshes=False, detail="3")
    return d


# --------------------------------------------------------------------------- paleta

PALETTE_NAMES = ["skin", "blush", "eye_white", "iris", "pupil", "highlight", "hair", "hair_dark", "mouth", "nose",
                 "top", "top_accent", "bottom", "bottom_accent", "shoes", "sole", "accent", "ear_inner",
                 "tail_tip", "metal"]
PALETTE_COLS = 8
PALETTE_ROWS = 8
CID = {n: i for i, n in enumerate(PALETTE_NAMES)}


def hex_rgb(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def shade(c, f):
    return tuple(int(clamp(round(v * f), 0, 255)) for v in c)


def build_palette(s, extras=()):
    skin, hair = hex_rgb(s.skin), hex_rgb(s.hair)
    top, bottom = hex_rgb(s.top_color), hex_rgb(s.bottom_color)
    acc = hex_rgb(s.accent)
    cols = {
        "skin": skin, "blush": mix(skin, (255, 105, 135), 0.5), "eye_white": (250, 250, 252),
        "iris": hex_rgb(s.eyes), "pupil": (28, 22, 38), "highlight": (255, 255, 255),
        "hair": hair, "hair_dark": shade(hair, 0.68), "mouth": (120, 48, 66), "nose": shade(skin, 0.94),
        "top": top, "top_accent": mix(top, acc, 0.85), "bottom": bottom, "bottom_accent": mix(bottom, acc, 0.8),
        "shoes": hex_rgb(s.shoes_color), "sole": (242, 242, 240), "accent": acc,
        "ear_inner": mix(skin, (255, 150, 175), 0.55), "tail_tip": (250, 248, 244), "metal": (72, 74, 86),
    }
    return [cols[n] for n in PALETTE_NAMES] + [hex_rgb(h) for h in extras]


def cid_uv(cid):
    """UV (convenção Unity, origem embaixo) do centro da célula da paleta."""
    col, row = cid % PALETTE_COLS, cid // PALETTE_COLS
    return ((col + 0.5) / PALETTE_COLS, 1.0 - (row + 0.5) / PALETTE_ROWS)


def add_anime_head(mesh, center, radii, cid, jw, seg=32, rings=24):
    """Cabeça anime suave: testa cheia, bochechas delicadas e queixo mais estreito."""
    rx, ry, rz = radii
    rows = []
    for i in range(rings + 1):
        th = math.pi * i / rings
        sy, cy = math.sin(th), math.cos(th)
        row = []
        for j in range(seg):
            ph = 2.0 * math.pi * j / seg
            x0, z0 = sy * math.sin(ph), sy * math.cos(ph)
            # Narrow the jaw and chin without creating a pointed, angular silhouette.
            jaw_t = clamp((cy + 0.92) / 0.62, 0.0, 1.0)
            jaw = 0.70 + 0.30 * smooth(jaw_t)
            cheek = 1.0 + 0.045 * math.exp(-((cy + 0.05) / 0.30) ** 2)
            depth = 1.0 + 0.035 * math.exp(-((cy + 0.02) / 0.38) ** 2)
            x = rx * x0 * jaw * cheek
            y = ry * cy
            z = rz * z0 * depth
            # Approximate the analytic normal; smooth vertex normals are rebuilt in finalize().
            rn = norm((x0 / max(rx, 1e-6), cy / max(ry, 1e-6), z0 / max(rz, 1e-6)))
            row.append(mesh.vertex(add(center, (x, y, z)), rn, cid, jw))
        rows.append(row)
    for i in range(rings):
        for j in range(seg):
            j2 = (j + 1) % seg
            a, b = rows[i][j], rows[i][j2]
            c, d = rows[i + 1][j], rows[i + 1][j2]
            mesh.tri(a, c, d)
            mesh.tri(a, d, b)


# --------------------------------------------------------------------------- resultado

class Avatar:
    def __init__(self):
        self.skeleton = None
        self.meshes = []
        self.palette = []
        self.humanoid = []       # [(nome_humanoid_unity, nome_osso)]
        self.physbones = []      # [{"root","kind","bones":[...]}]
        self.view_position = (0.0, 1.4, 0.05)
        self.eyes = {"left": "Eye_L", "right": "Eye_R"}
        self.spec = None
        self.scale = 1.0

    def stats(self):
        tris = sum(len(m.tris) // 3 for m in self.meshes)
        verts = sum(len(m.pos) for m in self.meshes)
        shapes = sum(len(m.shapes) for m in self.meshes)
        # Cadeias de PhysBones sobrepostas não devem contar o mesmo transform várias vezes.
        pb_bones = len({bone for p in self.physbones for bone in p["bones"]})
        return {"triangles": tris, "vertices": verts, "bones": len(self.skeleton.names),
                "skinned_meshes": len(self.meshes), "material_slots": len(self.meshes),
                "blendshapes": shapes, "physbone_components": len(self.physbones),
                "physbone_transforms": pb_bones}


RANK_LIMITS = [  # (chave, Excellent, Good, Medium, Poor)
    ("triangles", 32000, 70000, 70000, 70000),
    ("skinned_meshes", 1, 2, 8, 16),
    ("material_slots", 4, 8, 16, 32),
    ("bones", 75, 150, 256, 400),
    ("physbone_components", 4, 8, 16, 32),
    ("physbone_transforms", 16, 64, 128, 256),
]
RANK_NAMES = ["Excellent", "Good", "Medium", "Poor", "Very Poor"]


def perf_rank(stats):
    """Estimativa heurística local; não reproduz integralmente o ranking oficial do SDK."""
    worst, why = 0, []
    for key, *lims in RANK_LIMITS:
        v = stats.get(key, 0)
        r = 4
        for i, lim in enumerate(lims):
            if v <= lim:
                r = i
                break
        if r > worst:
            worst, why = r, []
        if r == worst and r > 0:
            why.append(key)
    return RANK_NAMES[worst], why


# --------------------------------------------------------------------------- construtor

VISEMES = {  # nome: (escala x, escala y, deslocamento y)  — relativos à boca
    "pp": (0.9, 0.5, 0.0), "ff": (1.0, 0.8, -0.0008), "th": (1.0, 1.5, -0.002), "dd": (1.0, 1.9, -0.003),
    "kk": (1.0, 2.3, -0.004), "ch": (0.7, 2.0, -0.004), "ss": (1.15, 1.2, -0.001), "nn": (1.0, 1.3, -0.002),
    "rr": (0.8, 2.2, -0.004), "aa": (1.0, 4.5, -0.009), "e": (1.25, 2.4, -0.005), "ih": (1.15, 1.9, -0.004),
    "oh": (0.65, 4.2, -0.008), "ou": (0.5, 3.2, -0.006),
}


class AvatarBuilder:
    def __init__(self, spec, detail=None):
        self.s = spec
        self.detail = int(detail or spec.detail)
        d = self.detail
        self.sd = {1: 12, 2: 18, 3: 24, 4: 32}[d]
        self.sf = {1: 6, 2: 8, 3: 10, 4: 12}[d]
        self.ec = {1: (10, 7), 2: (16, 11), 3: (22, 15), 4: (30, 20)}[d]
        self.hc = {1: (16, 11), 2: (22, 16), 3: (30, 22), 4: (40, 28)}[d]
        self.rk = {1: 0.6, 2: 1.0, 3: 1.5, 4: 2.0}[d]
        self.rng = random.Random(int(spec.seed))
        self.extra = {}   # cor hex -> índice na paleta (cores das peças do usuário)

    def color_cid(self, hexcol):
        hexcol = hexcol.lower()
        if hexcol in self.extra:
            return self.extra[hexcol]
        total = PALETTE_COLS * PALETTE_ROWS
        if len(PALETTE_NAMES) + len(self.extra) >= total:      # paleta cheia: usa a cor mais próxima
            pal = build_palette(self.s, list(self.extra))
            t = hex_rgb(hexcol)
            best = min(range(len(pal)), key=lambda i: sum((pal[i][k] - t[k]) ** 2 for k in range(3)))
            return best
        cid = len(PALETTE_NAMES) + len(self.extra)
        self.extra[hexcol] = cid
        return cid

    def R(self, n):
        return max(3, int(round(n * self.rk)))

    # ---------------------------------------------------------------- medidas
    def _dims(self):
        s = self.s
        lr, ar, hs, sw = s.leg_ratio, s.arm_ratio, s.head_size, s.shoulder_width
        self.ankle_y = 0.07
        self.L1, self.L2 = 0.40 * lr, 0.38 * lr
        self.hip_y = self.ankle_y + self.L1 + self.L2
        self.knee_y = self.ankle_y + self.L2
        h = self.hip_y
        self.spine_y, self.chest_y, self.uchest_y = h + 0.10, h + 0.24, h + 0.34
        self.neck_y, self.head_y, self.sh_y = h + 0.44, h + 0.51, h + 0.40
        self.hcy = self.head_y + 0.095 * hs
        self.hr = (0.108 * hs, 0.118 * hs, 0.108 * hs)
        self.leg_x = 0.085 * s.hip_width
        self.ua, self.fa = 0.27 * ar, 0.25 * ar
        self.uax = 0.155 * sw
        self.elx = self.uax + self.ua
        self.wrx = self.elx + self.fa
        self.arm_drop_elbow = 0.075 * ar
        self.arm_drop_hand = 0.145 * ar
        self.hand_y = self.sh_y - self.arm_drop_hand
        self.eye_x = 0.047 * hs
        self.eye_y = self.hcy - 0.012 * hs
        self.S = s.height / (self.hcy + self.hr[1])   # fator de escala final (altura real do avatar)

    def hz(self, x, y):
        hx, hy, hz = self.hr
        v = 1.0 - (x / hx) ** 2 - ((y - self.hcy) / hy) ** 2
        return hz * math.sqrt(max(v, 0.0))

    def surf_rot(self, x, y):
        hx, hy, hz = self.hr
        z = self.hz(x, y)
        n = norm((x / hx ** 2, (y - self.hcy) / hy ** 2, z / hz ** 2))
        yaw = math.atan2(n[0], n[2])
        pit = math.atan2(n[1], math.hypot(n[0], n[2]))
        return lambda v: rot_y(rot_x(v, -pit), yaw)

    # ---------------------------------------------------------------- esqueleto
    def _skeleton(self):
        sk = self.skel = Skeleton()
        s, B = self.s, {}
        self.B = B

        def bone(name, parent, pos, human=None):
            i = sk.add(name, B[parent] if parent else -1, pos)
            B[name] = i
            if human:
                self.humanoid.append((human, name))
            return i

        h = self.hip_y
        bone("Hips", None, (0, h, 0), "Hips")
        bone("Spine", "Hips", (0, self.spine_y, 0), "Spine")
        bone("Chest", "Spine", (0, self.chest_y, 0), "Chest")
        bone("UpperChest", "Chest", (0, self.uchest_y, 0), "UpperChest")
        bone("Neck", "UpperChest", (0, self.neck_y, 0), "Neck")
        bone("Head", "Neck", (0, self.head_y, 0), "Head")
        for side, sg in (("L", -1), ("R", 1)):
            P = "Left" if side == "L" else "Right"
            ez = self.hz(self.eye_x, self.eye_y) - 0.002
            bone("Eye_" + side, "Head", (sg * self.eye_x, self.eye_y, ez), P + "Eye")
            bone("Shoulder_" + side, "UpperChest", (sg * 0.05, self.sh_y + 0.012, 0), P + "Shoulder")
            bone("UpperArm_" + side, "Shoulder_" + side, (sg * self.uax, self.sh_y - 0.025, 0), P + "UpperArm")
            bone("LowerArm_" + side, "UpperArm_" + side, (sg * self.elx, self.sh_y - self.arm_drop_elbow, 0), P + "LowerArm")
            bone("Hand_" + side, "LowerArm_" + side, (sg * self.wrx, self.hand_y, 0), P + "Hand")
            x = sg * self.leg_x
            bone("UpperLeg_" + side, "Hips", (x, h, 0), P + "UpperLeg")
            bone("LowerLeg_" + side, "UpperLeg_" + side, (x, self.knee_y, 0), P + "LowerLeg")
            bone("Foot_" + side, "LowerLeg_" + side, (x, self.ankle_y, 0), P + "Foot")
            bone("Toes_" + side, "Foot_" + side, (x, 0.028, 0.105), P + "Toes")
            if s.fingers:
                self._finger_bones(side, sg, P, bone)

    def _finger_defs(self, sg):
        wx = self.wrx
        y = self.hand_y - 0.002
        bx = sg * (wx + 0.078)
        defs = {
            "Index": ((bx, y, 0.030), (sg, 0, 0), (0.030, 0.019, 0.016)),
            "Middle": ((bx, y, 0.011), (sg, 0, 0), (0.033, 0.021, 0.017)),
            "Ring": ((bx, y, -0.008), (sg, 0, 0), (0.030, 0.019, 0.016)),
            "Little": ((bx, y, -0.025), (sg, 0, 0), (0.024, 0.015, 0.014)),
        }
        tdir = norm((sg * 0.7, -0.12, 0.7))
        defs["Thumb"] = ((sg * (wx + 0.018), y - 0.004, 0.030), tdir, (0.032, 0.026, 0.022))
        return defs

    def _finger_chain_pts(self, base, d, lens):
        d = norm(d)
        p0 = base
        p1 = add(p0, mul(d, lens[0]))
        p2 = add(p1, mul(d, lens[1]))
        p3 = add(p2, mul(d, lens[2]))
        return [p0, p1, p2, p3]

    def _finger_bones(self, side, sg, P, bone):
        for finger, (base, d, lens) in self._finger_defs(sg).items():
            pts = self._finger_chain_pts(base, d, lens)
            parent = "Hand_" + side
            for k, seg in enumerate(("Proximal", "Intermediate", "Distal")):
                nm = "%s_%s_%s" % (finger, seg, side)
                bone(nm, parent, pts[k], "%s%s%s" % (P, finger, seg))
                parent = nm

    # ---------------------------------------------------------------- corpo
    def _body(self, m):
        s, B = self.s, self.B
        th = s.limb_thickness
        hw, sw, wst, bust = s.hip_width, s.shoulder_width, s.waist, s.bust
        h = self.hip_y

        # tronco + pescoço
        dyk = [(-0.07, 0.118 * hw, 0.086), (-0.02, 0.148 * hw, 0.101), (0.05, 0.136 * hw, 0.097),
               (0.12, 0.112 * wst, 0.083 * wst), (0.22, 0.123, 0.089 + 0.010 * bust),
               (0.29, 0.139, 0.096 + 0.026 * bust), (0.36, 0.151 * sw, 0.094), (0.40, 0.140 * sw, 0.084),
               (0.425, 0.072, 0.062), (0.44, 0.052, 0.050), (0.47, 0.044, 0.044), (0.51, 0.043, 0.043)]
        self.torso_keys = [(dy + 0.07, a, b) for dy, a, b in dyk]
        names = ["Hips", "Spine", "Chest", "UpperChest", "Neck", "Head"]
        self.torso = axis_chain([B[n] for n in names], [self.skel.pos[B[n]] for n in names], None, pre=0.07)
        body_tube(m, self.torso, self.torso_keys, CID["skin"], self.sd, self.R(26), caps=(True, False))

        # cabeça
        hx, hy, hz = self.hr
        add_anime_head(m, (0, self.hcy, 0), self.hr, CID["skin"], [(B["Head"], 1.0)],
                       seg=self.hc[0], rings=self.hc[1])

        for side, sg in (("L", -1), ("R", 1)):
            # braço
            nodes = ["UpperArm_" + side, "LowerArm_" + side, "Hand_" + side]
            ch = axis_chain([B[n] for n in nodes], [self.skel.pos[B[n]] for n in nodes],
                            B["Shoulder_" + side], pre=0.05)
            ua, fa = self.ua, self.fa
            keys = [(0.0, 0.052 * th, 0.052 * th), (0.05, 0.050 * th, 0.050 * th),
                    (0.05 + 0.4 * ua, 0.043 * th, 0.043 * th), (0.05 + ua, 0.036 * th, 0.036 * th),
                    (0.05 + ua + 0.3 * fa, 0.036 * th, 0.036 * th), (0.05 + ua + fa, 0.024 * th, 0.024 * th)]
            setattr(self, "arm_" + side, (ch, keys))
            body_tube(m, ch, keys, CID["skin"], self.sd, self.R(14), caps=(True, False))
            self._hand(m, side, sg)

            # perna
            nodes = ["UpperLeg_" + side, "LowerLeg_" + side, "Foot_" + side]
            ch = axis_chain([B[n] for n in nodes], [self.skel.pos[B[n]] for n in nodes], B["Hips"], pre=0.04)
            L1, L2 = self.L1, self.L2
            keys = [(0.0, 0.079 * th, 0.078 * th), (0.04, 0.084 * th, 0.083 * th),
                    (0.04 + 0.45 * L1, 0.074 * th, 0.073 * th), (0.04 + L1, 0.055 * th, 0.054 * th),
                    (0.04 + L1 + 0.35 * L2, 0.058 * th, 0.057 * th), (0.04 + L1 + L2, 0.035 * th, 0.035 * th)]
            setattr(self, "leg_" + side, (ch, keys))
            body_tube(m, ch, keys, CID["skin"], self.sd, self.R(14), caps=(True, False))

            # pé
            x = sg * self.leg_x
            pts = [(x, 0.030, -0.050), (x, 0.050, -0.005), (x, 0.028, 0.105), (x, 0.022, 0.180)]
            fch = Chain([B["Foot_" + side], B["Toes_" + side]], pts, [1, 2], None)
            fkeys = [(0.0, 0.030, 0.028), (0.049, 0.038, 0.040), (0.161, 0.046, 0.027), (fch.total, 0.030, 0.020)]
            setattr(self, "foot_" + side, (fch, fkeys))
            body_tube(m, fch, fkeys, CID["skin"], max(8, self.sd - 2), self.R(10), dome=(True, True))

    def _hand(self, m, side, sg):
        s, B = self.s, self.B
        Hb = B["Hand_" + side]
        W = self.skel.pos[Hb]
        sc = math.sqrt(s.limb_thickness)
        if s.fingers:
            add_ellipsoid(m, add(W, (sg * 0.038, -0.001, 0)), (0.042, 0.0165 * sc, 0.040 * sc),
                          CID["skin"], [(Hb, 1.0)], seg=self.ec[0], rings=self.ec[1])
            for finger, (base, d, lens) in self._finger_defs(sg).items():
                pts = self._finger_chain_pts(base, d, lens)
                bones = [B["%s_%s_%s" % (finger, seg, side)] for seg in ("Proximal", "Intermediate", "Distal")]
                ch = Chain(bones, pts, [0, 1, 2], Hb)
                r0, r1 = (0.0105, 0.0075) if finger == "Thumb" else (0.0088, 0.0062)
                keys = [(0.0, r0 * sc, r0 * sc), (ch.total, r1 * sc, r1 * sc)]
                body_tube(m, ch, keys, CID["skin"], self.sf, self.R(7), dome=(False, True))
        else:
            add_ellipsoid(m, add(W, (sg * 0.060, -0.001, 0.004)), (0.074, 0.017 * sc, 0.041 * sc),
                          CID["skin"], [(Hb, 1.0)], seg=self.ec[0], rings=self.ec[1])
            add_ellipsoid(m, add(W, (sg * 0.030, -0.006, 0.040)), (0.026, 0.012 * sc, 0.014 * sc),
                          CID["skin"], [(Hb, 1.0)], seg=self.ec[0], rings=self.ec[1],
                          rot=lambda v: rot_y(v, sg * -0.6))

    # ---------------------------------------------------------------- rosto
    def _face(self, m):
        s, B = self.s, self.B
        hs, es = s.head_size, s.eye_size
        self.centers = {}
        ex, ey = self.eye_x, self.eye_y
        seg, rg = self.ec
        for side, sg in (("L", -1), ("R", 1)):
            Eb = B["Eye_" + side]
            E = self.skel.pos[Eb]
            rot = self.surf_rot(sg * ex, ey)
            tag = "eye" + side
            jw = [(Eb, 1.0)]
            k = es * hs

            # Eye socket / eyeliner, almond-shaped sclera, layered iris and two catchlights.
            add_ellipsoid(m, add(E, rot((0.0, 0.0, 0.0015))), (0.031 * k, 0.0185 * k, 0.0075),
                          CID["eye_white"], jw, seg, rg, tag, rot)
            add_ellipsoid(m, add(E, rot((0.0, -0.001 * k, 0.0065))), (0.0165 * k, 0.0160 * k, 0.008),
                          CID["hair_dark"], jw, seg, rg, tag, rot)
            add_ellipsoid(m, add(E, rot((0.0, -0.001 * k, 0.0085))), (0.0148 * k, 0.0145 * k, 0.008),
                          CID["iris"], jw, seg, rg, tag, rot)
            add_ellipsoid(m, add(E, rot((0.0, -0.001 * k, 0.014))), (0.0072 * k, 0.0105 * k, 0.0045),
                          CID["pupil"], jw, max(8, seg - 2), max(6, rg - 2), tag, rot)
            add_ellipsoid(m, add(E, rot((sg * -0.0055 * k, 0.006 * k, 0.018))),
                          (0.0055 * k, 0.0055 * k, 0.0035), CID["highlight"], jw, 8, 6, tag, rot)
            add_ellipsoid(m, add(E, rot((sg * 0.0045 * k, -0.006 * k, 0.017))),
                          (0.0022 * k, 0.0028 * k, 0.002), CID["highlight"], jw, 6, 4, tag, rot)

            # Upper lash line follows the curved eye contour instead of a spherical bump.
            lash_pts = []
            for q in range(9):
                u = -1.0 + 2.0 * q / 8
                x = sg * ex + u * 0.032 * k
                y = ey + 0.0105 * k * math.sqrt(max(0.0, 1.0 - u * u)) + 0.002
                z = self.hz(x, y) + 0.006
                lash_pts.append((x, y, z))
            lash = Chain([B["Head"]], lash_pts, [0], None)
            body_tube(m, lash, [(0.0, 0.0018 * hs, 0.0015 * hs),
                                (lash.total, 0.0011 * hs, 0.0010 * hs)], CID["hair_dark"], 7, 10)

            # A softly arched brow, slightly thicker toward the inner corner.
            bx, by = sg * ex * 1.04, ey + 0.041 * k
            bz = self.hz(bx, by) + 0.003
            bpts = [(sg * (ex - 0.024 * hs), by - 0.003, self.hz(sg * (ex - 0.024 * hs), by - 0.003) + 0.002),
                    (bx, by + 0.004 * hs, bz),
                    (sg * (ex + 0.025 * hs), by - 0.002, self.hz(sg * (ex + 0.025 * hs), by - 0.002) + 0.002)]
            brow = Chain([B["Head"]], bpts, [0], None)
            body_tube(m, brow, [(0.0, 0.0048 * hs, 0.003), (brow.total, 0.0035 * hs, 0.0025)],
                      CID["hair_dark"], 7, 8)
            self.centers["eye" + side] = E
            # Soft cheek blush remains a toggleable blendshape.
            cx, cyy = sg * 0.064 * hs, ey - 0.030 * hs
            cz = self.hz(cx, cyy) + 0.001
            cr = self.surf_rot(cx, cyy)
            self.centers["blush" + side] = (cx, cyy, cz)
            add_ellipsoid(m, (cx, cyy, cz), (0.018 * hs, 0.009 * hs, 0.0025), CID["blush"],
                          [(B["Head"], 1.0)], 12, 5, "blush" + side, cr)

        # A little nose bridge and a soft tip make the profile less toy-like.
        ny = self.hcy - 0.030 * hs
        nr = self.surf_rot(0, ny)
        add_ellipsoid(m, (0, ny + 0.006 * hs, self.hz(0, ny + 0.006 * hs) + 0.001),
                      (0.0048 * hs, 0.013 * hs, 0.0035 * hs), CID["nose"], [(B["Head"], 1.0)], 10, 7, "", nr)
        add_ellipsoid(m, (0, ny - 0.003 * hs, self.hz(0, ny - 0.003 * hs) + 0.003),
                      (0.0075 * hs, 0.0055 * hs, 0.005 * hs), CID["nose"], [(B["Head"], 1.0)], 10, 6, "", nr)

        # Defined upper/lower lip volumes and a subtle mouth opening.
        my = self.hcy - 0.063 * hs
        mr = self.surf_rot(0, my)
        mc = (0, my, self.hz(0, my) + 0.002)
        add_ellipsoid(m, mc, (0.013 * hs, 0.0038 * hs, 0.003 * hs), CID["mouth"],
                      [(B["Head"], 1.0)], 14, 7, "mouth", mr)
        add_ellipsoid(m, add(mc, mr((0, -0.0045 * hs, 0.0005))),
                      (0.010 * hs, 0.0028 * hs, 0.0025 * hs), CID["blush"],
                      [(B["Head"], 1.0)], 12, 6, "mouth", mr)
        self.centers["mouth"] = mc

        # Human/elf ears are integrated into the head mesh.
        hx, hy, hz = self.hr
        ey2 = self.hcy - 0.012 * hs
        for side, sg in (("L", -1), ("R", 1)):
            if s.ears == "human":
                add_ellipsoid(m, (sg * hx * 0.98, ey2, -0.005), (0.014, 0.029 * hs, 0.020 * hs),
                              CID["skin"], [(B["Head"], 1.0)], 14, 8)
            elif s.ears == "elf":
                base = (sg * hx * 0.93, ey2, -0.005)
                tip = add(base, (sg * 0.075, 0.045, -0.035))
                ch = Chain([B["Head"]], [base, tip], [0], None)
                body_tube(m, ch, [(0.0, 0.016, 0.016), (ch.total, 0.002, 0.002)],
                          CID["skin"], 12, 8, dome=(False, True))

    # ---------------------------------------------------------------- blendshapes
    def _shapes(self, m):
        s, hs = self.s, self.s.head_size
        C = self.centers
        mc = C["mouth"]

        def mouth(wx, hy, dy, extra=None):
            def fn(tag, p):
                if tag == "mouth":
                    return (mc[0] + (p[0] - mc[0]) * wx, mc[1] + dy * hs + (p[1] - mc[1]) * hy, p[2])
                return extra(tag, p) if extra else None
            return fn

        m.morph("vrc.v_sil", lambda tag, p: None)
        for name, (wx, hy, dy) in VISEMES.items():
            m.morph("vrc.v_" + name, mouth(wx, hy, dy))

        def eyes(k, shift=0.0, only=None):
            def fn(tag, p):
                if tag in ("eyeL", "eyeR") and (only is None or tag == only):
                    c = C[tag]
                    return (p[0], c[1] + shift + (p[1] - c[1]) * k, p[2])
                return None
            return fn

        m.morph("Blink", eyes(0.08))
        m.morph("Blink_L", eyes(0.08, only="eyeL"))
        m.morph("Blink_R", eyes(0.08, only="eyeR"))
        m.morph("LookUp", eyes(1.06))
        m.morph("LookDown", eyes(0.72, -0.002))

        def brows(angle, dy, up=0.0):
            def fn(tag, p):
                if tag in ("browL", "browR"):
                    c = C[tag]
                    sg = -1 if tag == "browL" else 1
                    q = rot_z((p[0] - c[0], p[1] - c[1], 0.0), sg * angle)
                    return (c[0] + q[0], c[1] + q[1] + dy * hs, p[2])
                return None
            return fn

        def combine(*fns):
            def fn(tag, p):
                q = p
                for f in fns:
                    r = f(tag, q)
                    if r is not None:
                        q = r
                return q if q != p else None
            return fn

        m.morph("Smile", combine(eyes(0.45, -0.001), mouth(1.35, 1.6, -0.001), brows(-0.05, 0.002)))
        m.morph("Angry", combine(brows(0.38, -0.004), eyes(0.85), mouth(0.85, 1.0, -0.001)))
        m.morph("Sad", combine(brows(-0.32, 0.003), eyes(0.9), mouth(0.8, 0.8, -0.002)))
        m.morph("Surprised", combine(brows(0.0, 0.010), eyes(1.12), mouth(0.6, 4.0, -0.007)))

        # Blush: nasce "escondido" (colapsado) e cresce até o tamanho real
        d = {}
        for i, (tag, p) in enumerate(zip(m.tags, m.pos)):
            if tag in ("blushL", "blushR"):
                c = C[tag]
                d[i] = sub(p, c)       # delta que leva do ponto central ao tamanho real
                m.pos[i] = c
        m.shapes["Blush"] = d

    # ---------------------------------------------------------------- cabelo
    def _hair(self):
        s, B = self.s, self.B
        style = s.hair_style
        if style == "bald":
            return None
        hs = s.head_size
        hx, hy, hz = self.hr
        cy = self.hcy
        ey = self.eye_y
        m = Mesh("Hair", "Cabelo", "hair")
        Hj = [(B["Head"], 1.0)]
        ycut = {"short": -0.08, "spiky": -0.05, "bob": -0.55, "long": -0.70, "ponytail": -0.12,
                "twintails": -0.12}[style]
        ear_win = s.ears in ("human", "elf")
        add_ellipsoid(m, (0, cy + 0.004, -0.006), (hx * 1.07, hy * 1.07, hz * 1.08), CID["hair"], Hj,
                      seg=self.hc[0], rings=self.hc[1] + 2)

        def drop(c):
            xr = c[0] / (hx * 1.07)
            yr = (c[1] - cy) / (hy * 1.07)
            zr = (c[2] + 0.006) / (hz * 1.08)
            if zr > 0.28 and yr < 0.50:
                return True
            if yr < ycut:
                return True
            if ear_win and abs(xr) > 0.72 and abs(zr) < 0.38 and -0.5 < yr < 0.12:
                return True
            return False
        m.clip(drop)

        # Franja em mechas curvas e afiladas: volume na raiz, pontas finas e comprimentos variados.
        def face_z(x, y):
            return self.hz(clamp(x, -hx * 0.97, hx * 0.97), y) + 0.012

        # Mechas frontais em lâminas curvas: superfície achatada, raiz larga e ponta fina.
        # Isso evita a aparência de cápsulas grossas/faixa rígida na testa.
        def hair_ribbon(p0, p1, p2, widths, color=CID["hair"], depth=0.007):
            rows_front, rows_back = [], []
            samples, across = 14, 5
            def center(t):
                omt = 1.0 - t
                return (omt * omt * p0[0] + 2 * omt * t * p1[0] + t * t * p2[0],
                        omt * omt * p0[1] + 2 * omt * t * p1[1] + t * t * p2[1])
            def width_at(t):
                if t < 0.52:
                    q = t / 0.52
                    return widths[0] * (1-q) + widths[1] * q
                q = (t - 0.52) / 0.48
                return widths[1] * (1-q) + widths[2] * q
            for i in range(samples + 1):
                t = i / samples
                x, y = center(t)
                xa, ya = center(max(0.0, t - 0.01))
                xb, yb = center(min(1.0, t + 0.01))
                tx, ty = xb - xa, yb - ya
                ll = math.sqrt(tx * tx + ty * ty) or 1.0
                sx, sy = -ty / ll, tx / ll
                row_f, row_b = [], []
                w = width_at(t)
                for j in range(across):
                    u = -1.0 + 2.0 * j / (across - 1)
                    xx, yy = x + sx * w * u, y + sy * w * u
                    zz = face_z(xx, yy) + 0.010 * hs + depth * (1.0 - u * u)
                    row_f.append(m.vertex((xx, yy, zz), (0, 0, 1), color, Hj))
                    row_b.append(m.vertex((xx, yy, zz - 0.0035 * hs), (0, 0, -1), CID["hair_dark"], Hj))
                rows_front.append(row_f)
                rows_back.append(row_b)
            for i in range(samples):
                for j in range(across - 1):
                    a, b = rows_front[i][j], rows_front[i + 1][j]
                    c, d = rows_front[i + 1][j + 1], rows_front[i][j + 1]
                    m.tri(a, b, c); m.tri(a, c, d)
                    a, b = rows_back[i][j], rows_back[i + 1][j]
                    c, d = rows_back[i + 1][j + 1], rows_back[i][j + 1]
                    m.tri(a, c, b); m.tri(a, d, c)
            # Bordas laterais e extremidades para que a mecha tenha espessura real.
            for i in range(samples):
                for j in (0, across - 1):
                    a, b = rows_front[i][j], rows_front[i + 1][j]
                    c, d = rows_back[i + 1][j], rows_back[i][j]
                    m.tri(a, b, c); m.tri(a, c, d)
            for j in range(across - 1):
                for rf, rb in ((rows_front, rows_back),):
                    a, b = rf[0][j], rf[0][j + 1]
                    c, d = rb[0][j + 1], rb[0][j]
                    m.tri(a, b, c); m.tri(a, c, d)
                    a, b = rf[-1][j], rf[-1][j + 1]
                    c, d = rb[-1][j + 1], rb[-1][j]
                    m.tri(a, c, b); m.tri(a, d, c)

        # A quantidade e o comprimento variam por penteado, sem formar uma franja reta.
        fringe_count = 7 if style in ("long", "bob", "twintails") else 5
        for i in range(fringe_count):
            t = i / max(1, fringe_count - 1)
            xi = (-0.80 + 1.60 * t) * hx
            ytop = cy + hy * (0.73 - 0.06 * abs(2 * t - 1))
            ytip = ey + (0.060 - 0.020 * abs(2 * t - 1)) * hs
            tipx = xi * 0.78 + (t - 0.5) * 0.018 * hs
            midx = (xi + tipx) * 0.52 + (0.012 * hs if i % 2 else -0.009 * hs)
            midy = (ytop + ytip) * 0.51
            p0, p1, p2 = (xi, ytop), (midx, midy), (tipx, ytip)
            wroot = (0.010 + 0.003 * (1.0 - abs(2*t-1))) * hs
            wmid = (0.020 + 0.004 * (1.0 - abs(2*t-1))) * hs
            color = CID["hair_dark"] if i in (1, fringe_count - 2) else CID["hair"]
            hair_ribbon(p0, p1, p2, (wroot, wmid, 0.0018 * hs), color,
                        depth=0.0065 * hs)

        if style in ("bob", "long", "twintails"):
            for side, sg in (("L", -1), ("R", 1)):
                x0 = sg * hx * 0.92
                y0, y1 = cy + hy * 0.34, ey - (0.075 if style == "long" else 0.045) * hs
                x1 = sg * hx * (1.02 if style == "long" else 0.98)
                xm, ym = (x0 + x1) * 0.5, (y0 + y1) * 0.5
                pts = [(x0, y0, face_z(x0, y0)), (xm, ym, face_z(xm, ym) + 0.006),
                       (x1, y1, face_z(x1, y1) + 0.004)]
                lock = Chain([B["Head"]], pts, [0], None)
                body_tube(m, lock, [(0.0, 0.020 * hs, 0.014 * hs),
                                    (lock.total * 0.62, 0.015 * hs, 0.010 * hs),
                                    (lock.total, 0.002, 0.0015)], CID["hair"],
                          max(8, self.sf + 2), self.R(10), dome=(False, True))

        def chain_bones(prefix, pts_nodes):
            names = []
            parent = "Head"
            for k, p in enumerate(pts_nodes):
                nm = "%s_%02d" % (prefix, k + 1)
                i = self.skel.add(nm, self.B[parent], p)
                self.B[nm] = i
                names.append(nm)
                parent = nm
            return names

        def hair_chain(prefix, pts_nodes, keys_fn, post=0.04, sides=None, cidfn=None, kind="hair"):
            names = chain_bones(prefix, pts_nodes)
            ch = axis_chain([self.B[n] for n in names], pts_nodes, self.B["Head"], post=post)
            keys = keys_fn(ch)
            body_tube(m, ch, keys, cidfn or CID["hair"], sides or self.sf + 4, self.R(12), dome=(False, True))
            self.physbones.append({"root": names[0], "kind": kind, "bones": names})

        if style in ("long", "bob"):
            drops = [0.0, -0.11, -0.22, -0.34, -0.46] if style == "long" else [0.0, -0.08, -0.16]
            nodes = [(0.0, cy - 0.01 * hs + dy, -hz * 0.95 - 0.01 * k) for k, dy in enumerate(drops)]
            w0 = 0.105 * hs

            def keys_back(ch, w0=w0):
                tot = ch.total
                return [(0.0, w0, 0.030), (tot * 0.5, w0 * 0.93, 0.024), (tot, w0 * 0.75, 0.015)]
            hair_chain("Hair_Back", nodes, keys_back, sides=self.sd)
        if style == "long":
            for side, sg in (("L", -1), ("R", 1)):
                nodes = [(sg * hx * 0.97, cy - 0.04 * hs - 0.10 * k, 0.030 * hs + 0.004 * k) for k in range(3)]
                hair_chain("Hair_Side_" + side, nodes,
                           lambda ch: [(0.0, 0.026, 0.020), (ch.total, 0.012, 0.010)], post=0.04)
        if style == "ponytail":
            base = [(0.0, cy + 0.035 * hs, -hz * 0.98), (0.0, cy + 0.020 * hs, -hz * 1.55),
                    (0.0, cy - 0.040 * hs, -hz * 1.85), (0.0, cy - 0.120 * hs, -hz * 1.85),
                    (0.0, cy - 0.200 * hs, -hz * 1.75)]
            hair_chain("Hair_Pony", base,
                       lambda ch: [(0.0, 0.026, 0.026), (ch.total * 0.12, 0.020, 0.020),
                                   (ch.total * 0.4, 0.036, 0.036), (ch.total, 0.012, 0.012)],
                       post=0.05, sides=self.sd - 2,
                       cidfn=lambda u: CID["accent"] if u < 0.04 else CID["hair"])
        if style == "twintails":
            for side, sg in (("L", -1), ("R", 1)):
                base = [(sg * hx * 1.05, cy + 0.045 * hs, -0.030 * hs), (sg * hx * 1.30, cy + 0.010 * hs, -0.045 * hs),
                        (sg * hx * 1.45, cy - 0.070 * hs, -0.050 * hs), (sg * hx * 1.50, cy - 0.160 * hs, -0.050 * hs),
                        (sg * hx * 1.50, cy - 0.250 * hs, -0.045 * hs)]
                hair_chain("Hair_Twin_" + side, base,
                           lambda ch: [(0.0, 0.030, 0.030), (ch.total * 0.5, 0.032, 0.032), (ch.total, 0.012, 0.012)],
                           post=0.05, sides=self.sd - 2,
                           cidfn=lambda u: CID["accent"] if u < 0.035 else CID["hair"])
        if style == "spiky":
            for _ in range(9):
                th = self.rng.uniform(0.15, 1.15)
                ph = self.rng.uniform(0, 2 * math.pi)
                d = (math.sin(th) * math.sin(ph), math.cos(th), math.sin(th) * math.cos(ph))
                if d[2] > 0.5 and d[1] < 0.75:
                    continue
                base = (d[0] * hx * 1.0, cy + d[1] * hy * 1.0, d[2] * hz * 1.0 - 0.006)
                Ls = self.rng.uniform(0.07, 0.11) * hs
                ch = Chain([B["Head"]], [base, add(base, mul(d, Ls))], [0], None)
                body_tube(m, ch, [(0.0, 0.030 * hs, 0.030 * hs), (ch.total, 0.002, 0.002)], CID["hair"], 6, 4,
                          dome=(False, False))
        return m

    # ---------------------------------------------------------------- orelhas animais / cauda
    def _ears(self):
        s, B = self.s, self.B
        if s.ears not in ("cat", "fox", "bunny"):
            return None
        hs = s.head_size
        hx, hy, hz = self.hr
        m = Mesh("Ears", "Orelhas", "accessory")
        k, w0 = {"cat": (1.0, 0.034), "fox": (1.35, 0.042), "bunny": (2.1, 0.026)}[s.ears]
        for side, sg in (("L", -1), ("R", 1)):
            x0 = sg * 0.062 * hs
            yy = self.hcy + hy * math.sqrt(max(0.0, 1 - (x0 / hx) ** 2 - (0.004 / hz) ** 2))
            base = (x0, yy - 0.015, -0.004)
            tip = add(base, (sg * 0.028 * k * (0.5 if s.ears == "bunny" else 1.0), 0.115 * k,
                             -0.010 * k * (2.5 if s.ears == "bunny" else 1.0)))
            mid = lerp(base, tip, 0.5)
            n1, n2 = "Ear_%s_01" % side, "Ear_%s_02" % side
            i1 = self.skel.add(n1, B["Head"], base)
            B[n1] = i1
            i2 = self.skel.add(n2, i1, mid)
            B[n2] = i2
            ch = Chain([i1, i2], [base, mid, tip], [0, 1], B["Head"])
            L = ch.total
            keys = [(0.0, w0 * hs, 0.011), (L * 0.5, w0 * 0.75 * hs, 0.009), (L, 0.004, 0.003)]
            outer = (lambda u, L=L: CID["hair_dark"] if u > 0.72 * L else CID["hair"]) if s.ears == "fox" else CID["hair"]
            body_tube(m, ch, keys, outer, self.sf + 3, self.R(8), dome=(False, True))
            body_tube(m, ch, keys, CID["ear_inner"], self.sf + 3, self.R(8), u1=L * 0.93, dome=(False, False),
                      offset=(0, 0, 0.0055), scale=0.62)
            self.physbones.append({"root": n1, "kind": "ear", "bones": [n1, n2]})
        return m

    def _tail(self):
        s, B = self.s, self.B
        if s.tail == "none":
            return None
        m = Mesh("Tail", "Cauda", "accessory")
        by, bz = self.hip_y - 0.01, -0.085
        n = 6
        pts = []
        for i in range(n):
            t = i / (n - 1)
            if s.tail == "cat":
                p = (0.0, by - 0.02 * t + 0.34 * t * t, bz - 0.30 * t)
            elif s.tail == "fox":
                p = (0.0, by + 0.10 * t - 0.06 * t * t, bz - 0.44 * t)
            else:
                p = (0.0, by + 0.20 * t, bz - 0.15 * t)
            pts.append(p)
        names, parent = [], "Hips"
        for i, p in enumerate(pts):
            nm = "Tail_%02d" % (i + 1)
            B[nm] = self.skel.add(nm, B[parent], p)
            names.append(nm)
            parent = nm
        ch = axis_chain([B[x] for x in names], pts, B["Hips"], post=0.04)
        L = ch.total
        if s.tail == "fox":
            keys = [(0.0, 0.035, 0.035), (L * 0.35, 0.062, 0.062), (L * 0.7, 0.060, 0.060), (L, 0.012, 0.012)]
            col = lambda u: CID["tail_tip"] if u > 0.78 * L else CID["hair"]
        elif s.tail == "dog":
            keys = [(0.0, 0.032, 0.032), (L * 0.5, 0.026, 0.026), (L, 0.012, 0.012)]
            col = lambda u: CID["tail_tip"] if u > 0.85 * L else CID["hair"]
        else:
            keys = [(0.0, 0.030, 0.030), (L * 0.6, 0.026, 0.026), (L, 0.016, 0.016)]
            col = lambda u: CID["accent"] if u > 0.88 * L else CID["hair"]
        body_tube(m, ch, keys, col, self.sd - 2, self.R(16), dome=(True, True))
        self.physbones.append({"root": names[0], "kind": "tail", "bones": names})
        return m

    # ---------------------------------------------------------------- roupas
    def _top(self):
        s, B = self.s, self.B
        if s.top == "none":
            return None
        m = Mesh("Top", "Parte de cima", "clothes")
        g = 0.007
        shirt_top = {"hoodie": 0.445, "tshirt": 0.435, "longsleeve": 0.435, "tank": 0.385}[s.top]
        u0, u1 = (0.15 if s.bottom == "skirt" else 0.10), 0.07 + shirt_top
        hem = u0 + 0.03
        body_tube(m, self.torso, self.torso_keys, lambda u: CID["top_accent"] if u < hem else CID["top"],
                  self.sd, self.R(24), u0=u0, u1=u1, grow=g)
        if s.top in ("tshirt", "longsleeve", "hoodie"):
            for side in ("L", "R"):
                ch, keys = getattr(self, "arm_" + side)
                n0, n1, n2 = ch.node_u
                end = n0 + 0.55 * (n1 - n0) if s.top == "tshirt" else n2 - 0.012
                cuff = end - (0.025 if s.top == "tshirt" else 0.03)
                body_tube(m, ch, keys, lambda u, cuff=cuff: CID["top_accent"] if u > cuff else CID["top"],
                          self.sd, self.R(14), u0=0.02, u1=end, grow=g + 0.002)

        # Tailored neckline and small construction details make the clothing read as fabric.
        collar_y = self.neck_y + 0.012
        add_torus(m, (0.0, collar_y, 0.0), 0.045 * s.head_size, 0.0045, CID["top_accent"],
                  [(B["UpperChest"], 1.0)], seg=max(24, self.sd * 2), seg_small=7,
                  rot=lambda v: rot_x(v, math.pi / 2))
        if s.top == "hoodie":
            # Hood volume sits behind the neck; drawstrings and pouch sit on the front.
            add_ellipsoid(m, (0.0, self.neck_y + 0.018, -0.079), (0.056, 0.052, 0.024),
                          CID["top"], [(B["UpperChest"], 1.0)], self.sd, max(8, self.sd // 2))
            zipline = Chain([B["Spine"], B["Chest"]],
                            [(0.0, self.chest_y + 0.012, 0.108), (0.0, self.spine_y + 0.045, 0.106)], [0, 1], None)
            body_tube(m, zipline, [(0.0, 0.0016, 0.0013), (zipline.total, 0.0014, 0.0012)],
                      CID["top_accent"], 7, 10, dome=(False, True))
            # Pequeno puxador de zíper integrado à linha central.
            add_ellipsoid(m, (0.0, self.spine_y + 0.051, 0.110), (0.0035, 0.006, 0.0018),
                          CID["metal"], [(B["Spine"], 1.0)], 8, 5)

        return m

    def _bottom(self):
        s = self.s
        if s.bottom == "none":
            return None
        m = Mesh("Bottom", "Parte de baixo", "clothes")
        g = 0.004
        waist_u = 0.07 + 0.085
        if s.bottom == "skirt":
            self._skirt(m, waist_u, g)
            return m
        body_tube(m, self.torso, self.torso_keys,
                  lambda u: CID["bottom_accent"] if u > waist_u - 0.025 else CID["bottom"],
                  self.sd, self.R(8), u0=0.0, u1=waist_u, grow=g)
        for side in ("L", "R"):
            ch, keys = getattr(self, "leg_" + side)
            n0, n1, n2 = ch.node_u
            end = n0 + 0.55 * (n1 - n0) if s.bottom == "shorts" else n2 - 0.004
            hem = end - 0.03
            body_tube(m, ch, keys, lambda u, hem=hem: CID["bottom_accent"] if u > hem else CID["bottom"],
                      self.sd, self.R(12), u0=0.0, u1=end, grow=g, caps=(True, False))
        return m

    def _skirt(self, m, waist_u, g):
        """Saia evasê: cobre o topo das coxas; cintura presa ao quadril, a barra acompanha as pernas."""
        B, s = self.B, self.s
        hw, th = s.hip_width, s.limb_thickness
        body_tube(m, self.torso, self.torso_keys,
                  lambda u: CID["bottom_accent"] if u > waist_u - 0.025 else CID["bottom"],
                  self.sd, self.R(5), u0=0.10, u1=waist_u, grow=g)
        h = self.hip_y
        y_w, y_top, y_hem = h + 0.085, h + 0.045, h - 0.20
        tru, trv = profile(self.torso_keys, 0.07 + (y_top - h))
        rx1 = max(tru, self.leg_x + 0.078 * th) + g + 0.006
        rz1 = max(trv, 0.078 * th) + g + 0.006
        wru, wrv = profile(self.torso_keys, waist_u)
        rings = [(y_w, wru + g, wrv + g, 0.0), (y_top, rx1, rz1, 0.0), (h - 0.06, rx1 * 1.12, rz1 * 1.10, 0.4),
                 (y_hem, rx1 * 1.42, rz1 * 1.30, 1.0)]
        n = self.sd + 2
        rows = []
        for ri, (y, rx, rz, t) in enumerate(rings):
            row = []
            for j in range(n):
                a = 2 * math.pi * j / n
                x, z = rx * math.sin(a), rz * math.cos(a)
                leg = B["UpperLeg_R"] if x > 0 else B["UpperLeg_L"]
                wl = 0.7 * smooth(t) * smooth(abs(x) / 0.06)
                color = CID["bottom_accent"] if ri == len(rings) - 1 else CID["bottom"]
                row.append(m.vertex((x, y, z), norm((x / rx, 0.25 if ri else 0.0, z / rz)), color,
                                    [(B["Hips"], 1.0 - wl), (leg, wl)]))
            rows.append(row)
        for i in range(len(rows) - 1):
            for j in range(n):
                j2 = (j + 1) % n
                m.tri(rows[i][j], rows[i + 1][j], rows[i + 1][j2])
                m.tri(rows[i][j], rows[i + 1][j2], rows[i][j2])

        # Fine front pleats, weighted to the hips so they remain stable when animated.
        for k in range(-4, 5):
            a = k * 0.13
            pts = []
            for t in (0.08, 0.35, 0.68, 0.94):
                y = y_top + (y_hem - y_top) * t
                rx = rx1 * (1.0 + 0.42 * t)
                rz = rz1 * (1.0 + 0.30 * t)
                x, z = rx * math.sin(a), rz * math.cos(a) + 0.0025
                pts.append((x, y, z))
            seam = Chain([B["Hips"]], pts, [0], None)
            body_tube(m, seam, [(0.0, 0.00085, 0.0007), (seam.total, 0.0007, 0.0006)],
                      CID["bottom_accent"], 5, 8, dome=(False, False))

    def _shoes(self):
        s, B = self.s, self.B
        if s.shoes == "none":
            return None
        m = Mesh("Shoes", "Calçado", "clothes")
        for side, sg in (("L", -1), ("R", 1)):
            fch, fkeys = getattr(self, "foot_" + side)
            body_tube(m, fch, fkeys, CID["shoes"], max(8, self.sd - 2), self.R(10), grow=0.006, dome=(True, True))
            fb, tb = B["Foot_" + side], B["Toes_" + side]

            def wsole(z):
                t = smooth((z - 0.03) / 0.08)
                return [(fb, 1.0 - t), (tb, t)]
            # sola: várias fatias para os pesos acompanharem a dobra do pé
            x = sg * self.leg_x
            for zc, rz in ((-0.005, 0.060), (0.075, 0.055), (0.140, 0.050)):
                add_ellipsoid(m, (x, 0.007, zc), (0.047, 0.011, rz), CID["sole"], wsole(zc), 14, 7)
            if s.shoes == "sneakers":
                # Toe cap, tongue and visible laces give the shoe a sneaker silhouette.
                add_ellipsoid(m, (x, 0.035, 0.133), (0.034, 0.017, 0.043), CID["sole"],
                              [(fb, 0.55), (tb, 0.45)], 16, 8)
                add_ellipsoid(m, (x, 0.050, 0.064), (0.018, 0.018, 0.033), CID["shoes"],
                              [(fb, 0.65), (tb, 0.35)], 12, 7)
                for j in range(4):
                    z = 0.045 + j * 0.018
                    lace = Chain([fb, tb], [(x - 0.014, 0.062 - j * 0.001, z),
                                            (x + 0.014, 0.062 - j * 0.001, z + 0.003)], [0, 1], None)
                    body_tube(m, lace, [(0.0, 0.0022, 0.0017), (lace.total, 0.0022, 0.0017)],
                              CID["sole"], 6, 5, dome=(False, False))
                add_ellipsoid(m, (x, 0.050, 0.102), (0.008, 0.007, 0.006), CID["accent"],
                              [(tb, 1.0)], 8, 5)
            if s.shoes == "boots":
                ch, keys = getattr(self, "leg_" + side)
                n2 = ch.node_u[2]
                body_tube(m, ch, keys, CID["shoes"], self.sd, self.R(8), u0=n2 - 0.20, u1=n2 + 0.0,
                          grow=0.006)
        return m

    # ---------------------------------------------------------------- acessórios
    def _glasses(self):
        s, B = self.s, self.B
        if not s.glasses:
            return None
        hs, es = s.head_size, s.eye_size
        m = Mesh("Glasses", "Óculos", "accessory")
        Hj = [(B["Head"], 1.0)]
        ex, ey = self.eye_x, self.eye_y
        for sg in (-1, 1):
            c = (sg * ex, ey, self.hz(sg * ex, ey) + 0.020 * hs)
            rot = self.surf_rot(sg * ex, ey)
            add_torus(m, c, 0.036 * hs * max(es, 0.9), 0.0028, CID["metal"], Hj, 22, 5, rot)
            hx = self.hr[0]
            back = (sg * hx * 0.99, ey, -0.01)
            front = (sg * (ex + 0.036 * hs * max(es, 0.9)), ey, c[2] - 0.004)
            ch = Chain([B["Head"]], [front, back], [0], None)
            body_tube(m, ch, [(0.0, 0.0028, 0.0028), (ch.total, 0.0028, 0.0028)], CID["metal"], 5, 4)
        bridge = Chain([B["Head"]], [(-0.012 * hs, ey + 0.006, self.hz(0, ey) + 0.019 * hs),
                                    (0.012 * hs, ey + 0.006, self.hz(0, ey) + 0.019 * hs)], [0], None)
        body_tube(m, bridge, [(0.0, 0.0025, 0.0025), (bridge.total, 0.0025, 0.0025)], CID["metal"], 5, 3)
        return m

    def _headphones(self):
        s, B = self.s, self.B
        if not s.headphones:
            return None
        hx, hy, hz = self.hr
        cy = self.hcy
        m = Mesh("Headphones", "Fones de ouvido", "accessory")
        Hj = [(B["Head"], 1.0)]
        pts = []
        for i in range(11):
            a = math.radians(-92 + 184 * i / 10)
            pts.append(((hx + 0.024) * math.sin(a), cy - 0.012 + (hy + 0.024) * math.cos(a) * 0.98, -0.004))
        ch = Chain([B["Head"]], pts, [0], None)
        body_tube(m, ch, [(0.0, 0.0065, 0.010), (ch.total, 0.0065, 0.010)], CID["metal"], 8, 20)
        for sg in (-1, 1):
            add_ellipsoid(m, (sg * (hx + 0.026), cy - 0.014, -0.004), (0.020, 0.042, 0.038), CID["accent"], Hj, 12, 8)
        return m

    def _beanie(self):
        s, B = self.s, self.B
        if not s.beanie:
            return None
        hx, hy, hz = self.hr
        m = Mesh("Beanie", "Gorro", "accessory")
        Hj = [(B["Head"], 1.0)]
        add_ellipsoid(m, (0, self.hcy + 0.012, -0.006), (hx * 1.13, hy * 1.12, hz * 1.13), CID["bottom"], Hj,
                      seg=self.hc[0], rings=self.hc[1], th1=1.95)
        add_ellipsoid(m, (0, self.hcy + hy * 1.12 + 0.016, -0.006), (0.028, 0.026, 0.028), CID["accent"], Hj, 10, 6)
        return m

    # ---------------------------------------------------------------- montagem
    def build(self):
        s = self.s
        self.humanoid, self.physbones = [], []
        self._dims()
        self._skeleton()
        body = Mesh("Body", "Corpo", "body", toggle=False)
        self._body(body)
        self._face(body)
        extra = [self._hair(), self._ears(), self._tail(), self._top(), self._bottom(), self._shoes(),
                 self._glasses(), self._headphones(), self._beanie()]
        meshes = [body] + [e for e in extra if e is not None]
        meshes += build_part_meshes(self)
        # a ordem dos ossos mudou? (cabelo/orelhas/cauda acrescentam ossos) — nada a refazer: índices são estáveis
        for mm in meshes:
            mm.finalize()
        self._shapes(body)
        if s.merge_meshes:
            for mm in meshes[1:]:
                body.append(mm)
            meshes = [body]

        # escala final: "altura" = topo da cabeça
        top_y = self.hcy + self.hr[1]
        S = self.S
        av = Avatar()
        av.scale = S
        for mm in meshes:
            mm.pos = [mul(p, S) for p in mm.pos]
            for d in mm.shapes.values():
                for i in d:
                    d[i] = mul(d[i], S)
        sk = self.skel
        sk.pos = [mul(p, S) for p in sk.pos]
        av.skeleton = sk
        av.meshes = meshes
        av.palette = build_palette(s, list(self.extra))
        av.humanoid = list(self.humanoid)
        av.physbones = list(self.physbones)
        ey = self.eye_y * S
        av.view_position = (0.0, round(ey, 4), round(self.hz(0, self.eye_y) * 0.6 * S, 4))
        av.spec = s
        return av


def build_avatar(spec_or_dict, detail=None):
    spec = spec_or_dict if isinstance(spec_or_dict, SimpleNamespace) else make_spec(spec_or_dict)
    return AvatarBuilder(spec, detail).build()

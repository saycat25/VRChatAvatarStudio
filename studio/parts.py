# -*- coding: utf-8 -*-
"""Peças personalizadas: acessórios, roupas extras e qualquer objeto que o usuário queira criar.

Cada peça é um dicionário simples (guardado no preset):
    id, name, group, shape, bone, pos[3], rot[3], size[3], color, mirror, jiggle, obj

* pos  = deslocamento em metros a partir da origem do osso (para "Head" a origem é o CENTRO da cabeça)
* rot  = graus, mesma ordem do Unity (Z, depois X, depois Y)
* size = extensões totais em metros
* mirror = cria uma cópia espelhada no outro lado (osso _L <-> _R)
* jiggle = a peça ganha um osso próprio com PhysBone (balança)
* peças com o mesmo "group" viram UMA malha (um material, um objeto que liga/desliga no menu)
"""
import math
import re
import unicodedata

from .geometry import (Mesh, add, sub, mul, norm, cross, dot, rot_x, rot_y, rot_z, add_ellipsoid, add_box,
                       add_prism, add_ellipse_loop, add_extrude, star_outline, heart_outline)

SHAPES = [("sphere", "Esfera / elipsoide"), ("box", "Caixa"), ("cylinder", "Cilindro"), ("cone", "Cone"),
          ("ring", "Anel / argola"), ("star", "Estrela"), ("heart", "Coração"), ("obj", "Modelo OBJ importado")]

BONES = [("Head", "Cabeça (origem no centro)"), ("Neck", "Pescoço"), ("UpperChest", "Peito / costas altas"),
         ("Chest", "Tórax"), ("Spine", "Cintura"), ("Hips", "Quadril"),
         ("UpperArm_R", "Braço superior direito"), ("UpperArm_L", "Braço superior esquerdo"),
         ("LowerArm_R", "Antebraço direito"), ("LowerArm_L", "Antebraço esquerdo"),
         ("Hand_R", "Mão direita"), ("Hand_L", "Mão esquerda"),
         ("UpperLeg_R", "Coxa direita"), ("UpperLeg_L", "Coxa esquerda"),
         ("LowerLeg_R", "Canela direita"), ("LowerLeg_L", "Canela esquerda"),
         ("Foot_R", "Pé direito"), ("Foot_L", "Pé esquerdo")]
BONE_IDS = [b for b, _ in BONES]

MAX_PARTS = 80
MAX_OBJ_CHARS = 2_000_000
MAX_OBJ_FACES = 20000
MAX_OBJ_VERTICES = 100000

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _f3(v, lo, hi, dflt):
    try:
        out = [float(x) for x in v][:3]
        if len(out) != 3:
            raise ValueError
    except (TypeError, ValueError):
        out = list(dflt)
    return [max(lo, min(hi, x)) for x in out]


def safe_name(s, fallback="Extra"):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9_]", "", s.replace(" ", "_"))
    return s[:24] or fallback


def sanitize_parts(raw):
    """Valida a lista de peças vinda do usuário (UI, arquivo de preset...)."""
    out, seen = [], set()
    if not isinstance(raw, list):
        return out
    for i, p in enumerate(raw[:MAX_PARTS]):
        if not isinstance(p, dict):
            continue
        pid = re.sub(r"[^A-Za-z0-9]", "", str(p.get("id", ""))) or "p%d" % (i + 1)
        pid = pid[:12]
        while pid in seen:
            pid += "x"
        seen.add(pid)
        shape = p.get("shape", "sphere")
        shape = shape if shape in [s for s, _ in SHAPES] else "sphere"
        bone = p.get("bone", "Head")
        bone = bone if bone in BONE_IDS else "Head"
        color = str(p.get("color", "#ffffff"))
        item = {
            "id": pid,
            "name": (re.sub(r"[\r\n\t]", " ", str(p.get("name", "Peça %d" % (i + 1)))).strip()[:40] or "Peça"),
            "group": (re.sub(r"[\r\n\t]", " ", str(p.get("group", "Acessorios"))).strip()[:24] or "Acessorios"),
            "shape": shape, "bone": bone,
            "pos": _f3(p.get("pos"), -3, 3, (0, 0, 0)),
            "rot": _f3(p.get("rot"), -720, 720, (0, 0, 0)),
            "size": _f3(p.get("size"), 0.002, 3, (0.05, 0.05, 0.05)),
            "color": color if _HEX.match(color) else "#ffffff",
            "mirror": bool(p.get("mirror", False)),
            "jiggle": bool(p.get("jiggle", False)),
            "visible": bool(p.get("visible", True)),
            "locked": bool(p.get("locked", False)),
            "preserve_proportions": bool(p.get("preserve_proportions", True)),
        }
        if shape == "obj":
            obj = p.get("obj", "")
            item["obj"] = obj[:MAX_OBJ_CHARS] if isinstance(obj, str) else ""
        out.append(item)
    return out


# --------------------------------------------------------------------------- OBJ

def parse_obj_detailed(text, max_faces=MAX_OBJ_FACES):
    """Lê OBJ poligonal e retorna geometria mais diagnóstico.

    Suporta v/vt/vn na sintaxe das faces, índices positivos/negativos e
    triangulação em leque. MTL, UVs e normais de origem são deliberadamente
    ignorados: o Studio recalcula normais e usa sua paleta própria.
    """
    issues = []
    verts, tris = [], []
    ignored_faces = 0
    polygon_count = 0
    if not isinstance(text, str):
        return [], [], ["conteúdo OBJ não é texto"], {"vertices": 0, "faces": 0, "triangles": 0}
    if len(text) > MAX_OBJ_CHARS:
        return [], [], ["arquivo excede o limite de 2 MB"], {"vertices": 0, "faces": 0, "triangles": 0}

    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        fields = line.split()
        tag = fields[0]
        if tag == "v":
            if len(fields) < 4:
                issues.append("linha %d: vértice sem três coordenadas" % line_no)
                continue
            try:
                v = tuple(float(x) for x in fields[1:4])
            except ValueError:
                issues.append("linha %d: coordenada de vértice inválida" % line_no)
                continue
            if not all(math.isfinite(x) for x in v):
                issues.append("linha %d: vértice contém NaN/infinito" % line_no)
                continue
            verts.append(v)
            if len(verts) > MAX_OBJ_VERTICES:
                issues.append("limite de %d vértices excedido" % MAX_OBJ_VERTICES)
                break
        elif tag == "f":
            polygon_count += 1
            if len(fields) < 4:
                ignored_faces += 1
                issues.append("linha %d: face precisa de ao menos três vértices" % line_no)
                continue
            face = []
            malformed = False
            for token in fields[1:]:
                raw_index = token.split("/", 1)[0]
                try:
                    index = int(raw_index)
                except ValueError:
                    malformed = True
                    break
                # OBJ usa índices 1-based positivos ou relativos negativos.
                resolved = index - 1 if index > 0 else len(verts) + index
                if index == 0 or resolved < 0 or resolved >= len(verts):
                    malformed = True
                    break
                face.append(resolved)
            if malformed or len(set(face)) < 3:
                ignored_faces += 1
                issues.append("linha %d: índice de face inválido ou repetido" % line_no)
                continue
            before = len(tris)
            for j in range(1, len(face) - 1):
                tri = (face[0], face[j], face[j + 1])
                a, b, c = (verts[i] for i in tri)
                ab = (b[0]-a[0], b[1]-a[1], b[2]-a[2])
                ac = (c[0]-a[0], c[1]-a[1], c[2]-a[2])
                cross_v = (ab[1]*ac[2]-ab[2]*ac[1], ab[2]*ac[0]-ab[0]*ac[2], ab[0]*ac[1]-ab[1]*ac[0])
                if sum(x*x for x in cross_v) <= 1e-18:
                    continue
                tris.append(tri)
                if len(tris) >= max_faces:
                    issues.append("limite de %d triângulos atingido; restante ignorado" % max_faces)
                    break
            if len(tris) == before:
                ignored_faces += 1
                issues.append("linha %d: face degenerada" % line_no)
            if len(tris) >= max_faces:
                break
        # vt, vn, o/g/s/usemtl/mtllib são reconhecidos, mas o importador não os aplica.

    if not verts:
        issues.append("arquivo não contém vértices válidos")
    if not tris:
        issues.append("arquivo não contém faces trianguláveis")
    if any(line.lstrip().startswith("mtllib ") for line in text.splitlines()):
        issues.append("materiais MTL não são importados; será usada a paleta do Studio")
    info = {"vertices": len(verts), "faces": polygon_count, "triangles": len(tris),
            "ignored_faces": ignored_faces}
    return verts, tris, issues, info


def parse_obj(text, max_faces=MAX_OBJ_FACES):
    """Compatibilidade com chamadas antigas: retorna apenas vértices e triângulos."""
    verts, tris, _, _ = parse_obj_detailed(text, max_faces=max_faces)
    return verts, tris


def add_obj(mesh, text, c, size, cid, jw, rot=None, crease_deg=40.0):
    """Importa um OBJ: centraliza, normaliza (maior dimensão = 1), multiplica por size, converte a
    lateralidade (OBJ é destro, Unity é canhoto: X é invertido, como no importador do Unity)."""
    verts, tris = parse_obj(text)
    if not tris:
        return 0
    lo = [min(v[i] for v in verts) for i in range(3)]
    hi = [max(v[i] for v in verts) for i in range(3)]
    ctr = [(lo[i] + hi[i]) / 2 for i in range(3)]
    ext = max(hi[i] - lo[i] for i in range(3)) or 1.0
    P = []
    preserve = bool(getattr(mesh, "preserve_obj_proportions", True))
    scale = (max(size),) * 3 if preserve else size
    for v in verts:
        q = ((v[0] - ctr[0]) / ext * scale[0] * -1.0, (v[1] - ctr[1]) / ext * scale[1], (v[2] - ctr[2]) / ext * scale[2])
        P.append(rot(q) if rot else q)
    T = [(a, c_, b) for a, b, c_ in tris]           # inverte o sentido por causa do X invertido
    fn = []
    for a, b, d in T:
        n = cross(sub(P[b], P[a]), sub(P[d], P[a]))
        fn.append(norm(n) if dot(n, n) > 1e-18 else (0.0, 1.0, 0.0))
    inc = {}
    for fi, (a, b, d) in enumerate(T):
        for v in (a, b, d):
            inc.setdefault(v, []).append(fi)
    cos_c = math.cos(math.radians(crease_deg))
    cache = {}
    for fi, tri in enumerate(T):
        ids = []
        for v in tri:
            acc = (0.0, 0.0, 0.0)
            for fj in inc[v]:
                if dot(fn[fj], fn[fi]) >= cos_c:
                    acc = add(acc, fn[fj])
            nrm = norm(acc)
            key = (v, round(nrm[0] * 8), round(nrm[1] * 8), round(nrm[2] * 8))
            if key not in cache:
                cache[key] = mesh.vertex(add(c, P[v]), nrm, cid, jw)
            ids.append(cache[key])
        mesh.tri(*ids)
    return len(T)


# --------------------------------------------------------------------------- construção

def _rot_fn(rot_deg):
    rx, ry, rz = (math.radians(a) for a in rot_deg)
    return lambda v: rot_y(rot_x(rot_z(v, rz), rx), ry)


def swap_side(bone):
    if bone.endswith("_L"):
        return bone[:-2] + "_R"
    if bone.endswith("_R"):
        return bone[:-2] + "_L"
    return bone


def _origin(b, bone):
    if bone == "Head":
        return (0.0, b.hcy, 0.0)
    return b.skel.pos[b.B[bone]]


def _emit_shape(b, tmp, p, c, size, cid, jw):
    R = _rot_fn(p["rot"])
    sd = b.sd
    shape = p["shape"]
    if shape == "sphere":
        add_ellipsoid(tmp, c, (size[0] / 2, size[1] / 2, size[2] / 2), cid, jw, seg=max(8, sd),
                      rings=max(5, sd // 2 + 1), rot=R)
    elif shape == "box":
        add_box(tmp, c, size, cid, jw, R)
    elif shape == "cylinder":
        add_prism(tmp, c, size, cid, jw, sides=max(8, sd), rot=R)
    elif shape == "cone":
        add_prism(tmp, c, size, cid, jw, sides=max(8, sd), top=0.0, rot=R)
    elif shape == "ring":
        add_ellipse_loop(tmp, c, size[0], size[1], size[2], cid, jw, R, seg=max(18, sd * 2))
    elif shape == "star":
        add_extrude(tmp, c, size, star_outline(), cid, jw, R)
    elif shape == "heart":
        add_extrude(tmp, c, size, heart_outline(), cid, jw, R)
    elif shape == "obj":
        add_obj(tmp, p.get("obj", ""), c, size, cid, jw, R)


def build_part_meshes(b):
    """Cria as malhas das peças do usuário (uma por grupo). Pode acrescentar ossos de balanço ao esqueleto."""
    parts = getattr(b.s, "parts", None) or []
    groups, order = {}, []
    S = b.S
    for p in parts:
        if not p.get("visible", True):
            continue
        g = p["group"]
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append(p)
    meshes, used_names = [], set()
    for g in order:
        name = "Acc_" + safe_name(g)
        base, n = name, 2
        while name in used_names:
            name = "%s%d" % (base, n)
            n += 1
        used_names.add(name)
        mesh = Mesh(name, g, "accessory", toggle=True)
        for p in groups[g]:
            for mirror in ((False, True) if p["mirror"] else (False,)):
                bone = swap_side(p["bone"]) if mirror else p["bone"]
                if bone not in b.B:
                    continue
                origin = _origin(b, p["bone"])
                c = add(origin, mul(tuple(p["pos"]), 1.0 / S))
                size = tuple(max(v / S, 1e-4) for v in p["size"])
                cid = b.color_cid(p["color"])
                bone_idx = b.B[bone]
                if p["jiggle"]:
                    bname = "Acc_%s%s" % (safe_name(p["id"], "x"), "_m" if mirror else "")
                    cw = (-c[0], c[1], c[2]) if mirror else c
                    if bname not in b.B:
                        b.B[bname] = b.skel.add(bname, bone_idx, cw)
                        b.physbones.append({"root": bname, "kind": "accessory", "bones": [bname],
                                            "extent": max(size) * 0.9})
                    bone_idx = b.B[bname]
                tmp = Mesh("tmp", "", "")
                tmp.preserve_obj_proportions = bool(p.get("preserve_proportions", True))
                _emit_shape(b, tmp, p, c, size, cid, [(bone_idx, 1.0)])
                # copia para a malha do grupo (refletindo X nas cópias espelhadas)
                off = len(mesh.pos)
                for i, pos in enumerate(tmp.pos):
                    ref = tmp.ref[i]
                    if mirror:
                        pos, ref = (-pos[0], pos[1], pos[2]), (-ref[0], ref[1], ref[2])
                    mesh.vertex(pos, ref, tmp.cid[i], tmp.joints[i], tmp.tags[i])
                mesh.tris += [i + off for i in tmp.tris]
        if mesh.tris:
            meshes.append(mesh)
    return meshes


# --------------------------------------------------------------------------- biblioteca de modelos prontos

def _P(name, shape, bone, pos, size, color, rot=(0, 0, 0), mirror=False, jiggle=False):
    return {"name": name, "shape": shape, "bone": bone, "pos": list(pos), "rot": list(rot),
            "size": list(size), "color": color, "mirror": mirror, "jiggle": jiggle}


def _ctx(b):
    k = b.S
    hx, hy, hz = (v * k for v in b.hr)
    return k, hx, hy, hz


def t_halo(b):
    k, hx, hy, hz = _ctx(b)
    return [_P("Auréola", "ring", "Head", (0, hy + 0.09 * k, -0.01), (2.0 * hx, 2.0 * hz, 0.016), "#ffe27a", rot=(90, 0, 0))]


def t_horns(b):
    k, hx, hy, hz = _ctx(b)
    return [_P("Chifre", "cone", "Head", (0.55 * hx, 0.93 * hy, 0.12 * hz), (0.40 * hx, 1.15 * hx, 0.40 * hx),
               "#e8e0cc", rot=(-8, 0, -24), mirror=True)]


def t_crown(b):
    k, hx, hy, hz = _ctx(b)
    y0 = 0.80 * hy
    out = [_P("Aro da coroa", "ring", "Head", (0, y0, 0), (1.55 * hx, 1.55 * hz, 0.10 * hx), "#f2c94c", rot=(90, 0, 0))]
    for i in range(5):
        a = 2 * math.pi * i / 5
        out.append(_P("Ponta %d" % (i + 1), "cone", "Head", (0.75 * hx * math.sin(a), y0 + 0.26 * hx, 0.75 * hz * math.cos(a)),
                      (0.30 * hx, 0.55 * hx, 0.30 * hx), "#f2c94c"))
    return out


def t_bow(b):
    k, hx, hy, hz = _ctx(b)
    c = (0.52 * hx, 0.70 * hy, 0.52 * hz)
    col = "#ff5f8f"
    return [_P("Nó", "sphere", "Head", c, (0.20 * hx, 0.20 * hx, 0.20 * hx), col),
            _P("Laço", "sphere", "Head", (c[0] + 0.30 * hx, c[1] + 0.10 * hx, c[2] + 0.05 * hx),
               (0.55 * hx, 0.38 * hx, 0.16 * hx), col, rot=(0, 0, 22)),
            _P("Laço 2", "sphere", "Head", (c[0] - 0.30 * hx, c[1] + 0.10 * hx, c[2] + 0.05 * hx),
               (0.55 * hx, 0.38 * hx, 0.16 * hx), col, rot=(0, 0, -22))]


def t_ahoge(b):
    k, hx, hy, hz = _ctx(b)
    return [_P("Antena de cabelo", "cone", "Head", (0, hy + 0.30 * hx, 0.18 * hz), (0.20 * hx, 0.85 * hx, 0.20 * hx),
               b.s.hair, rot=(-20, 0, 0), jiggle=True)]


def t_wizard_hat(b):
    k, hx, hy, hz = _ctx(b)
    y0 = 0.74 * hy
    return [_P("Aba", "cylinder", "Head", (0, y0, 0), (2.5 * hx, 0.03, 2.5 * hz), "#4b3a8f"),
            _P("Cone", "cone", "Head", (0, y0 + 1.15 * hx, -0.1 * hz), (1.55 * hx, 2.3 * hx, 1.55 * hz), "#4b3a8f",
               rot=(-6, 0, 0)),
            _P("Faixa", "ring", "Head", (0, y0 + 0.14 * hx, 0), (1.62 * hx, 1.62 * hz, 0.16 * hx), "#f2c94c",
               rot=(90, 0, 0))]


def t_top_hat(b):
    k, hx, hy, hz = _ctx(b)
    y0 = 0.74 * hy
    return [_P("Aba", "cylinder", "Head", (0, y0, 0), (2.3 * hx, 0.025, 2.3 * hz), "#23232b"),
            _P("Copa", "cylinder", "Head", (0, y0 + 0.62 * hx, 0), (1.55 * hx, 1.25 * hx, 1.55 * hz), "#23232b"),
            _P("Faixa", "cylinder", "Head", (0, y0 + 0.2 * hx, 0), (1.60 * hx, 0.22 * hx, 1.60 * hz), "#b3262e")]


def t_eyepatch(b):
    k, hx, hy, hz = _ctx(b)
    ex, ey = b.eye_x * k, (b.eye_y - b.hcy) * k
    z = b.hz(b.eye_x, b.eye_y) * k + 0.006
    return [_P("Tapa-olho", "sphere", "Head", (ex, ey, z), (0.062 * hx / 0.1, 0.074 * hx / 0.1, 0.02), "#1d1d26")]


def t_star_pin(b):
    k, hx, hy, hz = _ctx(b)
    return [_P("Presilha estrela", "star", "Head", (-0.62 * hx, 0.55 * hy, 0.60 * hz + 0.004), (0.55 * hx, 0.55 * hx, 0.10 * hx),
               "#ffd84a", rot=(0, -38, 12))]


def t_heart_pin(b):
    k, hx, hy, hz = _ctx(b)
    return [_P("Presilha coração", "heart", "Head", (-0.62 * hx, 0.55 * hy, 0.60 * hz + 0.004), (0.55 * hx, 0.55 * hx, 0.10 * hx),
               "#ff5f8f", rot=(0, -38, 12))]


def t_bowtie(b):
    return [_P("Nó", "sphere", "Neck", (0, -0.02, 0.058), (0.028, 0.028, 0.022), "#b3262e"),
            _P("Laço", "sphere", "Neck", (0.032, -0.02, 0.056), (0.05, 0.036, 0.016), "#b3262e", rot=(0, 0, 10), mirror=True)]


def t_scarf(b):
    return [_P("Cachecol", "ring", "Neck", (0, -0.012, 0), (0.19, 0.17, 0.06), "#d94a4a", rot=(90, 0, 0)),
            _P("Ponta", "box", "Neck", (0.06, -0.13, 0.082), (0.06, 0.22, 0.016), "#d94a4a", rot=(0, 0, 0), jiggle=True)]


def t_necklace(b):
    return [_P("Gargantilha", "ring", "Neck", (0, 0.004, 0), (0.13, 0.13, 0.009), "#2b2b33", rot=(90, 0, 0)),
            _P("Pingente", "heart", "Neck", (0, -0.048, 0.086), (0.032, 0.032, 0.012), "#ff5f8f", rot=(8, 0, 0))]


def t_bell_collar(b):
    return [_P("Coleira", "ring", "Neck", (0, 0.004, 0), (0.135, 0.135, 0.016), "#d94a4a", rot=(90, 0, 0)),
            _P("Sininho", "sphere", "Neck", (0, -0.028, 0.062), (0.03, 0.03, 0.03), "#f2c94c", jiggle=True)]


def t_bracelets(b):
    return [_P("Pulseira", "ring", "Hand_R", (-0.03, 0, 0), (0.07, 0.07, 0.014), "#ffb347", rot=(0, 90, 0), mirror=True)]


def t_shoulder_pads(b):
    return [_P("Ombreira", "sphere", "UpperArm_R", (0.0, 0.042, 0), (0.13, 0.075, 0.13), "#8a8fa3", mirror=True)]


def t_belt(b):
    k = b.S
    w = b.s.waist
    return [_P("Cinto", "ring", "Spine", (0, 0.01, 0), (2 * (0.11 * w + 0.02) * k, 2 * (0.083 * w + 0.02) * k, 0.022),
               "#4a3322", rot=(90, 0, 0)),
            _P("Fivela", "box", "Spine", (0, 0.01, (0.083 * w + 0.02) * k + 0.004), (0.045, 0.04, 0.012), "#f2c94c")]


def t_backpack(b):
    return [_P("Mochila", "box", "UpperChest", (0, -0.03, -0.145), (0.21, 0.27, 0.10), "#2e7d6b"),
            _P("Tampa", "box", "UpperChest", (0, 0.115, -0.145), (0.215, 0.05, 0.105), "#ffb347"),
            _P("Bolso", "box", "UpperChest", (0, -0.09, -0.205), (0.14, 0.10, 0.03), "#ffb347")]


def t_cape(b):
    return [_P("Capa", "box", "UpperChest", (0, -0.23, -0.115), (0.30, 0.52, 0.014), "#b3262e", jiggle=True),
            _P("Gola da capa", "ring", "Neck", (0, -0.012, 0), (0.2, 0.18, 0.03), "#b3262e", rot=(90, 0, 0))]


def t_wings_angel(b):
    c = "#f8f8ff"
    return [_P("Asa 1", "sphere", "UpperChest", (0.17, 0.09, -0.115), (0.28, 0.10, 0.014), c, rot=(0, 0, 28), mirror=True),
            _P("Asa 2", "sphere", "UpperChest", (0.16, 0.00, -0.120), (0.24, 0.09, 0.014), c, rot=(0, 0, 8), mirror=True),
            _P("Asa 3", "sphere", "UpperChest", (0.13, -0.08, -0.125), (0.19, 0.075, 0.014), c, rot=(0, 0, -14), mirror=True),
            _P("Base da asa", "sphere", "UpperChest", (0.05, 0.05, -0.105), (0.07, 0.09, 0.03), c, mirror=True)]


def t_wings_bat(b):
    c, m = "#2a1e3d", "#6a3f8f"
    base = (0.05, 0.07, -0.115)
    angs = (64, 88, 112)
    out = [_P("Ombro da asa", "sphere", "UpperChest", (0.045, 0.06, -0.11), (0.06, 0.06, 0.05), c, mirror=True)]
    for i, ang in enumerate(angs):
        a = math.radians(ang)
        d = (math.sin(a), math.cos(a))
        ln = 0.36 if i == 1 else 0.30
        out.append(_P("Dedo %d" % (i + 1), "cone", "UpperChest",
                      (base[0] + d[0] * ln / 2, base[1] + d[1] * ln / 2, base[2]), (0.026, ln, 0.026), c,
                      rot=(0, 0, -ang), mirror=True))
    for i, ang in enumerate((76, 100)):
        a = math.radians(ang)
        d = (math.sin(a), math.cos(a))
        out.append(_P("Membrana %d" % (i + 1), "sphere", "UpperChest",
                      (base[0] + d[0] * 0.15, base[1] + d[1] * 0.15, base[2] - 0.004), (0.30, 0.13, 0.008), m,
                      rot=(0, 0, 90 - ang), mirror=True))
    return out


def t_sword_back(b):
    ang = 35.0
    d = (-math.sin(math.radians(ang)), math.cos(math.radians(ang)), 0.0)
    ctr = (0.0, 0.05, -0.16)

    def at(t):
        return (ctr[0] + d[0] * t, ctr[1] + d[1] * t, ctr[2])
    return [_P("Lâmina", "box", "UpperChest", at(0.12), (0.042, 0.62, 0.009), "#c9d3e0", rot=(0, 0, ang)),
            _P("Guarda", "box", "UpperChest", at(-0.20), (0.13, 0.024, 0.03), "#f2c94c", rot=(0, 0, ang)),
            _P("Cabo", "cylinder", "UpperChest", at(-0.275), (0.026, 0.14, 0.026), "#4a3322", rot=(0, 0, ang))]


TEMPLATES = {
    "halo": ("Auréola", t_halo), "horns": ("Chifres", t_horns), "crown": ("Coroa", t_crown),
    "bow": ("Laço de cabelo", t_bow), "ahoge": ("Antena de cabelo (ahoge)", t_ahoge),
    "wizard_hat": ("Chapéu de bruxo", t_wizard_hat), "top_hat": ("Cartola", t_top_hat),
    "eyepatch": ("Tapa-olho", t_eyepatch), "star_pin": ("Presilha estrela", t_star_pin),
    "heart_pin": ("Presilha coração", t_heart_pin), "bowtie": ("Gravata borboleta", t_bowtie),
    "scarf": ("Cachecol", t_scarf), "necklace": ("Colar com pingente", t_necklace),
    "bell_collar": ("Coleira com sininho", t_bell_collar), "bracelets": ("Pulseiras", t_bracelets),
    "shoulder_pads": ("Ombreiras", t_shoulder_pads), "belt": ("Cinto", t_belt),
    "backpack": ("Mochila", t_backpack), "cape": ("Capa", t_cape),
    "wings_angel": ("Asas de anjo", t_wings_angel), "wings_bat": ("Asas de morcego", t_wings_bat),
    "sword_back": ("Espada nas costas", t_sword_back),
}


def template_list():
    return [{"id": k, "label": v[0]} for k, v in TEMPLATES.items()]


def expand_template(template_id, spec):
    """Gera a lista de peças (editáveis) de um modelo pronto, ajustada às medidas atuais do avatar."""
    from .builder import AvatarBuilder
    if template_id not in TEMPLATES:
        raise KeyError(template_id)
    b = AvatarBuilder(spec)
    b._dims()
    label, fn = TEMPLATES[template_id]
    parts = fn(b)
    for p in parts:
        p["group"] = label
        p["pos"] = [round(v, 4) for v in p["pos"]]
        p["size"] = [round(max(v, 0.002), 4) for v in p["size"]]
    return parts

# -*- coding: utf-8 -*-
"""Exportadores (JSON para o Unity, GLB, PNG da paleta), renderizador de miniatura e auto-verificação."""
import hashlib
import json
import math
import os
import shutil
import struct
import tempfile
import zlib
from datetime import datetime, timezone

from .builder import PALETTE_COLS, PALETTE_ROWS, cid_uv, perf_rank, spec_to_dict
from .geometry import add, cross, dot, length, mul, norm, rot_x, rot_y, sub
from .version import APP_NAME, APP_VERSION, AVATAR_FORMAT, AVATAR_FORMAT_VERSION, UNITY_PACKAGE_VERSION

CELL_PX = 8


# --------------------------------------------------------------------------- PNG

def png_bytes(width, height, rgb):
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)
        raw += rgb[y * stride:(y + 1) * stride]

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))


def palette_png(palette):
    w, h = PALETTE_COLS * CELL_PX, PALETTE_ROWS * CELL_PX
    rgb = bytearray(w * h * 3)
    for i in range(PALETTE_COLS * PALETTE_ROWS):
        c = palette[i] if i < len(palette) else (0, 0, 0)
        cx, cy = (i % PALETTE_COLS) * CELL_PX, (i // PALETTE_COLS) * CELL_PX
        row = bytes(c) * CELL_PX
        for y in range(cy, cy + CELL_PX):
            o = (y * w + cx) * 3
            rgb[o:o + CELL_PX * 3] = row
    return png_bytes(w, h, bytes(rgb))


# --------------------------------------------------------------------------- JSON (Unity)

def _flat(seq, nd=5):
    out = []
    for v in seq:
        for c in v:
            out.append(round(c, nd))
    return out


def _physbone_json(av, pb):
    """Cadeia de PhysBone + 'endpoint' (continuação da cadeia, necessário para o último osso balançar)."""
    sk = av.skeleton
    last = sk.index[pb["bones"][-1]]
    ref = sk.parent[last] if len(pb["bones"]) == 1 else sk.index[pb["bones"][-2]]
    d = sub(sk.pos[last], sk.pos[ref])
    seg = length(d)
    if seg < 1e-6:
        d, seg = (0.0, -1.0, 0.0), 0.04
    ext = pb.get("extent")
    reach = max(seg * 0.6, 0.02) if ext is None else max(ext, 0.02)
    return {"root": pb["root"], "kind": pb["kind"], "bones": pb["bones"],
            "endpoint": [round(c, 5) for c in mul(norm(d), reach)]}


def unity_dict(av, palette_file):
    sk = av.skeleton
    meshes = []
    for m in av.meshes:
        uv = []
        for c in m.cid:
            uv.extend(cid_uv(c))
        bi, bw = [], []
        for jw in m.joints:
            for b, w in jw:
                bi.append(b)
                bw.append(round(w, 5))
        shapes = []
        for name, d in m.shapes.items():
            idx = sorted(d)
            shapes.append({"name": name, "indices": idx, "deltas": _flat([d[i] for i in idx], 6)})
        meshes.append({
            "name": m.name, "label": m.label, "category": m.category, "toggle": bool(m.toggle),
            "positions": _flat(m.pos), "normals": _flat(m.nrm, 4), "uv": [round(v, 5) for v in uv],
            "triangles": list(m.tris), "boneIndices": bi, "boneWeights": bw, "blendshapes": shapes,
        })
    st = av.stats()
    rank, _ = perf_rank(st)
    return {
        "format": AVATAR_FORMAT, "version": AVATAR_FORMAT_VERSION,
        "name": av.spec.name,
        "paletteTexture": palette_file,
        "viewPosition": list(av.view_position),
        "bones": [{"name": n, "parent": p, "position": [round(c, 5) for c in pos]}
                  for n, p, pos in zip(sk.names, sk.parent, sk.pos)],
        "humanoid": [{"human": h, "bone": b} for h, b in av.humanoid],
        "eyes": {"left": av.eyes["left"], "right": av.eyes["right"]},
        "physbones": [_physbone_json(av, p) for p in av.physbones],
        "meshes": meshes,
        "rank": rank,
        "specJson": json.dumps(spec_to_dict(av.spec, strip_obj=True), ensure_ascii=False),
    }


def write_unity_json(av, path, palette_file):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(unity_dict(av, palette_file), f, separators=(",", ":"), ensure_ascii=False)


# --------------------------------------------------------------------------- GLB

def build_glb(av):
    """GLB em convenção glTF (destro): inverte X e o sentido dos triângulos."""
    sk = av.skeleton
    nb = len(sk.names)
    buf = bytearray()
    views, accs = [], []

    def view(data, target=None):
        while len(buf) % 4:
            buf.append(0)
        v = {"buffer": 0, "byteOffset": len(buf), "byteLength": len(data)}
        if target:
            v["target"] = target
        buf.extend(data)
        views.append(v)
        return len(views) - 1

    def acc(data, ctype, typ, count, target=None, mn=None, mx=None):
        a = {"bufferView": view(data, target), "componentType": ctype, "count": count, "type": typ}
        if mn is not None:
            a["min"], a["max"] = mn, mx
        accs.append(a)
        return len(accs) - 1

    def vec3(points):
        flat = [c for p in points for c in p]
        mn = [min(p[i] for p in points) for i in range(3)] if points else [0, 0, 0]
        mx = [max(p[i] for p in points) for i in range(3)] if points else [0, 0, 0]
        return struct.pack("<%df" % len(flat), *flat), mn, mx

    gl = lambda p: (-p[0], p[1], p[2])

    nodes = [{"name": "Avatar", "children": []}, {"name": "Armature", "children": []}]
    nodes[0]["children"].append(1)
    children = {i: [] for i in range(nb)}
    for i in range(nb):
        p = sk.parent[i]
        if p >= 0:
            children[p].append(i)
    for i in range(nb):
        wp = gl(sk.pos[i])
        pp = gl(sk.pos[sk.parent[i]]) if sk.parent[i] >= 0 else (0, 0, 0)
        n = {"name": sk.names[i], "translation": [round(wp[k] - pp[k], 6) for k in range(3)]}
        if children[i]:
            n["children"] = [2 + c for c in children[i]]
        nodes.append(n)
        if sk.parent[i] < 0:
            nodes[1]["children"].append(2 + i)

    ibm = []
    for i in range(nb):
        wp = gl(sk.pos[i])
        ibm += [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -wp[0], -wp[1], -wp[2], 1]
    ibm_acc = acc(struct.pack("<%df" % len(ibm), *ibm), 5126, "MAT4", nb)
    skins = [{"joints": [2 + i for i in range(nb)], "skeleton": 2, "inverseBindMatrices": ibm_acc}]

    meshes = []
    for m in av.meshes:
        n = len(m.pos)
        pos = [gl(p) for p in m.pos]
        data, mn, mx = vec3(pos)
        a_pos = acc(data, 5126, "VEC3", n, 34962, mn, mx)
        data, _, _ = vec3([gl(v) for v in m.nrm])
        a_nrm = acc(data, 5126, "VEC3", n, 34962)
        uv = []
        for c in m.cid:
            u, v = cid_uv(c)
            uv += [u, 1.0 - v]
        a_uv = acc(struct.pack("<%df" % len(uv), *uv), 5126, "VEC2", n, 34962)
        ji, jw = [], []
        for jws in m.joints:
            for b, w in jws:
                ji.append(b)
                jw.append(w)
        a_j = acc(struct.pack("<%dH" % len(ji), *ji), 5123, "VEC4", n, 34962)
        a_w = acc(struct.pack("<%df" % len(jw), *jw), 5126, "VEC4", n, 34962)
        idx = []
        for i in range(0, len(m.tris), 3):
            idx += [m.tris[i], m.tris[i + 2], m.tris[i + 1]]
        a_i = acc(struct.pack("<%dI" % len(idx), *idx), 5125, "SCALAR", len(idx), 34963)
        prim = {"attributes": {"POSITION": a_pos, "NORMAL": a_nrm, "TEXCOORD_0": a_uv, "JOINTS_0": a_j,
                               "WEIGHTS_0": a_w}, "indices": a_i, "material": 0}
        names = sorted(m.shapes)
        if names:
            targets = []
            for nm in names:
                d = m.shapes[nm]
                dense = [gl(d.get(i, (0.0, 0.0, 0.0))) for i in range(n)]
                data, mn, mx = vec3(dense)
                targets.append({"POSITION": acc(data, 5126, "VEC3", n, 34962, mn, mx)})
            prim["targets"] = targets
        mesh = {"name": m.name, "primitives": [prim]}
        if names:
            mesh["extras"] = {"targetNames": names}
            mesh["weights"] = [0.0] * len(names)
        meshes.append(mesh)
        nodes.append({"name": m.name, "mesh": len(meshes) - 1, "skin": 0})
        nodes[0]["children"].append(len(nodes) - 1)

    img = view(palette_png(av.palette))
    doc = {
        "asset": {"version": "2.0", "generator": "VRChat Avatar Studio"},
        "scene": 0, "scenes": [{"nodes": [0]}], "nodes": nodes, "skins": skins, "meshes": meshes,
        "materials": [{"name": "Palette", "pbrMetallicRoughness": {
            "baseColorTexture": {"index": 0}, "metallicFactor": 0.0, "roughnessFactor": 1.0}}],
        "textures": [{"source": 0, "sampler": 0}],
        "samplers": [{"magFilter": 9728, "minFilter": 9728, "wrapS": 33071, "wrapT": 33071}],
        "images": [{"bufferView": img, "mimeType": "image/png"}],
        "accessors": accs, "bufferViews": views, "buffers": [{"byteLength": len(buf)}],
    }
    js = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)
    bn = bytes(buf) + b"\x00" * ((4 - len(buf) % 4) % 4)
    total = 12 + 8 + len(js) + 8 + len(bn)
    return (struct.pack("<III", 0x46546C67, 2, total) + struct.pack("<II", len(js), 0x4E4F534A) + js +
            struct.pack("<II", len(bn), 0x004E4942) + bn)


# --------------------------------------------------------------------------- renderizador (z-buffer, Gouraud)

def render_rgb(av, width=1200, height=900, yaw=28.0, pitch=6.0, ss=1, hidden=(), zoom=1.0, focus=None,
               bg=((238, 240, 248), (204, 209, 226))):
    ya, pa = math.radians(yaw), math.radians(pitch)
    W, H = width * ss, height * ss
    data = []
    xmin = ymin = 1e9
    xmax = ymax = -1e9
    for m in av.meshes:
        if m.name in hidden:
            continue
        P = [rot_x(rot_y(p, ya), pa) for p in m.pos]
        N = [rot_x(rot_y(n, ya), pa) for n in m.nrm]
        for p in P:
            xmin, xmax = min(xmin, p[0]), max(xmax, p[0])
            ymin, ymax = min(ymin, p[1]), max(ymax, p[1])
        data.append((m, P, N))
    scale = min(W * 0.80 / max(xmax - xmin, 1e-6), H * 0.92 / max(ymax - ymin, 1e-6)) * zoom
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    if focus is not None:
        fp = rot_x(rot_y(tuple(focus), ya), pa)
        cx, cy = fp[0], fp[1]
    img = bytearray(W * H * 3)
    for y in range(H):
        t = y / max(H - 1, 1)
        row = bytes(int(bg[0][i] + (bg[1][i] - bg[0][i]) * t) for i in range(3)) * W
        img[y * W * 3:(y + 1) * W * 3] = row
    zb = [-1e18] * (W * H)
    L = norm((0.45, 0.6, 0.75))
    L2 = norm((-0.62, 0.18, 0.44))
    ceil, floor = math.ceil, math.floor

    for m, P, N in data:
        S = [(W / 2 - (p[0] - cx) * scale, H / 2 - (p[1] - cy) * scale, p[2]) for p in P]
        inten = []
        for n in N:
            key = max(0.0, dot(n, L))
            fill = max(0.0, dot(n, L2))
            view = max(0.0, n[2])
            rim = (1.0 - view) ** 2 * 0.14
            inten.append(0.54 + 0.43 * key + 0.14 * fill + rim)
        T = m.tris
        for i in range(0, len(T), 3):
            a, b, c = T[i], T[i + 1], T[i + 2]
            pa_, pb_, pc_ = P[a], P[b], P[c]
            fn = cross(sub(pb_, pa_), sub(pc_, pa_))
            if fn[2] <= 0:
                continue
            x0, y0, z0 = S[a]
            x1, y1, z1 = S[b]
            x2, y2, z2 = S[c]
            det = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
            if abs(det) < 1e-9:
                continue
            i0, i1, i2 = inten[a], inten[b], inten[c]
            dzdx = ((z1 - z0) * (y2 - y0) - (z2 - z0) * (y1 - y0)) / det
            dzdy = ((x1 - x0) * (z2 - z0) - (x2 - x0) * (z1 - z0)) / det
            didx = ((i1 - i0) * (y2 - y0) - (i2 - i0) * (y1 - y0)) / det
            didy = ((x1 - x0) * (i2 - i0) - (x2 - x0) * (i1 - i0)) / det
            col = av.palette[m.cid[a]]
            r_, g_, b_ = col
            ys0 = max(0, int(ceil(min(y0, y1, y2) - 0.5)))
            ys1 = min(H - 1, int(floor(max(y0, y1, y2) - 0.5)))
            edges = ((x0, y0, x1, y1), (x1, y1, x2, y2), (x2, y2, x0, y0))
            for y in range(ys0, ys1 + 1):
                yc = y + 0.5
                xs = []
                for ax, ay, bx, by in edges:
                    if (ay <= yc < by) or (by <= yc < ay):
                        xs.append(ax + (yc - ay) * (bx - ax) / (by - ay))
                if len(xs) < 2:
                    continue
                xl, xr = (xs[0], xs[1]) if xs[0] < xs[1] else (xs[1], xs[0])
                xi0 = max(0, int(ceil(xl - 0.5)))
                xi1 = min(W - 1, int(floor(xr - 0.5)))
                if xi1 < xi0:
                    continue
                dx = xi0 + 0.5 - x0
                dy = yc - y0
                z = z0 + dzdx * dx + dzdy * dy
                it = i0 + didx * dx + didy * dy
                base = y * W + xi0
                for k in range(xi1 - xi0 + 1):
                    if z > zb[base + k]:
                        zb[base + k] = z
                        o = (base + k) * 3
                        v = it if it < 1.0 else 1.0
                        if v < 0.0:
                            v = 0.0
                        img[o] = int(r_ * v)
                        img[o + 1] = int(g_ * v)
                        img[o + 2] = int(b_ * v)
                    z += dzdx
                    it += didx
    if ss == 1:
        return width, height, bytes(img)
    out = bytearray(width * height * 3)
    n2 = ss * ss
    for y in range(height):
        rows = [img[((y * ss + j) * W) * 3:((y * ss + j) * W + W) * 3] for j in range(ss)]
        for ch in range(3):
            for x in range(width):
                s = 0
                for r in rows:
                    base = (x * ss) * 3 + ch
                    for i in range(ss):
                        s += r[base + i * 3]
                out[(y * width + x) * 3 + ch] = s // n2
    return width, height, bytes(out)


def render_png(av, width=1200, height=900, **kw):
    w, h, rgb = render_rgb(av, width, height, **kw)
    return png_bytes(w, h, rgb)


# --------------------------------------------------------------------------- verificação

def selfcheck(av):
    """Devolve (erros, avisos) sobre integridade do avatar gerado."""
    err, warn = [], []
    sk = av.skeleton
    nb = len(sk.names)
    if len(set(sk.names)) != nb:
        err.append("nomes de ossos duplicados")
    for i, p in enumerate(sk.parent):
        if p >= i:
            err.append("osso %s tem pai fora de ordem" % sk.names[i])
    have = {h for h, _ in av.humanoid}
    for req in ("Hips", "Spine", "Head", "Neck", "LeftUpperArm", "RightUpperArm", "LeftLowerArm", "RightLowerArm",
                "LeftHand", "RightHand", "LeftUpperLeg", "RightUpperLeg", "LeftLowerLeg", "RightLowerLeg",
                "LeftFoot", "RightFoot"):
        if req not in have:
            err.append("osso humanoide obrigatório ausente: " + req)
    # lado esquerdo deve estar em -X
    pos = {n: p for n, p in zip(sk.names, sk.pos)}
    if pos["Hand_L"][0] >= 0 or pos["Hand_R"][0] <= 0:
        err.append("lados esquerdo/direito invertidos")
    for m in av.meshes:
        n = len(m.pos)
        if not (len(m.nrm) == len(m.cid) == len(m.joints) == n):
            err.append("%s: arrays com tamanhos diferentes" % m.name)
        if any(i >= n or i < 0 for i in m.tris):
            err.append("%s: índice de triângulo fora do limite" % m.name)
        if len(m.tris) % 3:
            err.append("%s: triângulos incompletos" % m.name)
        bad_w = 0
        for jw in m.joints:
            s = sum(w for _, w in jw)
            if abs(s - 1.0) > 1e-3 or any(b >= nb for b, w in jw if w > 0):
                bad_w += 1
        if bad_w:
            err.append("%s: %d vértices com pesos inválidos" % (m.name, bad_w))
        bad_n = sum(1 for v in m.nrm if abs(length(v) - 1.0) > 1e-3)
        if bad_n:
            warn.append("%s: %d normais não unitárias" % (m.name, bad_n))
        for name, d in m.shapes.items():
            if any(i >= n for i in d):
                err.append("%s/%s: blendshape com índice inválido" % (m.name, name))
        # orientação: normal do triângulo deve concordar com a normal suave do vértice
        inward = 0
        T = m.tris
        for i in range(0, len(T), 3):
            a, b, c = T[i], T[i + 1], T[i + 2]
            fn = cross(sub(m.pos[b], m.pos[a]), sub(m.pos[c], m.pos[a]))
            sn = add(add(m.nrm[a], m.nrm[b]), m.nrm[c])
            if dot(fn, sn) < 0:
                inward += 1
        if T and inward / (len(T) / 3) > 0.02:
            warn.append("%s: %.1f%% dos triângulos com orientação suspeita" % (m.name, 100.0 * inward / (len(T) / 3)))
    return err, warn


# --------------------------------------------------------------------------- saída em disco

def _remove_path(path):
    if not path or not os.path.lexists(path):
        return
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    else:
        os.remove(path)


def export_all(av, out_dir, base_name, glb=True, thumbnail=True, thumb_size=(1200, 900), thumb_ss=1):
    """Gera o pacote em staging e publica a pasta final de forma transacional.

    Um erro durante GLB/PNG/JSON não deixa arquivos parciais no destino nem remove
    uma exportação anterior válida. A pasta antiga é preservada até o commit.
    """
    parent = os.path.abspath(os.path.dirname(out_dir) or ".")
    os.makedirs(parent, exist_ok=True)
    final_dir = os.path.abspath(out_dir)
    stage = tempfile.mkdtemp(prefix=".vas-export-", dir=parent)
    backup = None
    files = []
    try:
        pal = base_name + "_palette.png"
        with open(os.path.join(stage, pal), "wb") as f:
            f.write(palette_png(av.palette))
        files.append(pal)

        js = base_name + ".vrcavatar.json"
        write_unity_json(av, os.path.join(stage, js), pal)
        files.append(js)

        if glb:
            gn = base_name + ".glb"
            with open(os.path.join(stage, gn), "wb") as f:
                f.write(build_glb(av))
            files.append(gn)

        if thumbnail:
            tn = base_name + "_thumbnail.png"
            with open(os.path.join(stage, tn), "wb") as f:
                f.write(render_png(av, thumb_size[0], thumb_size[1], ss=thumb_ss))
            files.append(tn)

        pn = base_name + ".preset.json"
        with open(os.path.join(stage, pn), "w", encoding="utf-8") as f:
            json.dump(spec_to_dict(av.spec), f, indent=2, ensure_ascii=False)
        files.append(pn)

        # Validação mínima dos artefatos antes de trocar a pasta publicada.
        for name in files:
            path = os.path.join(stage, name)
            if not os.path.isfile(path) or os.path.getsize(path) <= 0:
                raise IOError("Arquivo de exportação ausente ou vazio: " + name)
        with open(os.path.join(stage, js), "r", encoding="utf-8") as f:
            exported_json = json.load(f)
        if exported_json.get("format") != AVATAR_FORMAT or exported_json.get("version") != AVATAR_FORMAT_VERSION:
            raise ValueError("O JSON exportado não corresponde ao formato esperado.")

        manifest_files = []
        for name in files:
            path = os.path.join(stage, name)
            digest = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    digest.update(chunk)
            manifest_files.append({
                "path": name,
                "size": os.path.getsize(path),
                "sha256": digest.hexdigest(),
            })
        rank, _ = perf_rank(av.stats())
        manifest = {
            "application": {"name": APP_NAME, "version": APP_VERSION},
            "avatar_format": {"name": AVATAR_FORMAT, "version": AVATAR_FORMAT_VERSION},
            "unity_package_version": UNITY_PACKAGE_VERSION,
            "avatar": {"name": av.spec.name, "estimated_pc_rank": rank, "stats": av.stats()},
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "options": {"glb": bool(glb), "thumbnail": bool(thumbnail),
                        "thumbnail_size": list(thumb_size), "thumbnail_supersampling": int(thumb_ss)},
            "files": manifest_files,
        }
        with open(os.path.join(stage, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        files.append("manifest.json")

        # Renomeações no mesmo volume: mantém uma cópia anterior para rollback.
        if os.path.lexists(final_dir):
            backup = tempfile.mkdtemp(prefix=".vas-backup-", dir=parent)
            os.rmdir(backup)
            os.replace(final_dir, backup)
        try:
            os.replace(stage, final_dir)
            stage = None
        except Exception:
            if backup and os.path.lexists(backup) and not os.path.lexists(final_dir):
                os.replace(backup, final_dir)
                backup = None
            raise
        if backup and os.path.lexists(backup):
            _remove_path(backup)
            backup = None
        return files
    except Exception:
        if backup and os.path.lexists(backup) and not os.path.lexists(final_dir):
            os.replace(backup, final_dir)
            backup = None
        raise
    finally:
        if stage and os.path.lexists(stage):
            _remove_path(stage)
        if backup and os.path.lexists(backup):
            # Só remove backup depois de confirmar que a nova pasta final existe.
            if os.path.lexists(final_dir):
                _remove_path(backup)

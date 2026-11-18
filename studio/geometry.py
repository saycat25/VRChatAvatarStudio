# -*- coding: utf-8 -*-
"""Geometria básica: vetores, malha com pesos de esqueleto, primitivas e correntes (cadeias de ossos).

Convenção de coordenadas (a mesma do Unity): Y para cima, +Z é a frente do avatar e +X é o
lado DIREITO do avatar. Unidades em metros. Faces frontais em sentido horário (como no Unity);
na prática a orientação é corrigida automaticamente em Mesh.finalize().
"""
import math

# --------------------------------------------------------------------------- vetores

def add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def length(a): return math.sqrt(dot(a, a))
def norm(a):
    l = length(a)
    return (a[0] / l, a[1] / l, a[2] / l) if l > 1e-12 else (0.0, 1.0, 0.0)
def lerp(a, b, t): return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)
def clamp(x, lo, hi): return lo if x < lo else hi if x > hi else x
def smooth(t):
    t = clamp(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)

def rot_x(v, a):
    c, s = math.cos(a), math.sin(a)
    return (v[0], v[1] * c - v[2] * s, v[1] * s + v[2] * c)

def rot_y(v, a):
    c, s = math.cos(a), math.sin(a)
    return (v[0] * c + v[2] * s, v[1], -v[0] * s + v[2] * c)

def rot_z(v, a):
    c, s = math.cos(a), math.sin(a)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c, v[2])


# --------------------------------------------------------------------------- esqueleto

class Skeleton:
    """Lista de ossos. Todos com rotação identidade (pose em T); posições em espaço global."""

    def __init__(self):
        self.names = []
        self.parent = []
        self.pos = []
        self.index = {}

    def add(self, name, parent_index, pos):
        if name in self.index:
            raise ValueError("osso duplicado: " + name)
        self.names.append(name)
        self.parent.append(parent_index)
        self.pos.append(tuple(pos))
        self.index[name] = len(self.names) - 1
        return len(self.names) - 1


# --------------------------------------------------------------------------- malha

def _normalize_weights(jw):
    acc = {}
    for b, w in jw:
        if w > 0:
            acc[b] = acc.get(b, 0.0) + w
    if not acc:
        return [(0, 1.0), (0, 0.0), (0, 0.0), (0, 0.0)]
    items = sorted(acc.items(), key=lambda kv: -kv[1])[:4]
    s = sum(w for _, w in items)
    items = [(b, w / s) for b, w in items]
    while len(items) < 4:
        items.append((0, 0.0))
    return items


class Mesh:
    def __init__(self, name, label, category, toggle=True):
        self.name = name
        self.label = label
        self.category = category
        self.toggle = toggle
        self.pos = []
        self.ref = []      # direção "para fora" por vértice (só para corrigir a orientação)
        self.cid = []      # índice de cor na paleta
        self.joints = []   # [(osso, peso)]
        self.tags = []     # rótulo opcional por vértice (olho, boca...)
        self.tris = []
        self.nrm = []
        self.shapes = {}   # nome -> {indice_vertice: (dx,dy,dz)}

    # -- construção
    def vertex(self, p, ref, cid, jw, tag=""):
        self.pos.append((p[0], p[1], p[2]))
        self.ref.append(ref)
        self.cid.append(cid)
        self.joints.append(jw)
        self.tags.append(tag)
        return len(self.pos) - 1

    def tri(self, a, b, c):
        self.tris.extend((a, b, c))

    def clip(self, drop):
        """Remove triângulos para os quais drop(centroide) é verdadeiro."""
        keep = []
        t, p = self.tris, self.pos
        for i in range(0, len(t), 3):
            a, b, c = p[t[i]], p[t[i + 1]], p[t[i + 2]]
            cen = ((a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3, (a[2] + b[2] + c[2]) / 3)
            if not drop(cen):
                keep.extend(t[i:i + 3])
        self.tris = keep

    def finalize(self):
        """Corrige orientação, remove degenerados e vértices órfãos, calcula normais suaves."""
        t, p, r = self.tris, self.pos, self.ref
        good = []
        for i in range(0, len(t), 3):
            a, b, c = t[i], t[i + 1], t[i + 2]
            n = cross(sub(p[b], p[a]), sub(p[c], p[a]))
            if dot(n, n) < 1e-16:
                continue
            if dot(n, add(add(r[a], r[b]), r[c])) < 0:
                b, c = c, b
            good.extend((a, b, c))
        used = sorted(set(good))
        remap = {old: new for new, old in enumerate(used)}
        self.pos = [p[i] for i in used]
        self.cid = [self.cid[i] for i in used]
        self.joints = [_normalize_weights(self.joints[i]) for i in used]
        self.tags = [self.tags[i] for i in used]
        self.tris = [remap[i] for i in good]
        self.ref = None
        acc = [[0.0, 0.0, 0.0] for _ in self.pos]
        P, T = self.pos, self.tris
        for i in range(0, len(T), 3):
            a, b, c = T[i], T[i + 1], T[i + 2]
            n = cross(sub(P[b], P[a]), sub(P[c], P[a]))
            for v in (a, b, c):
                acc[v][0] += n[0]; acc[v][1] += n[1]; acc[v][2] += n[2]
        self.nrm = [norm(tuple(v)) if (v[0] or v[1] or v[2]) else (0.0, 1.0, 0.0) for v in acc]
        return self

    # -- morph targets
    def morph(self, name, fn):
        """fn(tag, posição) -> nova posição ou None. Guarda só os deltas não nulos."""
        d = {}
        for i, (tag, p) in enumerate(zip(self.tags, self.pos)):
            if not tag:
                continue
            q = fn(tag, p)
            if q is None:
                continue
            dd = sub(q, p)
            if abs(dd[0]) + abs(dd[1]) + abs(dd[2]) > 1e-7:
                d[i] = dd
        self.shapes[name] = d

    def append(self, other):
        """Junta outra malha (já finalizada) a esta (também finalizada)."""
        off = len(self.pos)
        self.pos += other.pos
        self.nrm += other.nrm
        self.cid += other.cid
        self.joints += other.joints
        self.tags += other.tags
        self.tris += [i + off for i in other.tris]
        for name, d in other.shapes.items():
            tgt = self.shapes.setdefault(name, {})
            for i, dv in d.items():
                tgt[i + off] = dv
        # garante que todas as shapes existentes aparecem em ambas
        for name in list(self.shapes):
            other.shapes.setdefault(name, {})


# --------------------------------------------------------------------------- primitivas

def add_ellipsoid(mesh, c, r, cid, jw, seg=12, rings=8, tag="", rot=None, th0=0.0, th1=math.pi):
    """Elipsoide (ou calota, se th0/th1 não cobrirem 0..pi) centrado em c, raios r=(rx,ry,rz)."""
    rx, ry, rz = r

    def vert(th, ph):
        st, ct = math.sin(th), math.cos(th)
        loc = (rx * st * math.sin(ph), ry * ct, rz * st * math.cos(ph))
        rn = norm((st * math.sin(ph) / rx, ct / ry, st * math.cos(ph) / rz))
        if rot:
            loc, rn = rot(loc), rot(rn)
        return mesh.vertex(add(c, loc), rn, cid, jw, tag)

    rows = []
    for i in range(rings + 1):
        th = th0 + (th1 - th0) * i / rings
        if (i == 0 and th0 < 1e-9) or (i == rings and th1 > math.pi - 1e-9):
            rows.append([vert(th, 0.0)])
        else:
            rows.append([vert(th, 2 * math.pi * j / seg) for j in range(seg)])
    for i in range(rings):
        A, B = rows[i], rows[i + 1]
        if len(A) == 1:
            for j in range(seg):
                mesh.tri(A[0], B[(j + 1) % seg], B[j])
        elif len(B) == 1:
            for j in range(seg):
                mesh.tri(A[j], A[(j + 1) % seg], B[0])
        else:
            for j in range(seg):
                j2 = (j + 1) % seg
                mesh.tri(A[j], B[j], B[j2])
                mesh.tri(A[j], B[j2], A[j2])


def add_torus(mesh, c, big_r, small_r, cid, jw, seg=20, seg_small=6, rot=None, tag=""):
    """Anel no plano XY voltado para +Z."""
    grid = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        ca, sa = math.cos(a), math.sin(a)
        row = []
        for j in range(seg_small):
            b = 2 * math.pi * j / seg_small
            cb, sb = math.cos(b), math.sin(b)
            loc = ((big_r + small_r * cb) * ca, (big_r + small_r * cb) * sa, small_r * sb)
            rn = (cb * ca, cb * sa, sb)
            if rot:
                loc, rn = rot(loc), rot(rn)
            row.append(mesh.vertex(add(c, loc), rn, cid, jw, tag))
        grid.append(row)
    for i in range(seg):
        i2 = (i + 1) % seg
        for j in range(seg_small):
            j2 = (j + 1) % seg_small
            mesh.tri(grid[i][j], grid[i2][j], grid[i2][j2])
            mesh.tri(grid[i][j], grid[i2][j2], grid[i][j2])


class Ring:
    __slots__ = ("pos", "ru", "rv", "d", "jw", "cid")

    def __init__(self, pos, ru, rv, d, jw, cid):
        self.pos, self.ru, self.rv, self.d, self.jw, self.cid = pos, ru, rv, d, jw, cid


def frame(d):
    up = (0.0, 1.0, 0.0) if abs(d[1]) < 0.9 else (0.0, 0.0, 1.0)
    u = norm(cross(up, d))
    v = norm(cross(d, u))
    return u, v


def add_rings(mesh, rings, sides, caps=(False, False), dome=(False, False), tag=""):
    """Tubo por anéis elípticos. caps: tampa plana; dome: ponta arredondada."""
    seq = list(rings)
    first, last = seq[0], seq[-1]
    pre, post = [], []
    pole0 = pole1 = None
    if dome[0]:
        R = (first.ru + first.rv) / 2
        for a in (72, 42):
            ar = math.radians(a)
            pre.append(Ring(sub(first.pos, mul(first.d, R * math.sin(ar))), first.ru * math.cos(ar),
                            first.rv * math.cos(ar), first.d, first.jw, first.cid))
        pole0 = sub(first.pos, mul(first.d, R))
    if dome[1]:
        R = (last.ru + last.rv) / 2
        for a in (42, 72):
            ar = math.radians(a)
            post.append(Ring(add(last.pos, mul(last.d, R * math.sin(ar))), last.ru * math.cos(ar),
                             last.rv * math.cos(ar), last.d, last.jw, last.cid))
        pole1 = add(last.pos, mul(last.d, R))
    seq = pre + seq + post
    rows = []
    for rg in seq:
        u, v = frame(rg.d)
        row = []
        for j in range(sides):
            a = 2 * math.pi * j / sides
            ca, sa = math.cos(a), math.sin(a)
            p = add(rg.pos, add(mul(u, rg.ru * ca), mul(v, rg.rv * sa)))
            n = norm(add(mul(u, ca / max(rg.ru, 1e-6)), mul(v, sa / max(rg.rv, 1e-6))))
            row.append(mesh.vertex(p, n, rg.cid, rg.jw, tag))
        rows.append(row)
    for i in range(len(rows) - 1):
        A, B = rows[i], rows[i + 1]
        for j in range(sides):
            j2 = (j + 1) % sides
            mesh.tri(A[j], B[j], B[j2])
            mesh.tri(A[j], B[j2], A[j2])

    def close(row, center, ref, rg):
        c = mesh.vertex(center, ref, rg.cid, rg.jw, tag)
        for j in range(sides):
            mesh.tri(c, row[j], row[(j + 1) % sides])

    if pole0 is not None:
        close(rows[0], pole0, mul(first.d, -1), first)
    elif caps[0]:
        close(rows[0], first.pos, mul(first.d, -1), first)
    if pole1 is not None:
        close(rows[-1], pole1, last.d, last)
    elif caps[1]:
        close(rows[-1], last.pos, last.d, last)


# --------------------------------------------------------------------------- cadeias

class Chain:
    """Caminho (polilinha) com ossos ao longo dele. Calcula pesos de pele suaves nas juntas.

    pts       -- pontos do caminho
    node_idx  -- índice em pts de cada osso (na ordem de bones)
    prev      -- osso (índice) com o qual a primeira junta se mistura (pai), ou None
    """

    def __init__(self, bones, pts, node_idx, prev=None):
        self.bones = list(bones)
        self.pts = list(pts)
        self.prev = prev
        self.cum = [0.0]
        for i in range(1, len(self.pts)):
            self.cum.append(self.cum[-1] + length(sub(self.pts[i], self.pts[i - 1])))
        self.total = self.cum[-1]
        self.node_u = [self.cum[i] for i in node_idx]

    def point(self, u):
        u = clamp(u, 0.0, self.total)
        n = len(self.cum)
        for i in range(1, n):
            if u <= self.cum[i] or i == n - 1:
                seg = self.cum[i] - self.cum[i - 1]
                t = (u - self.cum[i - 1]) / seg if seg > 1e-12 else 0.0
                return lerp(self.pts[i - 1], self.pts[i], t), norm(sub(self.pts[i], self.pts[i - 1]))
        return self.pts[-1], (0.0, 1.0, 0.0)

    def weights(self, u):
        nu, b, n = self.node_u, self.bones, len(self.bones)
        if u <= nu[0]:
            if self.prev is None:
                return [(b[0], 1.0)]
            f = 0.5 + 0.5 * smooth((nu[0] - u) / 0.05)
            return [(self.prev, f), (b[0], 1.0 - f)]
        if u >= nu[-1]:
            if n >= 2:
                L = max(nu[-1] - nu[-2], 1e-6)
                f = 0.5 * (1.0 - smooth((u - nu[-1]) / (0.3 * L)))
                return [(b[-1], 1.0 - f), (b[-2], f)]
            return [(b[-1], 1.0)]
        for i in range(n - 1):
            if u <= nu[i + 1]:
                t = (u - nu[i]) / (nu[i + 1] - nu[i])
                if t < 0.3:
                    f = 0.5 * (1.0 - smooth(t / 0.3))
                    other = b[i - 1] if i > 0 else self.prev
                    if other is None:
                        return [(b[i], 1.0)]
                    return [(b[i], 1.0 - f), (other, f)]
                if t > 0.7:
                    f = 0.5 * smooth((t - 0.7) / 0.3)
                    return [(b[i], 1.0 - f), (b[i + 1], f)]
                return [(b[i], 1.0)]
        return [(b[-1], 1.0)]


def axis_chain(bones, node_pos, prev=None, pre=0.0, post=0.0):
    """Chain cujos pontos são as posições dos ossos, com extensões opcionais nas pontas."""
    pts = list(node_pos)
    off = 0
    if pre > 0:
        d = norm(sub(node_pos[0], node_pos[1]))
        pts.insert(0, add(node_pos[0], mul(d, pre)))
        off = 1
    if post > 0:
        d = norm(sub(node_pos[-1], node_pos[-2]))
        pts.append(add(node_pos[-1], mul(d, post)))
    return Chain(bones, pts, [i + off for i in range(len(node_pos))], prev)


def profile(keys, u):
    """Interpola (u, ru, rv) com suavização."""
    if u <= keys[0][0]:
        return keys[0][1], keys[0][2]
    for (u0, a0, b0), (u1, a1, b1) in zip(keys, keys[1:]):
        if u <= u1:
            t = smooth((u - u0) / (u1 - u0)) if u1 > u0 else 1.0
            return a0 + (a1 - a0) * t, b0 + (b1 - b0) * t
    return keys[-1][1], keys[-1][2]


def body_tube(mesh, chain, keys, cid, sides, nrings, u0=None, u1=None, grow=0.0,
              caps=(False, False), dome=(False, False), tag="", offset=(0.0, 0.0, 0.0), scale=1.0):
    """Tubo ao longo de uma Chain com raios dados por 'keys' (u em metros desde o início)."""
    if u0 is None:
        u0 = 0.0
    if u1 is None:
        u1 = chain.total
    rings = []
    for k in range(nrings):
        u = u0 + (u1 - u0) * k / (nrings - 1)
        p, d = chain.point(u)
        ru, rv = profile(keys, u)
        c = cid(u) if callable(cid) else cid
        rings.append(Ring(add(p, offset), max(ru * scale + grow, 1e-4), max(rv * scale + grow, 1e-4),
                          d, chain.weights(u), c))
    add_rings(mesh, rings, sides, caps, dome, tag)


# --------------------------------------------------------------------------- primitivas extras (acessórios)

def add_ellipse_loop(mesh, c, dx, dy, tube, cid, jw, rot=None, seg=28, seg_small=6, tag=""):
    """Anel elíptico (plano XY, voltado para +Z). dx, dy = diâmetros externos; tube = espessura do tubo."""
    rx = max((dx - tube) / 2.0, tube * 0.3)
    ry = max((dy - tube) / 2.0, tube * 0.3)
    grid = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        ca, sa = math.cos(a), math.sin(a)
        n_in = norm((ry * ca, rx * sa, 0.0))
        row = []
        for j in range(seg_small):
            b = 2 * math.pi * j / seg_small
            cb, sb = math.cos(b), math.sin(b)
            rn = (n_in[0] * cb, n_in[1] * cb, sb)
            loc = (rx * ca + rn[0] * tube / 2, ry * sa + rn[1] * tube / 2, rn[2] * tube / 2)
            if rot:
                loc, rn = rot(loc), rot(rn)
            row.append(mesh.vertex(add(c, loc), rn, cid, jw, tag))
        grid.append(row)
    for i in range(seg):
        i2 = (i + 1) % seg
        for j in range(seg_small):
            j2 = (j + 1) % seg_small
            mesh.tri(grid[i][j], grid[i2][j], grid[i2][j2])
            mesh.tri(grid[i][j], grid[i2][j2], grid[i][j2])


def add_box(mesh, c, size, cid, jw, rot=None, tag=""):
    hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
    faces = [((1, 0, 0), (1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1)),
             ((-1, 0, 0), (-1, -1, 1), (-1, 1, 1), (-1, 1, -1), (-1, -1, -1)),
             ((0, 1, 0), (-1, 1, -1), (-1, 1, 1), (1, 1, 1), (1, 1, -1)),
             ((0, -1, 0), (-1, -1, 1), (-1, -1, -1), (1, -1, -1), (1, -1, 1)),
             ((0, 0, 1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)),
             ((0, 0, -1), (1, -1, -1), (-1, -1, -1), (-1, 1, -1), (1, 1, -1))]
    for f in faces:
        nrm = f[0]
        ids = []
        for sx, sy, sz in f[1:]:
            loc = (sx * hx, sy * hy, sz * hz)
            rn = nrm
            if rot:
                loc, rn = rot(loc), rot(rn)
            ids.append(mesh.vertex(add(c, loc), rn, cid, jw, tag))
        mesh.tri(ids[0], ids[1], ids[2])
        mesh.tri(ids[0], ids[2], ids[3])


def add_prism(mesh, c, size, cid, jw, sides=14, top=1.0, bottom=1.0, rot=None, caps=True, tag=""):
    """Cilindro/cone (eixo Y). size = (diâmetro x, altura, diâmetro z). top/bottom = escala do raio."""
    rx, hy, rz = size[0] / 2, size[1] / 2, size[2] / 2
    rows = []
    for yy, k in ((-hy, bottom), (hy, top)):
        row = []
        for j in range(sides):
            a = 2 * math.pi * j / sides
            ca, sa = math.cos(a), math.sin(a)
            loc = (rx * k * ca, yy, rz * k * sa)
            rn = norm((ca, (bottom - top) * 0.5 * (hy * 2) / max(rx, 1e-6) * 0.5, sa))
            if rot:
                loc, rn = rot(loc), rot(rn)
            row.append(mesh.vertex(add(c, loc), rn, cid, jw, tag))
        rows.append(row)
    A, B = rows
    for j in range(sides):
        j2 = (j + 1) % sides
        mesh.tri(A[j], A[j2], B[j2])
        mesh.tri(A[j], B[j2], B[j])
    if caps:
        for yy, k, ny in ((-hy, bottom, -1.0), (hy, top, 1.0)):
            if k < 0.02:
                continue
            nn = (0.0, ny, 0.0)
            cen_loc = (0.0, yy, 0.0)
            if rot:
                cen_loc, nn = rot(cen_loc), rot(nn)
            cv = mesh.vertex(add(c, cen_loc), nn, cid, jw, tag)
            rim = []
            for j in range(sides):
                a = 2 * math.pi * j / sides
                loc = (rx * k * math.cos(a), yy, rz * k * math.sin(a))
                if rot:
                    loc = rot(loc)
                rim.append(mesh.vertex(add(c, loc), nn, cid, jw, tag))
            for j in range(sides):
                mesh.tri(cv, rim[j], rim[(j + 1) % sides])


def star_outline(points=5, inner=0.42):
    pts = []
    for i in range(points * 2):
        a = math.pi / 2 + math.pi * i / points
        r = 0.5 if i % 2 == 0 else 0.5 * inner
        pts.append((r * math.cos(a), r * math.sin(a)))
    return pts


def heart_outline(n=28):
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((x / 34.0, (y + 2.5) / 34.0))
    return pts


def add_extrude(mesh, c, size, outline, cid, jw, rot=None, tag=""):
    """Extrude um contorno 2D (cabe em [-0.5,0.5]) no plano XY; size = (largura, altura, espessura)."""
    sx, sy, th = size
    n = len(outline)
    for zs in (1.0, -1.0):
        nn = (0.0, 0.0, zs)
        cen = (0.0, 0.0, zs * th / 2)
        if rot:
            cen, nn = rot(cen), rot(nn)
        cv = mesh.vertex(add(c, cen), nn, cid, jw, tag)
        rim = []
        for x, y in outline:
            loc = (x * sx, y * sy, zs * th / 2)
            if rot:
                loc = rot(loc)
            rim.append(mesh.vertex(add(c, loc), nn, cid, jw, tag))
        for j in range(n):
            mesh.tri(cv, rim[j], rim[(j + 1) % n])
    ring = []
    for x, y in outline:
        rn = norm((x, y, 0.0))
        top = (x * sx, y * sy, th / 2)
        bot = (x * sx, y * sy, -th / 2)
        if rot:
            top, bot, rn = rot(top), rot(bot), rot(rn)
        ring.append((mesh.vertex(add(c, top), rn, cid, jw, tag), mesh.vertex(add(c, bot), rn, cid, jw, tag)))
    for j in range(n):
        a, b = ring[j], ring[(j + 1) % n]
        mesh.tri(a[0], a[1], b[1])
        mesh.tri(a[0], b[1], b[0])

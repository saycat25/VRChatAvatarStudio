# -*- coding: utf-8 -*-
"""Servidor local da interface (somente biblioteca padrão). Escuta apenas em 127.0.0.1."""
import base64
import io
import json
import logging
import mimetypes
import os
import re
import struct
import sys
import threading
import time
import traceback
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .builder import (RANK_LIMITS, RANK_NAMES, SCHEMA, AvatarBuilder, build_avatar, make_spec, perf_rank,
                      random_spec, spec_to_dict)
from .export import export_all, selfcheck
from .parts import BONES, SHAPES, expand_template, parse_obj_detailed, template_list
from .version import APP_NAME, APP_VERSION, AVATAR_FORMAT_VERSION, UNITY_PACKAGE_VERSION
from . import workshop

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
MAX_BODY = 36 * 1024 * 1024  # suporta upload base64 de assets locais de até 25 MB
EXPORT_LOCK = threading.Lock()  # evita colisões quando dois exports usam o mesmo nome simultaneamente.

STAT_LABELS = {"triangles": "Triângulos", "skinned_meshes": "Malhas (skinned)", "material_slots": "Materiais",
               "bones": "Ossos", "physbone_components": "PhysBones (componentes)",
               "physbone_transforms": "PhysBones (ossos afetados)"}


def _b64(fmt, values):
    return base64.b64encode(struct.pack("<%d%s" % (len(values), fmt), *values)).decode("ascii")


def _stat_rows(stats):
    rows = []
    for key, *lims in RANK_LIMITS:
        v = stats[key]
        r = 4
        for i, lim in enumerate(lims):
            if v <= lim:
                r = i
                break
        rows.append({"key": key, "label": STAT_LABELS[key], "value": v, "rank": r, "limits": lims})
    return rows


def model_payload(spec_dict):
    spec = make_spec(spec_dict)
    av = build_avatar(spec)
    err, warn = selfcheck(av)
    stats = av.stats()
    rank, why = perf_rank(stats)
    sk = av.skeleton
    meshes = []
    for m in av.meshes:
        n = len(m.pos)
        pos = [c for p in m.pos for c in p]
        nrm = [c for p in m.nrm for c in p]
        col = [c for i in m.cid for c in av.palette[i]]
        wide = n > 65535
        shapes = []
        for name, d in m.shapes.items():
            if not d:
                continue
            idx = sorted(d)
            shapes.append({"name": name, "idx": _b64("I", idx), "d": _b64("f", [c for i in idx for c in d[i]])})
        meshes.append({"name": m.name, "label": m.label, "category": m.category, "toggle": m.toggle,
                       "count": n, "tris": len(m.tris) // 3,
                       "pos": _b64("f", pos), "nrm": _b64("f", nrm),
                       "col": base64.b64encode(bytes(col)).decode("ascii"),
                       "idx": _b64("I" if wide else "H", m.tris), "wide": wide, "shapes": shapes})
    lines = []
    for i, p in enumerate(sk.parent):
        if p >= 0:
            lines += list(sk.pos[p]) + list(sk.pos[i])
    return {"meshes": meshes, "bones": _b64("f", lines), "boneCount": len(sk.names),
            "stats": stats, "rows": _stat_rows(stats), "rank": rank, "rankIndex": RANK_NAMES.index(rank),
            "why": why, "rankNote": "Estimativa local heurística; não é o ranking oficial do SDK.", "errors": err, "warnings": warn,
            "palette": ["#%02x%02x%02x" % c for c in av.palette],
            "partCount": len(spec.parts), "viewY": av.view_position[1], "height": spec.height}


def schema_payload():
    spec = make_spec({})
    return {"schema": SCHEMA, "defaults": spec_to_dict(spec), "shapes": SHAPES,
            "bones": BONES, "templates": template_list(), "rankNames": RANK_NAMES,
            "versions": {"app": APP_VERSION, "avatar_format": AVATAR_FORMAT_VERSION, "unity_package": UNITY_PACKAGE_VERSION}}


def export_zip(spec_dict):
    spec = make_spec(spec_dict)
    av = build_avatar(spec)
    err, _ = selfcheck(av)
    if err:
        raise ValueError("Avatar inválido: " + "; ".join(err))
    base = re.sub(r"[^\w\-]", "", spec.name) or "Avatar"
    out = os.path.join(OUTPUT_DIR, base)
    with EXPORT_LOCK:
        files = export_all(av, out, base, glb=True, thumbnail=True)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in files:
                z.write(os.path.join(out, f), base + "/" + f)
        return base, buf.getvalue(), out


class Handler(BaseHTTPRequestHandler):
    server_version = "VRChatAvatarStudio/1.4"

    def log_message(self, fmt, *args):
        if os.environ.get("AVATAR_STUDIO_VERBOSE"):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # -- segurança: só aceita Host local (evita DNS rebinding) e exige cabeçalho próprio nos POST (evita CSRF)
    def _host_ok(self):
        host = (self.headers.get("Host") or "").lower()
        port = self.server.server_address[1]
        return host in ("127.0.0.1:%d" % port, "localhost:%d" % port)

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, separators=(",", ":"), ensure_ascii=False))

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, "host inválido", "text/plain")
        path = self.path.split("?", 1)[0]
        if path == "/api/schema":
            return self._json(schema_payload())
        if path == "/api/workshop":
            return self._json({"assets": workshop.list_assets(), "tasks": workshop.list_jobs(),
                                "ai": workshop.api_status()})
        if path == "/api/ai/status":
            return self._json(workshop.api_status())
        if path.startswith("/api/ai/tasks/"):
            try:
                return self._json(workshop.poll_task(path.rsplit("/", 1)[-1]))
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
        if path.startswith("/api/assets/"):
            asset_id = path.rsplit("/", 1)[-1]
            try:
                item, data = workshop.get_asset(asset_id)
                ext = item["extension"]
                ctype = mimetypes.types_map.get(ext, "application/octet-stream")
                disposition = "attachment" if path.startswith("/api/assets/download/") else "inline"
                return self._send(200, data, ctype, {"Content-Disposition": "%s; filename=\"%s\"" %
                                  (disposition, item["name"].replace('"', ""))})
            except ValueError as e:
                return self._send(404, str(e), "text/plain; charset=utf-8")
        if path == "/":
            path = "/index.html"
        name = path.lstrip("/")
        if name not in ("index.html", "app.js", "style.css", "viewer.js"):
            return self._send(404, "não encontrado", "text/plain")
        with open(os.path.join(WEB_DIR, name), "rb") as f:
            data = f.read()
        self._send(200, data, (mimetypes.guess_type(name)[0] or "text/plain") + "; charset=utf-8")

    def do_POST(self):
        if not self._host_ok() or self.headers.get("X-Studio") != "1":
            return self._send(403, "proibido", "text/plain")
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                return self._json({"error": "requisição grande demais"}, 413)
            if n < 0:
                return self._json({"error": "Content-Length inválido"}, 400)
            body = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("o corpo da requisição deve ser um objeto JSON")
            path = self.path.split("?", 1)[0]
            if path == "/api/ai/config":
                key = body.get("api_key", "")
                if not isinstance(key, str):
                    raise ValueError("chave da API deve ser texto")
                return self._json({"configured": workshop.configure_api_key(key),
                                   "key_storage": "memória do servidor local"})
            if path == "/api/assets/upload":
                filename = body.get("filename", "")
                category = body.get("category", "accessory")
                encoded = body.get("content_base64", "")
                if not isinstance(filename, str) or not isinstance(category, str) or not isinstance(encoded, str):
                    raise ValueError("campos de upload inválidos")
                try:
                    data = base64.b64decode(encoded, validate=True)
                except (ValueError, TypeError) as e:
                    raise ValueError("conteúdo base64 inválido") from e
                asset = workshop.save_asset(filename, category, data)
                return self._json({"asset": asset}, 201)
            if path == "/api/ai/tasks":
                return self._json(workshop.create_task(body), 202)
            if path == "/api/ai/refine":
                return self._json(workshop.refine_text_task(str(body.get("preview_job_id", ""))), 202)
            if path == "/api/model":
                return self._json(model_payload(body.get("spec", {})))
            if path == "/api/random":
                seed = body.get("seed")
                return self._json(random_spec(seed))
            if path == "/api/template":
                spec = make_spec(body.get("spec", {}))
                return self._json({"parts": expand_template(str(body.get("template", "")), spec)})
            if path == "/api/obj-check":
                obj_text = body.get("text", "")
                if not isinstance(obj_text, str):
                    raise ValueError("conteúdo OBJ inválido")
                if len(obj_text) > 2_000_000:
                    raise ValueError("arquivo OBJ excede 2 MB")
                _, _, issues, info = parse_obj_detailed(obj_text)
                fatal = any("limite de 100000 vértices" in issue for issue in issues)
                return self._json({"issues": issues, "info": info, "valid": info["triangles"] > 0 and not fatal})
            if path == "/api/export":
                base, data, out = export_zip(body.get("spec", {}))
                return self._send(200, data, "application/zip", {
                    "Content-Disposition": 'attachment; filename="%s.zip"' % base,
                    "X-Saved-To": os.path.relpath(out).replace("\\", "/")})
            return self._json({"error": "rota desconhecida"}, 404)
        except KeyError as e:
            return self._json({"error": "modelo desconhecido: %s" % e}, 400)
        except (ValueError, json.JSONDecodeError) as e:
            return self._json({"error": str(e)}, 400)
        except Exception as e:                                   # noqa: BLE001 - devolve erro legível à UI
            logging.getLogger(__name__).exception("Falha ao processar %s", self.path)
            traceback.print_exc()
            return self._json({"error": "erro interno: %s" % e}, 500)


def serve(port=8765, open_browser=True):
    httpd = None
    for p in range(port, port + 20):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", p), Handler)
            break
        except OSError:
            continue
    if httpd is None:
        raise SystemExit("Não encontrei uma porta livre perto de %d." % port)
    url = "http://127.0.0.1:%d/" % httpd.server_address[1]
    print("VRChat Avatar Studio rodando em", url)
    print("(Ctrl+C para encerrar)")
    logging.getLogger(__name__).info("Servidor iniciado em %s", url)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrado.")
    finally:
        httpd.server_close()

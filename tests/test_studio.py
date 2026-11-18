# -*- coding: utf-8 -*-
"""Testes do VRChat Avatar Studio.  Rode:  python -m unittest discover -s tests -v"""
import hashlib
import base64
import io
import json
import os
from pathlib import Path
import re
import struct
import sys
import tempfile
import threading
import unittest
from unittest import mock
import urllib.request
import urllib.error
import zipfile
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from studio.builder import build_avatar, make_spec, perf_rank, random_spec          # noqa: E402
from studio.export import build_glb, export_all, selfcheck, unity_dict, palette_png  # noqa: E402
from studio.parts import (TEMPLATES, expand_template, parse_obj, parse_obj_detailed,
                          sanitize_parts)                                             # noqa: E402
from studio import export as export_module                                             # noqa: E402
from studio import server                                                            # noqa: E402

CUBE = "v -1 -1 -1\nv 1 -1 -1\nv 1 1 -1\nv -1 1 -1\nv -1 -1 1\nv 1 -1 1\nv 1 1 1\nv -1 1 1\n" \
       "f 1 2 3 4\nf 5 8 7 6\nf 1 5 6 2\nf 2 6 7 3\nf 3 7 8 4\nf 5 1 4 8\n"


def with_parts(keys, **kw):
    spec = make_spec(kw)
    parts = []
    for k in keys:
        for p in expand_template(k, spec):
            p["id"] = "p%d" % len(parts)
            parts.append(p)
    d = dict(kw)
    d["parts"] = parts
    return build_avatar(d)


class Spec(unittest.TestCase):
    def test_sanitize(self):
        s = make_spec({"height": 99, "skin": "nope", "hair_style": "xxx", "name": "a<b>/..\\c", "parts": "lixo"})
        self.assertEqual(s.height, 2.1)
        self.assertEqual(s.skin, "#f3cdb6")
        self.assertEqual(s.hair_style, "long")
        self.assertNotRegex(s.name, r"[<>/\\.]")
        self.assertEqual(s.parts, [])

    def test_parts_sanitize(self):
        parts = sanitize_parts([{"shape": "x", "bone": "Nada", "pos": ["a"], "size": [-5, 0, 99], "color": "red"},
                                {"id": "p1"}, {"id": "p1"}, 5])
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0]["shape"], "sphere")
        self.assertEqual(parts[0]["bone"], "Head")
        self.assertEqual(parts[0]["color"], "#ffffff")
        self.assertEqual(len({p["id"] for p in parts}), 3)
        self.assertTrue(all(0.002 <= v <= 3 for p in parts for v in p["size"]))

    def test_random_valid(self):
        for seed in range(25):
            av = build_avatar(random_spec(seed))
            err, _ = selfcheck(av)
            self.assertEqual(err, [], "seed %d" % seed)


class Build(unittest.TestCase):
    def test_every_option_builds(self):
        from studio.builder import SCHEMA
        for g in SCHEMA:
            for it in g["items"]:
                if it["type"] == "select":
                    for v, _ in it["options"]:
                        av = build_avatar({it["key"]: v})
                        err, _ = selfcheck(av)
                        self.assertEqual(err, [], "%s=%s" % (it["key"], v))

    def test_fingers_off_and_merge(self):
        av = build_avatar({"fingers": False, "merge_meshes": True})
        self.assertEqual(len(av.meshes), 1)
        self.assertEqual(selfcheck(av)[0], [])

    def test_viseme_and_expression_shapes(self):
        av = build_avatar({})
        names = set(av.meshes[0].shapes)
        for v in ("sil pp ff th dd kk ch ss nn rr aa e ih oh ou".split()):
            self.assertIn("vrc.v_" + v, names)
        for n in ("Blink", "Smile", "Angry", "Sad", "Surprised", "Blush", "LookUp", "LookDown"):
            self.assertIn(n, names)

    def test_visual_quality_profiles(self):
        self.assertEqual(make_spec({}).detail, 3)
        self.assertEqual(make_spec({}).ears, "human")
        self.assertEqual(make_spec({}).tail, "none")
        for detail in ("1", "2", "3", "4"):
            av = build_avatar({"detail": detail, "top": "hoodie", "bottom": "skirt", "hair_style": "long"})
            self.assertEqual(selfcheck(av)[0], [], "detail=" + detail)
            self.assertGreater(len(av.meshes[0].pos), 1000)
            if detail == "4":
                self.assertLess(av.stats()["triangles"], 70000)

    def test_perf_rank_table(self):
        self.assertEqual(perf_rank({"triangles": 1000, "skinned_meshes": 1, "material_slots": 1, "bones": 50,
                                    "physbone_components": 0, "physbone_transforms": 0})[0], "Excellent")
        self.assertEqual(perf_rank({"triangles": 90000, "skinned_meshes": 1, "material_slots": 1, "bones": 50,
                                    "physbone_components": 0, "physbone_transforms": 0})[0], "Very Poor")

    def test_merge_gives_excellent_or_good(self):
        av = build_avatar({"merge_meshes": True, "detail": "1", "hair_style": "short", "tail": "none"})
        self.assertIn(perf_rank(av.stats())[0], ("Excellent", "Good"))


class Parts(unittest.TestCase):
    def test_every_template_builds(self):
        for k in TEMPLATES:
            av = with_parts([k])
            self.assertEqual(selfcheck(av)[0], [], k)
            self.assertGreater(len(av.meshes), 5, k)

    def test_all_templates_together(self):
        av = with_parts(list(TEMPLATES))
        self.assertEqual(selfcheck(av)[0], [])
        self.assertLessEqual(len(av.palette), 64)

    def test_every_shape(self):
        parts = [{"id": "s%d" % i, "shape": s, "bone": "Head", "pos": [0, 0.2, 0], "size": [0.1, 0.1, 0.1],
                  "color": "#%06x" % (i * 40000), "obj": CUBE} for i, s in
                 enumerate(["sphere", "box", "cylinder", "cone", "ring", "star", "heart", "obj"])]
        av = build_avatar({"parts": parts})
        self.assertEqual(selfcheck(av)[0], [])
        acc = [m for m in av.meshes if m.name.startswith("Acc_")]
        self.assertEqual(len(acc), 1)
        self.assertGreater(len(acc[0].tris) // 3, 100)

    def test_mirror_and_groups(self):
        part = {"id": "m", "group": "Par", "shape": "sphere", "bone": "Hand_R", "pos": [-0.03, 0, 0],
                "size": [0.05, 0.05, 0.05], "mirror": True, "color": "#ff0000"}
        av = build_avatar({"parts": [part]})
        m = [x for x in av.meshes if x.name == "Acc_Par"][0]
        sk = av.skeleton
        used = {b for jw in m.joints for b, w in jw if w > 0}
        self.assertEqual(used, {sk.index["Hand_R"], sk.index["Hand_L"]})
        xs = [p[0] for p in m.pos]
        self.assertLess(min(xs), -0.3)
        self.assertGreater(max(xs), 0.3)

    def test_jiggle_adds_physbone(self):
        part = {"id": "j", "group": "G", "shape": "sphere", "bone": "Head", "pos": [0, 0.2, 0], "size": [0.04] * 3,
                "jiggle": True}
        av = build_avatar({"parts": [part]})
        self.assertIn("Acc_j", av.skeleton.names)
        self.assertTrue(any(p["root"] == "Acc_j" for p in av.physbones))
        d = unity_dict(av, "x.png")
        pb = [p for p in d["physbones"] if p["root"] == "Acc_j"][0]
        self.assertEqual(len(pb["endpoint"]), 3)

    def test_palette_overflow_does_not_crash(self):
        parts = [{"id": "c%d" % i, "shape": "sphere", "bone": "Head", "pos": [0, 0.2, 0], "size": [0.02] * 3,
                  "color": "#%02x%02x%02x" % (i * 3 % 256, i * 7 % 256, i * 11 % 256)} for i in range(70)]
        av = build_avatar({"parts": parts})
        self.assertLessEqual(len(av.palette), 64)
        self.assertEqual(selfcheck(av)[0], [])

    def test_obj_parser_limits(self):
        v, t = parse_obj(CUBE)
        self.assertEqual((len(v), len(t)), (8, 12))
        v, t = parse_obj("v 0 0 0\nf 1 2 3\nf -1 -1 -1\n")
        self.assertEqual(len(t), 0)   # índices fora do limite e faces degeneradas são rejeitados

    def test_obj_polygons_negative_indices_and_diagnostics(self):
        obj = "\n".join([
            "v 0 0 0", "v 1 0 0", "v 1 1 0", "v 0 1 0",
            "vt 0 0", "vn 0 0 1", "f -4/1/1 -3/1/1 -2/1/1 -1/1/1", ""
        ])
        verts, tris, issues, info = parse_obj_detailed(obj)
        self.assertEqual(len(verts), 4)
        self.assertEqual(len(tris), 2)
        self.assertEqual(info["triangles"], 2)
        self.assertEqual(issues, [])
        _, _, issues, info = parse_obj_detailed("v NaN 0 0\nf 1 2 3\n")
        self.assertEqual(info["triangles"], 0)
        self.assertTrue(any("NaN/infinito" in issue for issue in issues))

    def test_hidden_parts_are_not_exported_and_lock_is_preserved(self):
        p = {"id": "hidden", "group": "Grupo", "shape": "sphere", "bone": "Head",
             "pos": [0, 0.2, 0], "size": [0.04] * 3, "visible": False, "locked": True}
        clean = sanitize_parts([p])
        self.assertFalse(clean[0]["visible"])
        self.assertTrue(clean[0]["locked"])
        av = build_avatar({"parts": [p]})
        self.assertFalse(any(m.name.startswith("Acc_") for m in av.meshes))


class Export(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.av = with_parts(["wings_angel", "bell_collar"])

    def test_glb_structure(self):
        glb = build_glb(self.av)
        magic, ver, total = struct.unpack("<III", glb[:12])
        self.assertEqual((magic, ver, total), (0x46546C67, 2, len(glb)))
        jl, jt = struct.unpack("<II", glb[12:20])
        self.assertEqual(jt, 0x4E4F534A)
        doc = json.loads(glb[20:20 + jl])
        bl, bt = struct.unpack("<II", glb[20 + jl:28 + jl])
        self.assertEqual(bt, 0x004E4942)
        self.assertEqual(doc["buffers"][0]["byteLength"], bl - ((bl - doc["buffers"][0]["byteLength"])))
        for a in doc["accessors"]:
            v = doc["bufferViews"][a["bufferView"]]
            self.assertLessEqual(v["byteOffset"] + v["byteLength"], doc["buffers"][0]["byteLength"])
        for m in doc["meshes"]:
            p = m["primitives"][0]
            n = doc["accessors"][p["attributes"]["POSITION"]]["count"]
            self.assertEqual(doc["accessors"][p["attributes"]["JOINTS_0"]]["count"], n)
            self.assertEqual(doc["accessors"][p["indices"]]["count"] % 3, 0)
            for t in p.get("targets", []):
                self.assertEqual(doc["accessors"][t["POSITION"]]["count"], n)
        self.assertEqual(len(doc["skins"][0]["joints"]), len(self.av.skeleton.names))

    def test_unity_json_consistent(self):
        d = unity_dict(self.av, "p.png")
        nb = len(d["bones"])
        for i, b in enumerate(d["bones"]):
            self.assertLess(b["parent"], i)
        for m in d["meshes"]:
            n = len(m["positions"]) // 3
            self.assertEqual(len(m["normals"]) // 3, n)
            self.assertEqual(len(m["uv"]) // 2, n)
            self.assertEqual(len(m["boneIndices"]), n * 4)
            self.assertEqual(len(m["boneWeights"]), n * 4)
            self.assertLess(max(m["triangles"]), n)
            self.assertLess(max(m["boneIndices"]), nb)
            for v in range(n):
                self.assertAlmostEqual(sum(m["boneWeights"][v * 4:v * 4 + 4]), 1.0, places=3)
            for s in m["blendshapes"]:
                self.assertEqual(len(s["deltas"]), len(s["indices"]) * 3)
        names = {b["name"] for b in d["bones"]}
        self.assertTrue({h["bone"] for h in d["humanoid"]} <= names)
        self.assertTrue({d["eyes"]["left"], d["eyes"]["right"]} <= names)
        for pb in d["physbones"]:
            self.assertTrue(set(pb["bones"]) <= names)

    def test_json_keys_match_csharp_classes(self):
        """Os nomes dos campos das classes C# precisam ser exatamente as chaves do JSON (JsonUtility)."""
        with open(os.path.join(ROOT, "Unity/Assets/VRChatAvatarStudio/Editor/VASData.cs"), encoding="utf-8") as f:
            cs = f.read()
        classes = {}
        for m in re.finditer(r"public class (\w+)\s*\{(.*?)\}", cs, re.S):
            fields = re.findall(r"public\s+[\w\[\]]+\s+(\w+)\s*;", m.group(2))
            classes[m.group(1)] = set(fields)
        d = unity_dict(self.av, "p.png")
        self.assertEqual(set(d) - {"rank", "specJson"} - classes["VASAvatarData"], set())
        self.assertEqual(classes["VASAvatarData"] - set(d), set())
        self.assertEqual(set(d["bones"][0]), classes["VASBone"])
        self.assertEqual(set(d["humanoid"][0]), classes["VASHuman"])
        self.assertEqual(set(d["eyes"]), classes["VASEyes"])
        self.assertEqual(set(d["physbones"][0]), classes["VASPhysBone"])
        self.assertEqual(set(d["meshes"][0]), classes["VASMesh"])
        self.assertEqual(set(d["meshes"][0]["blendshapes"][0]), classes["VASShape"])

    def test_palette_png_signature(self):
        self.assertTrue(palette_png(self.av.palette).startswith(b"\x89PNG\r\n\x1a\n"))

    def test_export_manifest_and_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "Avatar")
            files = export_all(self.av, target, "Avatar", glb=True, thumbnail=False)
            self.assertIn("manifest.json", files)
            with open(os.path.join(target, "manifest.json"), encoding="utf-8") as f:
                manifest = json.load(f)
            self.assertEqual(manifest["avatar_format"]["version"], 1)
            self.assertEqual(manifest["application"]["version"], "1.4.0")
            for entry in manifest["files"]:
                path = os.path.join(target, entry["path"])
                with open(path, "rb") as f:
                    digest = hashlib.sha256(f.read()).hexdigest()
                self.assertEqual(entry["sha256"], digest)

    def test_export_failure_preserves_previous_complete_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "Avatar")
            export_all(self.av, target, "Avatar", glb=False, thumbnail=False)
            with open(os.path.join(target, "manifest.json"), "rb") as f:
                before = f.read()
            with mock.patch.object(export_module, "build_glb", side_effect=RuntimeError("falha simulada")):
                with self.assertRaises(RuntimeError):
                    export_all(self.av, target, "Avatar", glb=True, thumbnail=False)
            with open(os.path.join(target, "manifest.json"), "rb") as f:
                after = f.read()
            self.assertEqual(before, after)
            self.assertTrue(os.path.isfile(os.path.join(target, "Avatar.preset.json")))


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def req(self, path, body=None, headers=None, host=None):
        h = {"Host": host or "127.0.0.1:%d" % self.port}
        h.update(headers or {})
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), data=data, headers=h)
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_pages(self):
        for p in ("/", "/app.js", "/viewer.js", "/style.css", "/api/schema"):
            self.assertEqual(self.req(p)[0], 200, p)
        self.assertEqual(self.req("/../studio/server.py")[0], 404)

    def test_security(self):
        self.assertEqual(self.req("/", host="evil.example")[0], 403)
        self.assertEqual(self.req("/api/model", {"spec": {}})[0], 403)                         # sem X-Studio
        self.assertEqual(self.req("/api/model", {"spec": {}}, {"X-Studio": "1", "Host": "evil.example"})[0], 403)

    def test_api(self):
        hdr = {"X-Studio": "1", "Content-Type": "application/json"}
        code, body = self.req("/api/model", {"spec": {"bottom": "skirt"}}, hdr)
        self.assertEqual(code, 200)
        m = json.loads(body)
        self.assertEqual(m["errors"], [])
        self.assertGreater(m["stats"]["triangles"], 1000)
        code, body = self.req("/api/template", {"template": "halo", "spec": {}}, hdr)
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["parts"][0]["shape"], "ring")
        self.assertEqual(self.req("/api/template", {"template": "xx"}, hdr)[0], 400)
        self.assertEqual(self.req("/api/random", {"seed": 3}, hdr)[0], 200)
        code, body = self.req("/api/obj-check", {"text": CUBE}, hdr)
        self.assertEqual(code, 200)
        obj = json.loads(body)
        self.assertTrue(obj["valid"])
        self.assertEqual(obj["info"]["triangles"], 12)

    def test_export_endpoint_contains_manifest_and_hashes(self):
        hdr = {"X-Studio": "1", "Content-Type": "application/json"}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(server, "OUTPUT_DIR", tmp):
            code, body = self.req("/api/export", {"spec": {"name": "TestZip"}}, hdr)
            self.assertEqual(code, 200)
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                names = archive.namelist()
                self.assertIn("TestZip/manifest.json", names)
                manifest = json.loads(archive.read("TestZip/manifest.json"))
                self.assertTrue(manifest["files"])
                for item in manifest["files"]:
                    payload = archive.read("TestZip/" + item["path"])
                    self.assertEqual(hashlib.sha256(payload).hexdigest(), item["sha256"])


class UnitySourceChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = os.path.join(ROOT, "Unity/Assets/VRChatAvatarStudio/Editor")
        def read(name):
            with open(os.path.join(base, name), encoding="utf-8") as f:
                return f.read()
        cls.importer = read("VASImporter.cs")
        cls.setup = read("VASVRChatSetup.cs")
        cls.performance = read("VASPerformanceCheck.cs")

    def test_importer_validates_arrays_and_untrusted_paths(self):
        for needle in ("ValidateAvatarData", "boneWeights", "triangles", "blendshapes", "SafeTextureName",
                       "ReadAndValidatePalette", "StartsWith(prefix", "BuildHumanAvatar"):
            self.assertIn(needle, self.importer)
        self.assertIn('folder + "/" + data.paletteTexture', self.importer)
        self.assertNotIn('folder + "/" + name + "_palette.png"', self.importer)

    def test_importer_has_non_destructive_collision_flow(self):
        for needle in ("DisplayDialogComplex", "Substituir + backup", "Criar cópia", "OperationCanceledException",
                       "AssetDatabase.MoveAsset", "AssetDatabase.DeleteAsset(folder)"):
            self.assertIn(needle, self.importer)

    def test_expression_menus_are_paged_and_capped(self):
        self.assertIn("BuildToggleMenuTree", self.setup)
        self.assertIn("if (items.Count > 8)", self.setup)
        self.assertIn("Math.Min(64", self.setup)
        self.assertNotIn("Take(40)", self.setup)

    def test_performance_is_explicitly_heuristic_and_counts_enabled_renderers(self):
        self.assertIn("estimativa heurística local", self.performance)
        self.assertIn("!r.enabled", self.performance)
        self.assertNotIn("unreadable", self.performance.lower())



class WorkshopStorage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patcher = mock.patch.multiple(
            server.workshop,
            WORKSPACE_DIR=self.root,
            ASSET_DIR=self.root / "assets",
            ASSET_INDEX=self.root / "assets.json",
            TASKS_FILE=self.root / "ai_tasks.json",
        )
        self.patcher.start()

    def tearDown(self):
        server.workshop.configure_api_key("")
        self.patcher.stop()
        self.tmp.cleanup()

    def test_upload_keeps_original_and_hash(self):
        original = b"glTF" + b"original-model-data"
        item = server.workshop.save_asset("Base Model.glb", "base_model", original)
        saved, data = server.workshop.get_asset(item["id"])
        self.assertEqual(data, original)
        self.assertEqual(saved["sha256"], hashlib.sha256(original).hexdigest())
        self.assertTrue(saved["original"])
        self.assertEqual(saved["category"], "base_model")

    def test_asset_hash_change_is_rejected_before_api_usage(self):
        item = server.workshop.save_asset("avatar.glb", "base_model", b"glTF" + b"trusted")
        stored = server.workshop.ASSET_DIR / (item["id"] + ".glb")
        stored.write_bytes(b"glTF" + b"tampered")
        with self.assertRaisesRegex(ValueError, "integridade"):
            server.workshop.get_asset(item["id"])

    def test_model_download_rejects_non_meshy_urls(self):
        with mock.patch.object(server.workshop, "urlopen") as request:
            with self.assertRaisesRegex(ValueError, "domínio seguro"):
                server.workshop._download_model("https://evil.example/model.glb")
            request.assert_not_called()

    def test_upload_rejects_mismatched_file_type_and_unknown_category(self):
        with self.assertRaises(ValueError):
            server.workshop.save_asset("bad.glb", "base_model", b"not-a-glb")
        with self.assertRaises(ValueError):
            server.workshop.save_asset("bad.exe", "accessory", b"MZ")
        with self.assertRaises(ValueError):
            server.workshop.save_asset("thing.obj", "unknown", CUBE.encode())

    def test_preserve_mode_creates_separate_asset_task_not_base_edit(self):
        original = b"glTF" + b"untouched-base"
        base = server.workshop.save_asset("base.glb", "base_model", original)
        server.workshop.configure_api_key("mesh-test-key")
        captured = {}

        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n=-1): return b'{"result":"remote-text-task"}'

        def fake_urlopen(req, timeout=0):
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            captured["authorization"] = req.headers.get("Authorization")
            return Response()

        with mock.patch.object(server.workshop, "urlopen", side_effect=fake_urlopen):
            job = server.workshop.create_task({
                "mode": "preserve", "operation": "text_to_3d", "asset_kind": "hair",
                "prompt": "cabelo longo roxo com mechas em camadas", "base_asset_id": base["id"],
            })
        self.assertEqual(captured["authorization"], "Bearer mesh-test-key")
        self.assertNotIn("model_url", captured["payload"])
        self.assertIn("standalone 3D hair asset", captured["payload"]["prompt"])
        self.assertTrue(job["policy"]["new_asset"])
        self.assertIn("face", job["policy"]["preserve"])
        _, saved_again = server.workshop.get_asset(base["id"])
        self.assertEqual(saved_again, original)

    def test_preserve_mode_refuses_base_retexture_or_remesh(self):
        base = server.workshop.save_asset("base.glb", "base_model", b"glTF" + b"data")
        server.workshop.configure_api_key("mesh-test-key")
        with mock.patch.object(server.workshop, "_meshy_request") as request:
            with self.assertRaisesRegex(ValueError, "modo Preservar"):
                server.workshop.create_task({
                    "mode": "preserve", "operation": "retexture_base", "prompt": "toon shader",
                    "base_asset_id": base["id"],
                })
            request.assert_not_called()

    def test_preserve_mode_can_retexture_separate_accessory_without_touching_base(self):
        base_bytes = b"glTF" + b"base-never-sent-to-retexture"
        accessory_bytes = b"glTF" + b"accessory-only"
        base = server.workshop.save_asset("avatar.glb", "base_model", base_bytes)
        accessory = server.workshop.save_asset("hair.glb", "accessory", accessory_bytes)
        server.workshop.configure_api_key("mesh-test-key")
        captured = {}

        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n=-1): return b'{"result":"remote-accessory-retexture"}'

        def fake_urlopen(req, timeout=0):
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return Response()

        with mock.patch.object(server.workshop, "urlopen", side_effect=fake_urlopen):
            job = server.workshop.create_task({
                "mode": "preserve", "operation": "retexture_base", "prompt": "glossy dark violet hair",
                "base_asset_id": base["id"], "target_asset_id": accessory["id"],
            })
        self.assertIn(base64.b64encode(accessory_bytes).decode("ascii"), captured["payload"]["model_url"])
        self.assertNotIn(base64.b64encode(base_bytes).decode("ascii"), captured["payload"]["model_url"])
        self.assertTrue(job["policy"]["target_is_separate_accessory"])
        _, still_base = server.workshop.get_asset(base["id"])
        _, still_accessory = server.workshop.get_asset(accessory["id"])
        self.assertEqual(still_base, base_bytes)
        self.assertEqual(still_accessory, accessory_bytes)

    def test_ai_task_requires_api_key(self):
        with self.assertRaisesRegex(ValueError, "Configure a chave"):
            server.workshop.create_task({"mode": "preserve", "operation": "text_to_3d", "prompt": "anime hair"})

    def test_personalize_retexture_uses_copy_source_and_never_overwrites_original(self):
        original = b"glTF" + b"base-original-data"
        base = server.workshop.save_asset("avatar.glb", "base_model", original)
        server.workshop.configure_api_key("mesh-test-key")
        captured = {}

        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n=-1): return b'{"result":"remote-retexture-task"}'

        def fake_urlopen(req, timeout=0):
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return Response()

        with mock.patch.object(server.workshop, "urlopen", side_effect=fake_urlopen):
            job = server.workshop.create_task({
                "mode": "personalize", "operation": "retexture_base", "prompt": "anime pastel fabric",
                "base_asset_id": base["id"], "target_asset_id": base["id"],
            })
        self.assertTrue(captured["payload"]["model_url"].startswith("data:application/octet-stream;base64,"))
        self.assertEqual(job["source_sha256"], base["sha256"])
        _, still_original = server.workshop.get_asset(base["id"])
        self.assertEqual(still_original, original)

    def test_successful_task_result_is_saved_as_new_generated_asset(self):
        original = b"glTF" + b"base"
        base = server.workshop.save_asset("base.glb", "base_model", original)
        job = {
            "id": "a" * 32, "remote_id": "remote-task", "route": "text_to_3d", "operation": "text_to_3d",
            "mode": "preserve", "asset_kind": "accessory", "status": "PENDING", "progress": 0,
            "target_asset_id": base["id"], "policy": {"new_asset": True},
        }
        server.workshop._save_job(job)
        with mock.patch.object(server.workshop, "_meshy_request", return_value={
            "status": "SUCCEEDED", "progress": 100,
            "model_urls": {"glb": "https://assets.meshy.ai/example/result.glb"},
        }), mock.patch.object(server.workshop, "_download_model", return_value=b"glTF" + b"generated"):
            finished = server.workshop.poll_task(job["id"])
        self.assertEqual(finished["status"], "SUCCEEDED")
        self.assertTrue(finished.get("result_asset_id"))
        self.assertNotIn("remote_id", server.workshop.list_jobs()[0])
        generated, generated_bytes = server.workshop.get_asset(finished["result_asset_id"])
        self.assertEqual(generated["category"], "generated")
        self.assertEqual(generated_bytes, b"glTF" + b"generated")
        _, still_original = server.workshop.get_asset(base["id"])
        self.assertEqual(still_original, original)


class WorkshopServerRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def request(self, path, body=None, headers=None):
        hdr = {"Host": "127.0.0.1:%d" % self.port}
        hdr.update(headers or {})
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), data=data, headers=hdr)
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def test_workshop_api_pages_and_upload(self):
        import base64
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.multiple(
                server.workshop,
                WORKSPACE_DIR=root,
                ASSET_DIR=root / "assets",
                ASSET_INDEX=root / "assets.json",
                TASKS_FILE=root / "ai_tasks.json",
            ):
                self.assertEqual(self.request("/api/workshop")[0], 200)
                self.assertEqual(self.request("/api/ai/status")[0], 200)
                payload = {"filename": "upload.glb", "category": "base_model",
                           "content_base64": base64.b64encode(b"glTF" + b"upload").decode("ascii")}
                code, raw = self.request("/api/assets/upload", payload, {"X-Studio": "1", "Content-Type": "application/json"})
                self.assertEqual(code, 201)
                asset = json.loads(raw)["asset"]
                code, downloaded = self.request("/api/assets/download/" + asset["id"])
                self.assertEqual(code, 200)
                self.assertEqual(downloaded, b"glTF" + b"upload")


if __name__ == "__main__":
    unittest.main()

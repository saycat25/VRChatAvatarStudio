#!/usr/bin/env python3
"""Gera VRChatAvatarStudio_Unity.unitypackage (duplo clique no Unity para instalar as ferramentas)."""
import hashlib, io, os, tarfile, sys
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "Unity")
META = ("fileFormatVersion: 2\nguid: %s\nMonoImporter:\n  externalObjects: {}\n  serializedVersion: 2\n"
        "  defaultReferences: []\n  executionOrder: 0\n  icon: {instanceID: 0}\n  userData: \n"
        "  assetBundleName: \n  assetBundleVariant: \n")
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "VRChatAvatarStudio_Unity.unitypackage")
with tarfile.open(out, "w:gz") as tar:
    def add(name, data):
        ti = tarfile.TarInfo(name); ti.size = len(data); tar.addfile(ti, io.BytesIO(data))
    for dp, _, fs in os.walk(SRC):
        for f in sorted(fs):
            if not f.endswith(".cs"):
                continue
            full = os.path.join(dp, f)
            rel = os.path.relpath(full, SRC).replace(os.sep, "/")
            guid = hashlib.md5(rel.encode()).hexdigest()
            with open(full, "rb") as source:
                add(guid + "/asset", source.read())
            add(guid + "/asset.meta", (META % guid).encode())
            add(guid + "/pathname", rel.encode())
print("gerado:", out)

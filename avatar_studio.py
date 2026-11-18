#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VRChat Avatar Studio — criador de avatares para o VRChat.

Uso:
  python avatar_studio.py                    abre a interface no navegador (recomendado)
  python avatar_studio.py --preset meu.json --out saida     exporta direto, sem interface
  python avatar_studio.py --random --seed 5 --add halo --add wings_angel
  python avatar_studio.py --list-templates   lista os acessórios prontos
"""
import argparse
import json
import os
import re
import sys

if sys.version_info < (3, 8):
    sys.exit("É preciso Python 3.8 ou mais novo.")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from studio.builder import build_avatar, make_spec, perf_rank, random_spec, spec_to_dict   # noqa: E402
from studio.export import export_all, selfcheck                                           # noqa: E402
from studio.parts import TEMPLATES, expand_template                                       # noqa: E402
from studio.logging_config import configure_logging                                         # noqa: E402
from studio.version import APP_NAME, APP_VERSION                                             # noqa: E402


def cli_export(args):
    if args.preset:
        with open(args.preset, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif args.random:
        data = random_spec(args.seed)
    else:
        data = {}
    if args.name:
        data["name"] = args.name
    if args.detail:
        data["detail"] = str(args.detail)
    spec = make_spec(data)
    parts = list(spec.parts)
    for t in args.add or []:
        if t not in TEMPLATES:
            sys.exit("Modelo desconhecido: %s (use --list-templates)" % t)
        for p in expand_template(t, spec):
            p["id"] = "t%d" % (len(parts) + 1)
            parts.append(p)
    data = spec_to_dict(spec)
    data["parts"] = parts
    av = build_avatar(data)
    err, warn = selfcheck(av)
    for w in warn:
        print("aviso:", w)
    if err:
        sys.exit("Avatar inválido:\n  " + "\n  ".join(err))
    base = re.sub(r"[^\w\-]", "", av.spec.name) or "Avatar"
    out = os.path.join(args.out, base)
    files = export_all(av, out, base, glb=not args.no_glb, thumbnail=not args.no_thumbnail)
    st = av.stats()
    rank, why = perf_rank(st)
    print("Avatar '%s' gerado em %s" % (base, os.path.abspath(out)))
    print("  triângulos: %(triangles)d · ossos: %(bones)d · malhas: %(skinned_meshes)d · blendshapes: %(blendshapes)d" % st)
    print("  ranking de desempenho (PC): %s%s" % (rank, " (limitado por: %s)" % ", ".join(why) if why else ""))
    for f in files:
        print("  -", f)


def main():
    ap = argparse.ArgumentParser(description="VRChat Avatar Studio", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    ap.add_argument("--version", action="version", version="%(prog)s " + APP_VERSION)
    ap.add_argument("--port", type=int, default=8765, help="porta da interface (padrão 8765)")
    ap.add_argument("--no-browser", action="store_true", help="não abrir o navegador sozinho")
    ap.add_argument("--preset", help="arquivo de preset (.json) para exportar sem interface")
    ap.add_argument("--random", action="store_true", help="exportar um avatar aleatório")
    ap.add_argument("--seed", type=int, help="semente do avatar aleatório")
    ap.add_argument("--add", action="append", metavar="MODELO", help="adicionar acessório da biblioteca (repetível)")
    ap.add_argument("--name", help="nome do avatar")
    ap.add_argument("--detail", type=int, choices=(1, 2, 3), help="nível de detalhe da malha")
    ap.add_argument("--out", default=os.path.join(HERE, "output"), help="pasta de saída")
    ap.add_argument("--no-glb", action="store_true", help="não gerar o arquivo .glb")
    ap.add_argument("--no-thumbnail", action="store_true", help="não gerar a miniatura PNG")
    ap.add_argument("--list-templates", action="store_true", help="listar os acessórios prontos")
    args = ap.parse_args()
    configure_logging(HERE)

    if args.list_templates:
        for k, (label, _) in TEMPLATES.items():
            print("%-14s %s" % (k, label))
        return
    if args.preset or args.random or args.add:
        return cli_export(args)
    from studio.server import serve
    serve(args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()

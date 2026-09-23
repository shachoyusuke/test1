#!/usr/bin/env python3
"""EPUB を展開する・展開したフォルダを EPUB に固め直す。

    python3 epub_pack.py unpack <book.epub> <フォルダ>
    python3 epub_pack.py pack <フォルダ> <book.epub> [--touch]

受け取った EPUB を、原稿（src）を経由せずに直接直すときに使う。
固め直すときは EPUB の決まりに合わせる。
  - mimetype を ZIP の先頭に、無圧縮で置く（中身は application/epub+zip）
  - それ以外は名前順に並べて圧縮する（何度固めても同じ並びになる）
  - --touch を付けると、OPF の dcterms:modified を今の時刻に書き換える
"""
import argparse
import datetime
import os
import re
import sys
import zipfile


def unpack(epub, outdir):
    with zipfile.ZipFile(epub) as z:
        names = z.namelist()
        if not names or names[0] != "mimetype":
            print("注意: mimetype が先頭にない", file=sys.stderr)
        z.extractall(outdir)
    print(f"{len(names)} ファイルを {outdir} に展開した")


def touch_opf(folder):
    for root, _, files in os.walk(folder):
        for fn in files:
            if fn.endswith(".opf"):
                p = os.path.join(root, fn)
                s = open(p, encoding="utf-8").read()
                now = datetime.datetime.now(datetime.timezone.utc)
                stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
                s2 = re.sub(r'(<meta property="dcterms:modified">)[^<]*(</meta>)',
                            r"\g<1>" + stamp + r"\g<2>", s)
                if s2 != s:
                    open(p, "w", encoding="utf-8").write(s2)
                    print(f"dcterms:modified を {stamp} にした: {p}")


def pack(folder, epub, touch=False):
    mt = os.path.join(folder, "mimetype")
    if not os.path.exists(mt):
        raise SystemExit("mimetype がない")
    if open(mt, "rb").read() != b"application/epub+zip":
        raise SystemExit("mimetype の中身が application/epub+zip でない")
    if touch:
        touch_opf(folder)
    files = []
    for root, dirs, fs in os.walk(folder):
        dirs.sort()
        for fn in sorted(fs):
            rel = os.path.relpath(os.path.join(root, fn), folder).replace(os.sep, "/")
            if rel == "mimetype" or fn in (".DS_Store", "Thumbs.db"):
                continue
            files.append(rel)
    if os.path.exists(epub):
        os.remove(epub)
    with zipfile.ZipFile(epub, "w") as z:
        z.write(mt, "mimetype", compress_type=zipfile.ZIP_STORED)
        for rel in files:
            z.write(os.path.join(folder, rel), rel,
                    compress_type=zipfile.ZIP_DEFLATED)
    print(f"{len(files) + 1} ファイルを {epub} に固めた")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("unpack")
    u.add_argument("epub")
    u.add_argument("outdir")
    p = sub.add_parser("pack")
    p.add_argument("folder")
    p.add_argument("epub")
    p.add_argument("--touch", action="store_true")
    a = ap.parse_args()
    if a.cmd == "unpack":
        unpack(a.epub, a.outdir)
    else:
        pack(a.folder, a.epub, a.touch)


if __name__ == "__main__":
    main()

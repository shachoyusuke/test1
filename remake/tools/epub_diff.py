#!/usr/bin/env python3
"""二つの EPUB を比べ、どこが違うかを報告する。

    python3 epub_diff.py <A.epub> <B.epub> [--show N]

受け取った EPUB が、手元のソースから再ビルドしたものと同じ中身かを確かめるために使う。
比べるもの:
  - ZIP の中のファイル一覧（片方にしかないもの）
  - 画像・CSS などのバイナリ（SHA-256）
  - OPF のメタデータ（dcterms:modified のようにビルドのたびに変わる値は分けて示す）
  - XHTML の本文テキスト（タグを除き、空白を正規化して行単位で比較）
  - XHTML のマークアップ（テキストが同じでもタグが違う場合）
"""
import argparse
import difflib
import hashlib
import html
import re
import sys
import unicodedata
import zipfile

VOLATILE = [r'<meta property="dcterms:modified">[^<]*</meta>']


def text_lines(xhtml):
    body = xhtml.split("<body", 1)[-1]
    body = re.sub(r"<(p|h[1-6]|li|tr|pre|div|figcaption|dt|dd)\b", r"\n<\1", body)
    t = html.unescape(re.sub(r"<[^>]+>", "", body))
    t = unicodedata.normalize("NFC", t)
    return [re.sub(r"[ \t　]+", " ", l).strip()
            for l in t.split("\n") if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--show", type=int, default=12,
                    help="文書ごとに表示する差分の行数（既定12）")
    x = ap.parse_args()
    za, zb = zipfile.ZipFile(x.a), zipfile.ZipFile(x.b)
    na, nb = set(za.namelist()), set(zb.namelist())
    print(f"A: {x.a}（{len(na)} ファイル）")
    print(f"B: {x.b}（{len(nb)} ファイル）")
    for label, only in (("Aだけにある", na - nb), ("Bだけにある", nb - na)):
        if only:
            print(f"\n{label}: {len(only)} 件")
            for n in sorted(only):
                print("  ", n)
    same, textdiff, markupdiff, bindiff = [], [], [], []
    for n in sorted(na & nb):
        da, db = za.read(n), zb.read(n)
        if da == db:
            same.append(n)
            continue
        if n.endswith((".xhtml", ".html", ".opf", ".ncx", ".css", ".xml")):
            sa, sb = da.decode("utf-8"), db.decode("utf-8")
            va, vb = sa, sb
            for pat in VOLATILE:
                va, vb = re.sub(pat, "", va), re.sub(pat, "", vb)
            if va == vb:
                same.append(n + "（ビルド日時のみ違う）")
                continue
            if n.endswith((".xhtml", ".html")):
                la, lb = text_lines(sa), text_lines(sb)
                if la == lb:
                    markupdiff.append(n)
                else:
                    textdiff.append((n, la, lb))
            else:
                textdiff.append((n, sa.splitlines(), sb.splitlines()))
        else:
            bindiff.append((n, hashlib.sha256(da).hexdigest()[:12],
                            hashlib.sha256(db).hexdigest()[:12],
                            len(da), len(db)))
    print(f"\n一致: {len(same)} 件")
    for n in same:
        if "ビルド日時" in n:
            print("  ", n)
    if bindiff:
        print(f"\nバイナリが違う: {len(bindiff)} 件")
        for n, ha, hb, sa, sb in bindiff:
            print(f"   {n}: {ha}（{sa:,}B）→ {hb}（{sb:,}B）")
    if markupdiff:
        print(f"\nテキストは同じでマークアップだけ違う: {len(markupdiff)} 件")
        for n in markupdiff:
            print("  ", n)
    if textdiff:
        print(f"\n中身が違う: {len(textdiff)} 件")
        for n, la, lb in textdiff:
            sm = difflib.SequenceMatcher(a=la, b=lb, autojunk=False)
            ratio = sm.ratio()
            print(f"\n== {n}（一致率 {ratio:.1%}、A {len(la)} 行 / B {len(lb)} 行）")
            shown = 0
            for line in difflib.unified_diff(la, lb, "A", "B", n=0,
                                             lineterm=""):
                if line.startswith(("---", "+++", "@@")):
                    continue
                print("   " + line[:160])
                shown += 1
                if shown >= x.show:
                    print("   …")
                    break
    if not (na ^ nb or bindiff or markupdiff or textdiff):
        print("\n→ 中身は同じ（違いはビルド日時だけ）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

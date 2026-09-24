#!/usr/bin/env python3
"""EPUB の本文XHTMLを、章ごとの Markdown に変換する。

    python3 xhtml2md.py <book.epub | OEBPS/Text ディレクトリ> <出力ディレクトリ>
                        [--keep-results] [--only ch00,ch01,...]

用途は二つある。
  1. 人（やエージェント）が本文を通読するための、読みやすいテキスト版を作る
  2. natural-japanese の lint.py にかける入力を作る

lint.py（textcore.mask_markdown_structure）は、見出し・箇条書き・コード・
引用・表の行をマスクして、地の文だけを検査する。そこで次のように書き分ける。
  - 地の文（段落、囲み記事の中の段落、確認問題の解説）… 段落のまま出す → 検査される
  - 見出し・箇条書き・コード・表 … Markdown の書式で出す → マスクされる
  - 過去問題の引用（div.kakomon）、関係スキーマ、出典表示、図表の題
    … 引用（> ）で出す → マスクされる（原文どおりの引用は書き換えの対象外のため）
  - SQL の実行結果の表 … 省く（--keep-results で残す）
  - 注番号・「目次へ」… 省く
"""
import argparse
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

XHTML_NS = "{http://www.w3.org/1999/xhtml}"


def local(tag):
    return tag.split("}", 1)[-1] if isinstance(tag, str) else ""


def classes(el):
    return set((el.get("class") or "").split())


def inline_child(ch):
    """子要素1つ（後ろに続くテキストを含む）を文字列にする。"""
    tag, cls = local(ch.tag), classes(ch)
    if tag == "code":
        s = "`" + "".join(ch.itertext()) + "`"
    elif (tag == "a" and "ref" in cls) or tag == "sup":
        s = ""
    elif tag == "br":
        s = " / "
    else:
        s = inline(ch)
    return s + (ch.tail or "")


def inline(el):
    """要素の中身を1行のテキストにする。コードは `…`、注番号は省く。"""
    parts = [el.text or ""] + [inline_child(ch) for ch in el]
    return re.sub(r"\s*\n\s*", "", "".join(parts)).strip()


class Converter:
    def __init__(self, keep_results=False):
        self.keep_results = keep_results
        self.out = []

    def blank(self):
        if self.out and self.out[-1] != "":
            self.out.append("")

    def emit(self, line, quote=False):
        self.out.append(("> " + line) if quote else line)

    def para(self, text, quote=False):
        if not text:
            return
        self.blank()
        self.emit(text, quote)
        self.blank()

    def table(self, el, quote=False):
        rows = []
        for tr in el.iter(XHTML_NS + "tr"):
            cells = [inline(c).replace("|", "｜") for c in tr
                     if local(c.tag) in ("th", "td")]
            rows.append("| " + " | ".join(cells) + " |")
        if not rows:
            return
        self.blank()
        self.emit(rows[0], quote)
        self.emit("|" + "---|" * rows[0].count(" | ") + "---|", quote)
        for r in rows[1:]:
            self.emit(r, quote)
        self.blank()

    def walk(self, el, quote=False):
        for ch in el:
            self.block(ch, quote)

    def block(self, el, quote=False):
        tag, cls = local(el.tag), classes(el)
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            if tag == "h1":
                spans = [inline(s) for s in el if "chno" in classes(s)
                         or "chttl" in classes(s)]
                text = "　".join(spans) if spans else inline(el)
            else:
                text = inline(el)
            self.blank()
            self.emit("#" * level + " " + text, quote)
            self.blank()
        elif tag == "p":
            if cls & {"totoc", "runfile", "codehead"}:
                return
            if cls & {"reshead", "rescount", "resmsg"}:
                if self.keep_results:
                    self.para(inline(el), quote=True)
                return
            if cls & {"rel", "src", "srcs", "treettl", "pmcap", "chlabel"}:
                self.para(inline(el), quote=True)
                return
            if cls & {"qno", "ano"}:
                self.blank()
                self.emit("#### " + inline(el), quote)
                self.blank()
                return
            self.para(inline(el), quote)
        elif tag in ("ul", "ol"):
            self.blank()
            for li in el:
                if local(li.tag) != "li":
                    continue
                own = [li.text or ""]
                nested = []
                for c in li:
                    if local(c.tag) in ("ul", "ol"):
                        nested.append(c)
                        own.append(c.tail or "")
                    else:
                        own.append(inline_child(c))
                text = re.sub(r"\s*\n\s*", "", "".join(own)).strip()
                self.emit("- " + text, quote)
                for n in nested:
                    sub = Converter(self.keep_results)
                    sub.block(n)
                    for line in sub.out:
                        if line:
                            self.emit("  " + line, quote)
            self.blank()
        elif tag == "pre":
            code = "".join(el.itertext()).rstrip("\n")
            lang = (cls - {"code"}).pop() if cls - {"code"} else ""
            self.blank()
            self.emit("```" + lang, quote)
            for line in code.split("\n"):
                self.emit(line, quote)
            self.emit("```", quote)
            self.blank()
        elif tag == "table":
            if "res" in cls and not self.keep_results:
                return
            self.table(el, quote=quote or "res" in cls)
        elif tag == "figure":
            cap = el.find(XHTML_NS + "figcaption")
            img = el.find(XHTML_NS + "img")
            name = os.path.basename(img.get("src", "")) if img is not None else ""
            if cap is not None:
                self.para(f"［図 {name}］" + inline(cap), quote=True)
        elif tag == "div":
            if "kakomon" in cls:
                self.walk(el, quote=True)
                self.blank()
            elif "table-caption" in cls:
                self.para(inline(el), quote=True)
            else:
                self.walk(el, quote)
        elif tag in ("section", "nav", "body", "dl"):
            self.walk(el, quote)
        elif tag == "dt":
            self.para("**" + inline(el) + "**", quote)
        elif tag == "dd":
            self.para(inline(el), quote)
        else:
            text = inline(el)
            if text:
                self.para(text, quote)

    def text(self):
        s = "\n".join(self.out).strip("\n") + "\n"
        return re.sub(r"\n{3,}", "\n\n", s)


def load_xhtml(src):
    """(ファイル名, バイト列) を返す。src は EPUB か Text ディレクトリ。"""
    if zipfile.is_zipfile(src):
        z = zipfile.ZipFile(src)
        for n in sorted(z.namelist()):
            if n.endswith(".xhtml"):
                yield os.path.basename(n), z.read(n)
    else:
        for n in sorted(os.listdir(src)):
            if n.endswith(".xhtml"):
                with open(os.path.join(src, n), "rb") as f:
                    yield n, f.read()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("src")
    ap.add_argument("outdir")
    ap.add_argument("--keep-results", action="store_true")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    only = set(filter(None, a.only.split(",")))
    os.makedirs(a.outdir, exist_ok=True)
    n = 0
    for name, data in load_xhtml(a.src):
        stem = name[:-6]
        if only and stem not in only:
            continue
        root = ET.fromstring(data)
        body = root.find(XHTML_NS + "body")
        if body is None:
            continue
        c = Converter(a.keep_results)
        c.walk(body)
        with open(os.path.join(a.outdir, stem + ".md"), "w",
                  encoding="utf-8") as f:
            f.write(c.text())
        n += 1
    print(f"{n} ファイルを {a.outdir} に書き出した", file=sys.stderr)


if __name__ == "__main__":
    main()

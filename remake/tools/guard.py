#!/usr/bin/env python3
"""リメイク中の原稿が、変えてはいけない箇所を変えていないかを調べる。

    python3 guard.py <元の src ディレクトリ> <作業中の src ディレクトリ> [--facts facts.txt]

「エラー」は原則として元に戻すもの、「確認」は意図した変更なら残してよいもの。
  エラー（原則として変えない）
    - 午後問題の原文（:::pm〜:::endpm）
    - 確認問題の問題部分（:::quiz〜===）と、答えの記号（A1 ウ など）
    - 出典コード（Q1 出典=R3a-26* など）
  確認（変えたなら理由を台帳に書く）
    - SQL のコード（~~~sql〜~~~）。変えると実行結果と本文の説明がずれる
    - 図・表の ID とキャプション（@fig・@table・@pmfig）。図は描画済み
    - 節番号（## 1.2 など）。<<1.2>> の参照先になっている
    - 注（^[key]）の増減、用語の定義箇所（{{語}}）の増減
    - 地の文に新しく現れた数値（通しケースの数字は SQL か facts.txt で確かめる）
"""
import argparse
import collections
import glob
import os
import re
import sys


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def blocks(text, start, end):
    """start で始まり end で終わる行の範囲を、中身の文字列のリストで返す。"""
    out, cur = [], None
    for ln in text.split("\n"):
        s = ln.strip()
        if cur is None and start(s):
            cur = [ln]
        elif cur is not None:
            cur.append(ln)
            if end(s):
                out.append("\n".join(cur))
                cur = None
    return out


def quiz_parts(text):
    qs, keys, srcs = [], [], []
    for b in blocks(text, lambda s: s.startswith(":::quiz"),
                    lambda s: s == ":::"):
        q, _, a = b.partition("\n===\n")
        qs.append(q)
        keys += re.findall(r"^A(\d+)\s+(\S.*)$", a, re.M)
        srcs += re.findall(r"^Q(\d+)\s+(出典=\S+)?", q, re.M)
    return qs, keys, srcs


def sql_blocks(text):
    return [re.sub(r"[ \t]+$", "", b, flags=re.M)
            for b in blocks(text, lambda s: s.startswith("~~~sql"),
                            lambda s: s == "~~~")]


def prose_numbers(text):
    """コード・表・過去問題を除いた地の文に出る数値（3桁以上か、桁区切りつき）。"""
    kept, mode = [], None
    for ln in text.split("\n"):
        s = ln.strip()
        if mode == "code":
            mode = None if s == "~~~" else mode
            continue
        if mode == "pm":
            mode = None if s == ":::endpm" else mode
            continue
        if mode == "quiz":
            mode = None if s == "===" else mode
            continue
        if s.startswith("~~~"):
            mode = "code"
            continue
        if s.startswith(":::pm"):
            mode = "pm"
            continue
        if s.startswith(":::quiz"):
            mode = "quiz"
            continue
        if s.startswith(("|", "@", "%%", "##")):
            continue
        kept.append(s)
    body = "\n".join(kept)
    body = re.sub(r"<<[^>]+>>|\^\[[^\]]+\]", "", body)
    return collections.Counter(
        re.findall(r"(?<![\d.])\d{1,3}(?:,\d{3})+(?![\d])|(?<![\d.,])\d{3,}(?![\d,])",
                   body))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("orig")
    ap.add_argument("work")
    ap.add_argument("--facts", default=None)
    a = ap.parse_args()
    facts = read(a.facts) if a.facts else ""
    errors, checks = [], []
    names = sorted({os.path.relpath(p, a.orig)
                    for p in glob.glob(os.path.join(a.orig, "**", "*.txt"),
                                       recursive=True)}
                   | {os.path.relpath(p, a.work)
                      for p in glob.glob(os.path.join(a.work, "**", "*.txt"),
                                         recursive=True)})
    for name in names:
        po, pw = os.path.join(a.orig, name), os.path.join(a.work, name)
        if not os.path.exists(pw):
            errors.append(f"{name}: 作業中の原稿にない（削除された）")
            continue
        if not os.path.exists(po):
            checks.append(f"{name}: 新しいファイル")
            continue
        o, w = read(po), read(pw)
        if o == w:
            continue
        is_pm = lambda s: s.startswith(":::pm")
        end_pm = lambda s: s == ":::endpm"
        if blocks(o, is_pm, end_pm) != blocks(w, is_pm, end_pm):
            errors.append(f"{name}: 午後問題の原文（:::pm）が変わった")
        qo, ko, so = quiz_parts(o)
        qw, kw, sw = quiz_parts(w)
        if qo != qw:
            errors.append(f"{name}: 確認問題の問題部分（:::quiz〜===）が変わった")
        if [k[0] + k[1].split()[0] for k in ko] != \
                [k[0] + k[1].split()[0] for k in kw]:
            errors.append(f"{name}: 確認問題の答えの記号が変わった: "
                          f"{ko} → {kw}")
        if so != sw:
            errors.append(f"{name}: 出典コードが変わった: {so} → {sw}")
        if sql_blocks(o) != sql_blocks(w):
            no, nw = sql_blocks(o), sql_blocks(w)
            gone = [b.split("\n")[1][:40] for b in no if b not in nw]
            new = [b.split("\n")[1][:40] for b in nw if b not in no]
            checks.append(f"{name}: SQLのコードが変わった（{len(no)}→{len(nw)}本。"
                          f"消えた {len(gone)}、増えた {len(new)}）"
                          + (f" 消えた例: {gone[:3]}" if gone else "")
                          + (f" 増えた例: {new[:3]}" if new else ""))
        for pat, label in [(r"^\s*@(?:fig|pmfig|table)\s+.*$", "図表のIDとキャプション"),
                           (r"^## [0-9A-G終]+\.[0-9]+", "節番号")]:
            fo = re.findall(pat, o, re.M)
            fw = re.findall(pat, w, re.M)
            if fo != fw:
                diff = [x for x in fo if x not in fw] + ["→"] + \
                    [x for x in fw if x not in fo]
                checks.append(f"{name}: {label}が変わった: {diff}")
        for pat, label in [(r"\^\[([^\]]+)\]", "注"), (r"\{\{([^}]+)\}\}", "定義語")]:
            co = collections.Counter(re.findall(pat, o))
            cw = collections.Counter(re.findall(pat, w))
            if co != cw:
                checks.append(f"{name}: {label}の増減: 減 {dict(co - cw)} ／ 増 {dict(cw - co)}")
        no, nw = prose_numbers(o), prose_numbers(w)
        new_nums = [n for n in (nw - no) if n not in facts and n.replace(",", "") not in facts]
        if new_nums:
            checks.append(f"{name}: 地の文に新しい数値（SQLかfacts.txtで確かめる）: "
                          f"{sorted(set(new_nums))[:15]}")
    for e in errors:
        print("エラー:", e)
    for c in checks:
        print("確認:", c)
    print(f"\nエラー {len(errors)} 件 ／ 確認 {len(checks)} 件")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

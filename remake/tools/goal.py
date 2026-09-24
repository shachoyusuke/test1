#!/usr/bin/env python3
"""リメイクの完成条件をまとめて判定する（ゴールコマンド）。

    python3 remake/tools/goal.py          # 全部を判定する
    python3 remake/tools/goal.py --fast   # EPUBCheck と lint を省く途中確認（PASSED にはならない）

最終行が「GOAL: PASSED」なら完成。そうでなければ、未達の項目と件数を出す。
判定は4つの群に分かれる。

  A 壊していない  ビルド、EPUBCheck、内部リンク、過去問題の原文と正答、出典、地の文の新しい数値の裏取り
  B 別の顔        CSS・表紙・副題・章の入口と出口が、見本（合同会社の本）の型から離れている
  C 読む気がわく  文のリズム（lint）、定義の囲みと先送りの数、登場人物、節の記号、図の文字の大きさ、B+木の図
  D 通読と採点    前付と全章を読者として通読し、natural-japanese の6軸ルーブリックで採点した記録
                  （remake/goal/review.json）が、いまの本文に対してある

D は読み手役のサブエージェントを使わず、書き手が自分で通読して記録する。章ごとに本文の指紋を
残すので、本文を直した章だけが読み直しの対象になる。
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.dirname(HERE)
BOOK = os.path.join(R, "book")
ORIG = os.path.join(R, "book-orig")
GOAL = os.path.join(R, "goal")
WORK = os.path.join(R, "work", "goal")
CHAPTERS = [f"ch{n:02d}" for n in range(14)]
NAMES = ["宇佐美", "椎野", "沢井", "葛西", "真壁"]
sys.path.insert(0, HERE)

results = []


def check(group, cid, ok, label, detail=""):
    results.append((group, cid, bool(ok), label, detail))


def run(cmd, cwd=None, timeout=1800):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout)


def content_hash(epub):
    """本文・CSS・画像だけから作る指紋。ビルド日時の入る OPF と NCX は含めない。"""
    z = zipfile.ZipFile(epub)
    h = hashlib.sha256()
    for n in sorted(z.namelist()):
        if n.endswith((".opf", ".ncx")) or n == "mimetype":
            continue
        h.update(n.encode())
        h.update(z.read(n))
    return h.hexdigest()


def prose_of_md(path):
    """xhtml2md の出力から、引用・コード・表・見出しを除いた地の文を返す。"""
    out, incode = [], False
    for line in open(path, encoding="utf-8"):
        if line.startswith("```"):
            incode = not incode
            continue
        if incode or line.startswith((">", "|", "#")):
            continue
        out.append(line)
    return "".join(out)


def css_rules(path):
    """CSS を（セレクタ、プロパティ、値）の組の集合にする。"""
    s = re.sub(r"/\*.*?\*/", "", open(path, encoding="utf-8").read(), flags=re.S)
    rules = set()
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", s):
        for one in sel.split(","):
            one = " ".join(one.split())
            for decl in body.split(";"):
                if ":" in decl:
                    k, v = decl.split(":", 1)
                    rules.add((one, k.strip(), " ".join(v.split())))
    return rules


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    a = ap.parse_args()
    os.makedirs(WORK, exist_ok=True)

    # ---------------------------------------------------------- A 壊していない
    p = run(["python3", "tools/build.py"], cwd=BOOK)
    log = p.stdout + p.stderr
    errs = [l for l in log.splitlines() if l.startswith("エラー")]
    check("A", "A1", p.returncode == 0 and not errs, "ビルドが通る",
          f"エラー {len(errs)} 件" + (f"（{errs[0][:80]}）" if errs else ""))
    epubs = sorted(glob.glob(os.path.join(BOOK, "dist", "*.epub")),
                   key=os.path.getmtime)
    if not epubs or p.returncode != 0:
        print("ビルドが通らないので、ここで止める。\n" + "\n".join(errs[:20]))
        print("GOAL: NOT YET（ビルド失敗）")
        return 1
    epub = os.path.join(WORK, "book.epub")
    shutil.copy(epubs[-1], epub)
    chash = content_hash(epub)
    z = zipfile.ZipFile(epub)
    xnames = [n for n in z.namelist() if n.endswith(".xhtml")]

    if a.fast:
        check("A", "A2", False, "EPUBCheck が 0 件", "--fast では判定しない")
    else:
        jars = sorted(glob.glob(os.path.join(R, ".tools", "epubcheck-*",
                                             "epubcheck.jar")),
                      key=lambda j: [int(x) for x in re.findall(r"\d+", j.split("epubcheck-")[-1])])
        if not jars:
            check("A", "A2", False, "EPUBCheck が 0 件", "EPUBCheck がない")
        else:
            out = run(["java", "-jar", jars[-1], epub]).stdout
            m = re.search(r"Messages: (\d+) fatals / (\d+) errors / (\d+) warnings", out)
            ok = bool(m) and m.groups() == ("0", "0", "0")
            check("A", "A2", ok, "EPUBCheck が 0 件",
                  (f"{m.group(1)} fatals / {m.group(2)} errors / {m.group(3)} warnings"
                   if m else "結果を読めない") + f"（{os.path.basename(os.path.dirname(jars[-1]))}）")

    ids, hrefs = set(), []
    for n in xnames:
        s = z.read(n).decode()
        b = n.split("/")[-1]
        ids |= {b + "#" + i for i in re.findall(r'id="([^"]+)"', s)}
        hrefs += [(b, h) for h in re.findall(r'href="([^"]+)"', s)
                  if not h.startswith(("http", "../"))]
    bad = [(b, h) for b, h in hrefs if "#" in h
           and ((h.split("#")[0] or b) + "#" + h.split("#")[1]) not in ids]
    check("A", "A3", not bad, "内部リンクが全部つながる",
          f"{len(hrefs)} 本中 未解決 {len(bad)}")

    g = run(["python3", os.path.join(HERE, "guard.py"), os.path.join(ORIG, "src"),
             os.path.join(BOOK, "src"), "--facts",
             os.path.join(ORIG, "plan", "guide", "facts.txt")])
    m = re.search(r"エラー (\d+) 件 ／ 確認 (\d+) 件", g.stdout)
    gerr = [l for l in g.stdout.splitlines() if l.startswith("エラー:")]
    check("A", "A4", m and m.group(1) == "0",
          "過去問題の原文・確認問題の問題文と正答・出典コードが元のまま",
          (gerr[0][4:90] if gerr else "変更なし"))

    TERM = {"h": "春", "a": "秋", "o": "-10月", "t": "特別"}
    ans = {}
    for line in open(os.path.join(BOOK, "kakomon", "am_answers.md"), encoding="utf-8"):
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) >= 3 and c[1].isdigit() and c[2] in "アイウエ":
            ans[(c[0], c[1])] = c[2]
    ok_n = ng_n = 0
    for f in sorted(glob.glob(os.path.join(BOOK, "src", "quiz", "*.txt"))):
        s = open(f, encoding="utf-8").read()
        amap = dict(re.findall(r"^A(\d+)\s+([アイウエ])\s*$", s, re.M))
        for no, code in re.findall(r"^Q(\d+)\s+出典=([A-Za-z0-9-]+)\*?\s*$", s, re.M):
            era, y, t, q = re.match(r"([HR])(\d+)([haot])-(\d+)$", code).groups()
            if ans.get((f"{era}{y}{TERM[t]}", q)) == amap.get(no):
                ok_n += 1
            else:
                ng_n += 1
    alltext = "".join(z.read(n).decode() for n in xnames)
    r8 = "出典：令和8年度" in alltext
    check("A", "A5", ng_n == 0 and ok_n == 53 and not r8,
          "午前の過去問題53問の正答が正答表と一致し、令和8年度の問題がない",
          f"一致 {ok_n} ／ 不一致 {ng_n}" + ("／令和8年度あり" if r8 else ""))

    approved = set()
    ap_path = os.path.join(GOAL, "numbers_ok.txt")
    if os.path.exists(ap_path):
        for line in open(ap_path, encoding="utf-8"):
            t = line.split("#")[0].strip()
            if t:
                approved.add(t)
    new_nums = []
    for line in g.stdout.splitlines():
        mm = re.search(r"地の文に新しい数値.*?: \[(.*)\]", line)
        if mm:
            new_nums += re.findall(r"'([^']+)'", mm.group(1))
    unverified = sorted(set(n for n in new_nums if n not in approved))
    check("A", "A6", not unverified,
          "地の文の新しい数値は、SQL か facts で確かめて numbers_ok.txt に記録済み",
          f"未確認 {len(unverified)} 件" + (f"：{unverified[:8]}" if unverified else ""))

    # ---------------------------------------------------------- B 別の顔
    sample = css_rules(os.path.join(ORIG, "tools", "kindle_sample.css"))
    cur = css_rules(os.path.join(BOOK, "tools", "kindle.css"))
    ratio = len(sample & cur) / max(len(sample), 1)
    check("B", "B1", ratio < 0.25, "CSS が見本（合同会社の本）から離れている",
          f"見本と同じ指定 {ratio:.0%}（25%未満で合格）")

    try:
        from PIL import Image
        im = Image.open(os.path.join(BOOK, "figs", "cover.jpg")).convert("RGB").resize((64, 100))
        px = list(im.getdata())
        navy = sum(1 for (r_, g_, b_) in px if b_ > r_ + 15 and b_ >= g_ and r_ + g_ + b_ < 330)
        frac = navy / len(px)
        same = open(os.path.join(BOOK, "figs", "cover.jpg"), "rb").read() == \
            open(os.path.join(ORIG, "figs", "cover.jpg"), "rb").read()
        check("B", "B2", frac < 0.3 and not same, "表紙が作り直され、紺地の表紙ではない",
              f"紺色の面積 {frac:.0%}" + ("／元の表紙のまま" if same else ""))
    except Exception as e:
        check("B", "B2", False, "表紙が作り直され、紺地の表紙ではない", f"判定できない: {e}")

    bp = open(os.path.join(BOOK, "tools", "build.py"), encoding="utf-8").read()
    sub = re.search(r'^SUBTITLE = "([^"]*)"', bp, re.M)
    subt = sub.group(1) if sub else ""
    check("B", "B3", subt and not subt.endswith("ひとつながりになる本"),
          "副題が「〜がひとつながりになる本」の型でない", f"副題：{subt}")

    srcs = {c: open(os.path.join(BOOK, "src", c + ".txt"), encoding="utf-8").read()
            for c in CHAPTERS}
    bridge = sum(len(re.findall(
        r"(序章|第\s*\d+\s*章)(で|では|までで|までは)、?[^。\n]{0,90}。\s*ここ(から|で)は", s))
        for s in srcs.values())
    check("B", "B4", bridge == 0, "章の入口に「第N章では〜。ここからは〜」の型がない",
          f"{bridge} 箇所")
    nxt = [c for c, s in srcs.items() if re.search(r"^:::next\s*$", s, re.M)]
    cq = [c for c, s in srcs.items() if re.search(r"^@cq ", s, re.M)]
    check("B", "B5", len(nxt) <= 3 and len(cq) <= 3,
          "全章同じ「章の問い」と「後で効いてくる場面」をやめている",
          f"章の問い {len(cq)} 章、後で効いてくる場面 {len(nxt)} 章（どちらも3章まで）")

    # ---------------------------------------------------------- C 読む気がわく
    md_dir = os.path.join(WORK, "md")
    shutil.rmtree(md_dir, ignore_errors=True)
    run(["python3", os.path.join(HERE, "xhtml2md.py"), epub, md_dir])
    if a.fast:
        check("C", "C1", False, "各章の文のリズムが単調でない（lint）", "--fast では判定しない")
    else:
        import nj_score
        burst, low = [], []
        for c in CHAPTERS:
            path = os.path.join(md_dir, c + ".md")
            res = nj_score.run_lint(path, "tech")
            n = len(open(path, encoding="utf-8").read())
            sc, _ = nj_score.score(res["findings"], n)
            if any(f["category"] == "low_burstiness" for f in res["findings"]):
                burst.append(c)
            if sc < 95:
                low.append(f"{c}={sc:.0f}")
        check("C", "C1", not burst and not low,
              "各章の文のリズムが単調でなく、自然度が95点以上（lint, tech）",
              f"リズム単調 {len(burst)} 章 {burst[:6]}" + (f"／95点未満 {low}" if low else ""))

    defs = sum(len(re.findall(r"^:::def\b", s, re.M)) for s in srcs.values())
    check("C", "C2", defs <= 30, "「定義」の囲みが30個以下（元は117個）", f"{defs} 個")

    prose = {c: prose_of_md(os.path.join(md_dir, c + ".md")) for c in CHAPTERS}
    defer = sum(len(re.findall(
        r"(で|に)(もう一度)?扱う|で詳しく扱う|で見る。|にまとめ|にある。|で作る。|で読み解く", t))
        for t in prose.values())
    check("C", "C3", defer <= 35, "「◯.◯で扱う」のような先送りが35回以下（元は97回）",
          f"{defer} 回")

    with_names = [c for c, t in prose.items() if any(nm in t for nm in NAMES)]
    check("C", "C4", len(with_names) >= 10,
          "登場人物が序章から終章の14章のうち10章以上に出てくる",
          f"{len(with_names)} 章")

    h2 = re.findall(r"<h2\b[^>]*>(.*?)</h2>", alltext, re.S)
    tagged = [x for x in h2 if 'class="tag' in x]
    tratio = len(tagged) / max(len(h2), 1)
    check("C", "C5", tratio <= 0.10, "節見出しの記号（科目A・科目B など）が1割以下",
          f"{len(tagged)} / {len(h2)} 節")

    meta_path = os.path.join(BOOK, "figs", "_meta.json")
    used = sorted({os.path.basename(n)[:-4] for n in z.namelist()
                   if n.startswith("OEBPS/Images/") and n.endswith(".png")})
    if not os.path.exists(meta_path):
        check("C", "C6", False, "図の中のいちばん小さい文字が、スマホ幅で9pt相当以上",
              "図の記録（figs/_meta.json）がない。図を描き直すと作られる")
        check("C", "C7", False, "B+木の図（f11-btree）に申込番号1001〜1018がすべて描かれている",
              "図の記録がない")
    else:
        meta = json.load(open(meta_path, encoding="utf-8"))
        small = []
        for name in used:
            mm = meta.get(name)
            if not mm:
                small.append(f"{name}=記録なし")
                continue
            pt = mm["min_font"] * 390 / mm["width"]
            if pt < 9.0:
                small.append(f"{name}={pt:.1f}")
        check("C", "C6", not small, "図の中のいちばん小さい文字が、スマホ幅で9pt相当以上",
              f"足りない図 {len(small)} 点" + (f"：{small[:6]}" if small else ""))
        labels = " ".join(meta.get("f11-btree", {}).get("labels", []))
        missing = [str(n) for n in range(1001, 1019) if str(n) not in labels]
        check("C", "C7", "f11-btree" in meta and not missing,
              "B+木の図（f11-btree）に申込番号1001〜1018がすべて描かれている",
              f"欠け {missing}" if missing else "全部ある")

    # ---------------------------------------------------------- D 通読と採点
    # 読み手役のサブエージェントは使わない。書き手（このセッション）が、組み上がった章を
    # 読者として通読し、natural-japanese の6軸ルーブリックで採点して review.json に残す。
    # 章ごとに本文（XHTML）の指紋を記録するので、直した章だけ読み直せばよい。
    AXES = ["脱AI臭", "情報密度", "機能性", "論理の明晰性", "人間味", "自己証明力"]
    docs = ["frontmatter"] + CHAPTERS
    rv_path = os.path.join(GOAL, "review.json")
    review = json.load(open(rv_path, encoding="utf-8")) if os.path.exists(rv_path) else {}
    missing, stale, weak = [], [], []
    for d in docs:
        n = f"OEBPS/Text/{d}.xhtml"
        h = hashlib.sha256(z.read(n)).hexdigest() if n in z.namelist() else None
        e = review.get(d)
        if not e:
            missing.append(d)
            continue
        if e.get("hash") != h:
            stale.append(d)
            continue
        sc = e.get("scores", {})
        vals = [sc.get(ax, 0) for ax in AXES]
        if min(vals) < 90 or sum(vals) / len(vals) < 92 or not e.get("note"):
            weak.append(f"{d}(最低{min(vals)}・平均{sum(vals) / len(vals):.0f})")
    check("D", "D1", not (missing or stale or weak),
          "前付と全章を通読し、6軸すべて90点以上・平均92点以上（review.json）",
          f"未読 {len(missing)}、読んだ後に変わった {len(stale)}"
          + (f" {stale[:5]}" if stale else "") + f"、点が足りない {weak[:5]}")

    # ---------------------------------------------------------- 表示
    names = {"A": "壊していない", "B": "合同会社の本と別の顔", "C": "読む気がわく",
             "D": "通読と採点"}
    print(f"本文の指紋: {chash[:16]}　EPUB: {os.path.basename(epubs[-1])}")
    for grp in "ABCD":
        print(f"\n[{grp}] {names[grp]}")
        for g_, cid, ok, label, detail in results:
            if g_ == grp:
                print(f"  {'✅' if ok else '❌'} {cid} {label} — {detail}")
    failed = [r for r in results if not r[2]]
    print()
    if a.fast:
        print(f"GOAL: NOT YET（--fast の途中確認。未達 {len(failed)} 件）")
        return 1
    if failed:
        print(f"GOAL: NOT YET（未達 {len(failed)} 件：{'、'.join(r[1] for r in failed)}）")
        return 1
    print("GOAL: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""natural-japanese の lint.py を複数の Markdown にかけ、章ごとの自然度スコアを表にする。

    python3 nj_score.py [--genre tech] [--json-dir DIR] [--reading-load]
                        [--experimental] <file.md>...

スコアは references/diagnose.md の「機械ベース」の式による（高いほど自然）。
    減点 = (critical×8 + warn×4 + info×0.5) × (1000 / max(文字数, 1000))
    機械ベース = max(100 − 減点, 20)
判断調整（±15点）は人が行うもので、ここでは計算しない。

--json-dir     各ファイルの lint --json の出力を保存する（次の周回の --baseline に使う）
--reading-load 読解負荷レーン（スコアに入らない指さし）の件数も数える
--experimental 未校正の実験的検出器（太字・箇条書き・定型見出し・段落頭の接続詞など）
               の件数を別の列に出す。スコアには入れない
"""
import argparse
import collections
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
# リポジトリに同梱したスキル（.claude/skills）を優先し、なければ参考資料の複製を使う
LINT = next(p for p in [
    os.path.join(os.path.dirname(os.path.dirname(HERE)), ".claude", "skills",
                 "natural-japanese", "scripts", "lint.py"),
    os.path.join(os.path.dirname(HERE), "ref", "natural-japanese", "skills",
                 "natural-japanese", "scripts", "lint.py"),
] if os.path.exists(p))
WEIGHT = {"critical": 8, "warn": 4, "info": 0.5}


def run_lint(path, genre=None, extra=()):
    cmd = ["uv", "run", "--quiet", LINT, path, "--json", *extra]
    if genre:
        cmd += ["--genre", genre]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"lint.py が失敗した: {path}\n{p.stderr}")
    return json.loads(p.stdout)


def score(findings, nchars):
    sev = collections.Counter(f["severity"] for f in findings)
    penalty = sum(WEIGHT.get(k, 0) * v for k, v in sev.items()) \
        * (1000 / max(nchars, 1000))
    return max(100 - penalty, 20), sev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--genre", default=None)
    ap.add_argument("--json-dir", default=None)
    ap.add_argument("--reading-load", action="store_true")
    ap.add_argument("--experimental", action="store_true")
    a = ap.parse_args()
    if a.json_dir:
        os.makedirs(a.json_dir, exist_ok=True)
    rows = []
    cats_total, rl_total, ex_total = (collections.Counter() for _ in range(3))
    for path in a.files:
        with open(path, encoding="utf-8") as f:
            nchars = len(f.read())
        extra = ["--reading-load"] if a.reading_load else []
        res = run_lint(path, a.genre, extra)
        sc, sev = score(res["findings"], nchars)
        cats = collections.Counter(x["category"] for x in res["findings"])
        cats_total.update(cats)
        rl = collections.Counter(
            x["category"] for x in res.get("reading_load", {}).get("findings", []))
        rl_total.update(rl)
        ex = collections.Counter()
        if a.experimental:
            r2 = run_lint(path, a.genre, ["--experimental"])
            base = [json.dumps(x, sort_keys=True) for x in res["findings"]]
            ex = collections.Counter(
                x["category"] for x in r2["findings"]
                if json.dumps(x, sort_keys=True) not in base)
            ex_total.update(ex)
        if a.json_dir:
            name = os.path.splitext(os.path.basename(path))[0] + ".json"
            with open(os.path.join(a.json_dir, name), "w",
                      encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=1)
        rows.append((os.path.basename(path), nchars, sc, sev, cats, rl, ex,
                     res["stats"].get("total_sentences")))

    head = "| 文書 | 字数 | 文数 | 自然度 | critical | warn | info |"
    sep = "|---|---|---|---|---|---|---|"
    if a.reading_load:
        head += " 読解負荷 |"
        sep += "---|"
    if a.experimental:
        head += " 実験的 |"
        sep += "---|"
    print(head + " 主な検出 |")
    print(sep + "---|")
    for name, n, sc, sev, cats, rl, ex, ns in rows:
        top = "、".join(f"{k}×{v}" for k, v in cats.most_common(4))
        line = (f"| {name} | {n:,} | {ns} | {sc:.1f} | {sev.get('critical', 0)} "
                f"| {sev.get('warn', 0)} | {sev.get('info', 0)} |")
        if a.reading_load:
            line += f" {sum(rl.values())} |"
        if a.experimental:
            line += f" {sum(ex.values())} |"
        print(line + f" {top} |")
    print()
    print("カテゴリ別合計: " + "、".join(
        f"{k}×{v}" for k, v in cats_total.most_common()))
    if a.reading_load:
        print("読解負荷の内訳: " + "、".join(
            f"{k}×{v}" for k, v in rl_total.most_common()))
    if a.experimental:
        print("実験的検出器の内訳: " + "、".join(
            f"{k}×{v}" for k, v in ex_total.most_common()))


if __name__ == "__main__":
    main()

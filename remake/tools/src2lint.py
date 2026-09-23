#!/usr/bin/env python3
"""原稿（src/*.txt の独自記法）を、行番号を保ったまま lint.py 用の Markdown にする。

    python3 src2lint.py <src/chNN.txt> [<出力.md>]

lint.py の指摘の行番号が、そのまま原稿の行番号になる（1行を1行に写す）。
  - 地の文と @cq / @cprev、よくある誤解の Q: / A:、確認問題の解説 … 残す
  - @title … 見出しにする。ほかの @ 行・:::囲みの行・%% コメント … 空行にする
  - :::pm〜:::endpm（午後問題の原文）、:::quiz〜===（問題文と選択肢）… 空行にする
  - 確認問題の答えの行（A1 ウ）… 空行にする
  - インラインの記法（{{語|登録名}}・[[語]]・<<参照>>・^[注]・__ ~~ == [#a]）… 表示される文字だけ残す
  - ~~~ のコード・| の表・箇条書き … そのまま（lint.py がマスクする）
"""
import re
import sys


def plain_inline(s):
    s = re.sub(r"\^\[[^\]]+\]", "", s)
    s = re.sub(r"\{\{([^}|]+)\|[^}]+\}\}", r"\1", s)
    s = re.sub(r"\{\{([^}]+)\}\}", r"\1", s)
    s = re.sub(r"\[\[([^\]|]+)\|[^\]]+\]\]", r"\1", s)
    s = re.sub(r"\[\[([^\]]+)\]\]", r"\1", s)
    s = re.sub(r"<<([^>|]+)\|[^>]+>>", r"\1", s)
    s = re.sub(r"<<(?:fig|tbl):[^>]+>>", "図表", s)
    s = re.sub(r"<<([^>]+)>>", r"\1", s)
    s = re.sub(r"==(.+?)==", r"\1", s)
    s = re.sub(r"__(.+?)__", r"\1", s)
    s = re.sub(r"(?<!~)~~(?!~)(.+?)(?<!~)~~(?!~)", r"\1", s)
    s = re.sub(r"\[#([^\]]+)\]", r"\1", s)
    return s


def convert(lines):
    out = []
    mode = None          # None / "pm" / "quiz_q" / "quiz_a" / "code"
    for ln in lines:
        s = ln.strip()
        if mode == "code":
            out.append(ln)
            if s == "~~~":
                mode = None
            continue
        if mode == "pm":
            out.append("")
            if s == ":::endpm":
                mode = None
            continue
        if mode == "quiz_q":
            out.append("")
            if s == "===":
                mode = "quiz_a"
            continue
        if mode == "quiz_a":
            if s == ":::":
                out.append("")
                mode = None
            elif re.match(r"^A\d+(\s|$)", s):
                out.append("")
            elif s.startswith("~~~"):
                out.append(ln)
                mode = "code_in_quiz"
            else:
                out.append(plain_inline(ln))
            continue
        if mode == "code_in_quiz":
            out.append(ln)
            if s == "~~~":
                mode = "quiz_a"
            continue
        if s.startswith("~~~"):
            out.append(ln)
            mode = "code"
            continue
        if s.startswith(":::pm"):
            out.append("")
            mode = "pm"
            continue
        if s.startswith(":::quiz"):
            out.append("")
            mode = "quiz_q"
            continue
        if s.startswith(":::") or s.startswith("%%"):
            out.append("")
            continue
        if s.startswith("@title "):
            out.append("# " + s[7:])
            continue
        if s.startswith("@cq ") or s.startswith("@cprev "):
            out.append(plain_inline(s.split(None, 1)[1]))
            continue
        if s.startswith("@"):
            out.append("")
            continue
        if re.match(r"[アイウエ](　|$)", s):
            out.append("")
            continue
        if s.startswith("Q: ") or s.startswith("A: "):
            out.append(plain_inline(s[3:]))
            continue
        if s.startswith("## ") or s.startswith("### "):
            out.append(re.sub(r"\s*\{[A-Z実発 ]+\}\s*$", "", plain_inline(ln)))
            continue
        out.append(plain_inline(ln))
    return out


def main():
    src = sys.argv[1]
    with open(src, encoding="utf-8") as f:
        lines = f.read().split("\n")
    text = "\n".join(convert(lines))
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()

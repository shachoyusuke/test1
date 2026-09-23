#!/usr/bin/env bash
# リメイクの1周ごとに回す一括検証。
#
#   remake/tools/verify.sh            # 全部
#   remake/tools/verify.sh --quick    # ビルドと見張り番と自然度だけ（EPUBCheck を省く）
#
# 前提: remake/book（作業コピー）と remake/book-orig（元の制作一式）がある。
# 出力: remake/work/verify/ に EPUB・Markdown・lint の JSON を置く。
set -u -o pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
R="$(dirname "$HERE")"
BOOK="$R/book"
ORIG="$R/book-orig"
OUT="$R/work/verify"
QUICK=0
[ "${1:-}" = "--quick" ] && QUICK=1
fail=0
step() { printf '\n== %s ==\n' "$1"; }

mkdir -p "$OUT"

step "1. ビルド"
if (cd "$BOOK" && python3 tools/build.py > "$OUT/build.log" 2>&1); then
  grep -E "^(警告|EPUB):" "$OUT/build.log" | sed 's/^/   /'
else
  grep -E "^エラー" "$OUT/build.log" | head -30 | sed 's/^/   /'
  echo "   → ビルド失敗（全文は $OUT/build.log）"; exit 1
fi
EPUB="$(ls -t "$BOOK"/dist/*.epub 2>/dev/null | head -1)"
[ -n "$EPUB" ] || { echo "   dist/ に EPUB がない"; exit 1; }
cp "$EPUB" "$OUT/book.epub"

if [ $QUICK -eq 0 ]; then
  step "2. EPUBCheck"
  JAR="$(ls -d "$R"/.tools/epubcheck-*/epubcheck.jar 2>/dev/null | sort -V | tail -1)"
  if [ -n "$JAR" ]; then
    java -jar "$JAR" "$OUT/book.epub" 2>&1 | grep -v JAVA_TOOL_OPTIONS \
      | grep -E "^(Messages|ERROR|FATAL|WARNING)" | head -20 | sed 's/^/   /'
    java -jar "$JAR" "$OUT/book.epub" 2>&1 | grep -q "0 fatals / 0 errors" || fail=1
  else
    echo "   EPUBCheck がない（remake/.tools/ に置く。setup を参照）"; fail=1
  fi
fi

step "3. 内部リンク・正答・出典・演習SQL"
python3 - "$OUT/book.epub" "$BOOK" "$ORIG" <<'PY2' || fail=1
import glob, html, os, re, subprocess, sys, zipfile
epub, book, orig = sys.argv[1:4]
z = zipfile.ZipFile(epub)
names = [n for n in z.namelist() if n.endswith(".xhtml")]
ids, hrefs = set(), []
for n in names:
    s = z.read(n).decode()
    b = n.split("/")[-1]
    ids |= {b + "#" + m for m in re.findall(r'id="([^"]+)"', s)}
    hrefs += [(b, h) for h in re.findall(r'href="([^"]+)"', s)
              if not h.startswith(("http", "../"))]
bad = [(b, h) for b, h in hrefs
       if "#" in h and ((h.split("#")[0] or b) + "#" + h.split("#")[1]) not in ids]
print(f"   内部リンク {len(hrefs)} 本 ／ 未解決 {len(bad)}")
for b, h in bad[:10]:
    print("     未解決:", b, h)
# 午前の過去問題の正答を、照合済みの正答表と突き合わせる
TERM = {"h": "春", "a": "秋", "o": "-10月", "t": "特別"}
ans = {}
for line in open(os.path.join(book, "kakomon/am_answers.md")):
    c = [x.strip() for x in line.strip().strip("|").split("|")]
    if len(c) >= 3 and c[1].isdigit() and c[2] in "アイウエ":
        ans[(c[0], c[1])] = c[2]
ok = ng = 0
for f in sorted(glob.glob(os.path.join(book, "src/quiz/*.txt"))):
    s = open(f).read()
    a = dict(re.findall(r"^A(\d+)\s+([アイウエ])\s*$", s, re.M))
    for no, code in re.findall(r"^Q(\d+)\s+出典=([A-Za-z0-9-]+)\*?\s*$", s, re.M):
        era, y, t, q = re.match(r"([HR])(\d+)([haot])-(\d+)$", code).groups()
        if ans.get((f"{era}{y}{TERM[t]}", q)) == a.get(no):
            ok += 1
        else:
            ng += 1
            print("     正答の不一致:", os.path.basename(f), code)
print(f"   午前の正答 一致 {ok} ／ 不一致 {ng}")
allt = html.unescape("".join(z.read(n).decode() for n in names))
outs = set(re.findall(r"出典：[^<」]+", allt))
r8 = [o for o in outs if "令和8年度" in o]
print(f"   出典表示 {len(outs)} 種類 ／ 令和8年度 {len(r8)}")
# 演習SQLのエラー箇所の数を、元の制作一式と比べる（本文で「エラーになる」と書いた箇所だけのはず）
def err_counts(root):
    # setup_db.py --run は practice/ に hakobera.db を作るので、一時フォルダに複製して動かす
    import shutil, tempfile
    tmp = tempfile.mkdtemp(prefix="verify_practice_")
    work = os.path.join(tmp, "practice")
    shutil.copytree(os.path.join(root, "practice"), work,
                    ignore=shutil.ignore_patterns("*.db", "__pycache__"))
    res = {}
    for f in sorted(glob.glob(os.path.join(work, "answers/*.sql"))):
        name = os.path.basename(f)[:-4]
        p = subprocess.run(["python3", "setup_db.py", "--run", "answers/" + name + ".sql"],
                           cwd=work, capture_output=True, text=True)
        res[name] = sum(1 for l in (p.stdout + p.stderr).splitlines() if l.startswith("エラー:"))
    shutil.rmtree(tmp, ignore_errors=True)
    return res
eo, ew = err_counts(orig), err_counts(book)
diff = [f"{k}={ew.get(k)}（元は{eo.get(k)}）" for k in sorted(set(eo) | set(ew)) if eo.get(k) != ew.get(k)]
print("   演習SQLのエラー箇所: " + ("元と同じ" if not diff else "変化あり " + " ".join(diff)))
sys.exit(1 if bad or ng or r8 else 0)
PY2

step "4. 見張り番（変えてはいけない箇所）"
python3 "$HERE/guard.py" "$ORIG/src" "$BOOK/src" --facts "$ORIG/plan/guide/facts.txt" \
  | sed 's/^/   /' || fail=1

step "5. 自然度（natural-japanese lint, genre=tech）"
python3 "$HERE/xhtml2md.py" "$OUT/book.epub" "$OUT/md" 2>/dev/null
# 目次・索引・用語集・出典一覧・奥付は検査しない
FILES="$(ls "$OUT"/md/*.md | grep -vE '/(toc|nav|index|glossary|sources|colophon)\.md$' | sort -V | tr '\n' ' ')"
python3 "$HERE/nj_score.py" --genre tech --reading-load --json-dir "$OUT/lint" $FILES \
  | tee "$OUT/score.md" | sed 's/^/   /'

step "結果"
if [ $fail -eq 0 ]; then echo "   すべて通過"; else echo "   要対応あり（上を見る）"; fi
exit $fail

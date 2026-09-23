#!/usr/bin/env bash
# アップロードされた zip から、リメイクの作業場を組み立て直す。
# クラウドのコンテナは使い捨てなので、新しいセッションではまずこれを流す。
#
#   remake/tools/restore.sh <制作一式.zip> [<見本・引き継ぎ一式.zip>]
#
#   制作一式.zip   … tools/build.py と src/ を含む本の制作一式（book/ 以下）
#                     → remake/book-orig/（元のまま保つ）と remake/book/（作業コピー）に展開する
#                       remake/book/ がすでにあるときは上書きしない（作業中の原稿を守る）
#   見本・引き継ぎ一式.zip（任意）→ remake/ref/ に展開する
# 最後に natural-japanese の参考資料一式を取り寄せ、検証（--quick）を回す。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
R="$(dirname "$HERE")"
[ $# -ge 1 ] || { sed -n '2,12p' "$0"; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

unzip -q "$1" -d "$tmp/book"
build_py="$(find "$tmp/book" -path '*/tools/build.py' | head -1)"
[ -n "$build_py" ] || { echo "制作一式に tools/build.py が見つからない: $1"; exit 1; }
src_root="$(dirname "$(dirname "$build_py")")"
rm -rf "$R/book-orig"
cp -a "$src_root" "$R/book-orig"
echo "元の制作一式: $R/book-orig"
if [ -d "$R/book" ]; then
  echo "作業コピーはすでにあるので上書きしない: $R/book"
else
  cp -a "$R/book-orig" "$R/book"
  echo "作業コピー: $R/book"
fi

if [ $# -ge 2 ]; then
  mkdir -p "$R/ref"
  unzip -q -o "$2" -d "$R/ref"
  echo "参考資料: $R/ref/"
fi

if [ ! -d "$R/ref/natural-japanese" ]; then
  mkdir -p "$R/ref"
  git clone -q --depth 1 https://github.com/coji/natural-japanese.git "$R/ref/natural-japanese" \
    && rm -rf "$R/ref/natural-japanese/.git" \
    && echo "natural-japanese の参考資料一式: $R/ref/natural-japanese" \
    || echo "natural-japanese の取得に失敗（スキル本体は .claude/skills にあるので作業は続けられる）"
fi

"$HERE/verify.sh" --quick

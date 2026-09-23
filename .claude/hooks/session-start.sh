#!/bin/bash
# クラウドセッションの開始時に、EPUB リメイク作業の道具をそろえる。
# 入っているものは入れ直さない（何度実行しても同じ結果になる）。
#
#   - EPUBCheck（remake/.tools/ に jar を置く。Java は環境に入っている）
#   - Python: Pillow（図・表紙の検査）、playwright（図の再生成。Chromium は環境に入っている）
#   - フォント: Noto Sans CJK JP（図の日本語）、poppler-utils（PDF の文字抽出）
#   - natural-japanese の lint.py が使う sudachipy と辞書（uv のキャッシュに事前取得）
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
TOOLS="$ROOT/remake/.tools"
EPUBCHECK_VERSIONS="5.1.0 5.3.0"   # 5.1.0 は元の納品時と同じ版、5.3.0 は新しい版

log() { echo "[session-start] $*" >&2; }

# EPUBCheck
mkdir -p "$TOOLS"
for v in $EPUBCHECK_VERSIONS; do
  if [ ! -f "$TOOLS/epubcheck-$v/epubcheck.jar" ]; then
    log "EPUBCheck $v を取得"
    tmp="$(mktemp -d)"
    curl -sSfL -o "$tmp/epubcheck.zip" \
      "https://github.com/w3c/epubcheck/releases/download/v$v/epubcheck-$v.zip"
    unzip -q -o "$tmp/epubcheck.zip" -d "$TOOLS"
    rm -rf "$tmp"
  fi
done

# Python パッケージ
if ! python3 -c "import PIL, playwright" 2>/dev/null; then
  log "Pillow と playwright を導入"
  python3 -m pip install --quiet --break-system-packages pillow playwright
fi

# フォントと PDF 抽出
need_apt=""
fc-list :lang=ja 2>/dev/null | grep -q "Noto Sans CJK JP" || need_apt="$need_apt fonts-noto-cjk"
command -v pdftotext >/dev/null 2>&1 || need_apt="$need_apt poppler-utils"
if [ -n "$need_apt" ]; then
  log "apt で導入:$need_apt"
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq $need_apt >/dev/null
fi

# natural-japanese の lint.py の依存（初回は sudachipy と辞書を取得する）
LINT="$ROOT/.claude/skills/natural-japanese/scripts/lint.py"
if [ -f "$LINT" ] && command -v uv >/dev/null 2>&1; then
  uv run --quiet "$LINT" \
    "$ROOT/.claude/skills/natural-japanese/scripts/fixtures/natural.md" >/dev/null
fi

log "準備完了"

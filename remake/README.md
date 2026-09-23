# EPUB リメイクの作業場

AI が書いた Kindle 向け EPUB（学習書）を、人間の読者に向けて書き直すための作業場。
リライトの方法論は [natural-japanese](https://github.com/coji/natural-japanese)（MIT）を使い、`.claude/skills/natural-japanese/` に同梱してある。

## このリポジトリに入れないもの

このリポジトリは公開されている。原稿・参考資料・作業メモは `.gitignore` で外してあり、コンテナの中にだけ置く。

| 置き場 | 中身 | コミット |
|---|---|---|
| `remake/book-orig/` | 元の制作一式（原稿・ビルド・図・過去問題の資料）。**編集しない** | しない |
| `remake/book/` | 作業コピー。書き直しはここの `src/` に入れる | しない |
| `remake/ref/` | 参考資料（見本の EPUB 一式、natural-japanese の研究資料） | しない |
| `remake/notes/` | 診断ノート・ベースラインの計測結果 | しない |
| `remake/work/` | 検証の出力（EPUB・Markdown・lint の JSON） | しない |
| `remake/.tools/` | EPUBCheck（セッション開始フックが取り寄せる） | しない |
| `remake/tools/` | 下の道具 | する |

新しいセッションでは、zip をアップロードしてから `remake/tools/restore.sh` を流す。

```bash
remake/tools/restore.sh <制作一式.zip> [<見本・引き継ぎ一式.zip>]
```

## 道具

| 道具 | 役目 |
|---|---|
| `tools/verify.sh` | 1周ごとの一括検証。ビルド → EPUBCheck → 内部リンク・午前の正答・出典・演習SQL → 見張り番 → 自然度。`--quick` で EPUBCheck を省く |
| `tools/guard.py` | 変えてはいけない箇所の見張り番。過去問題の原文・確認問題の問題部分と正答・出典コードが変わったらエラー。SQL・図表の ID・節番号・注・定義語の増減・地の文の新しい数値は「確認」として出す |
| `tools/nj_score.py` | natural-japanese の lint.py を章ごとにかけ、自然度（diagnose.md の機械ベースの式）を表にする |
| `tools/xhtml2md.py` | EPUB の本文を章ごとの Markdown にする。通読用と lint 用。過去問題の引用は引用ブロックにして lint から外す |
| `tools/src2lint.py` | 原稿（独自記法）を行番号を保ったまま lint 用にする。指摘の行番号が原稿の行番号になる |
| `tools/epub_diff.py` | 二つの EPUB を比べる。受け取った EPUB が手元のソースのビルドと同じかを確かめる |
| `tools/restore.sh` | zip から作業場を組み立て直す |

## 1周の回し方（章単位）

1. 診断ノート（`notes/chapters/<章>.md`）の keep / change を見て、直す箇所を選ぶ。既定は keep
2. `book/src/<章>.txt` を書き直す。判断は台帳に1行ずつ残す（直した／残す＋理由）
3. `python3 book/tools/build.py --check <章>` でその章だけ組む
4. `remake/tools/verify.sh --quick` で全体を検証する。見張り番のエラーは原則として元に戻す
5. 章を読み直し、6軸ルーブリック（`.claude/skills/natural-japanese/references/eval-rubric.md`）で採点する

## 環境

セッション開始フック（`.claude/hooks/session-start.sh`）が、EPUBCheck（5.1.0 と 5.3.0）、Pillow、playwright、Noto Sans CJK JP、poppler-utils、lint.py の依存（sudachipy）をそろえる。入っているものは入れ直さない。

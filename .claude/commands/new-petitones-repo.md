---
description: "PetitOnes組織に新しい公開リポジトリを作る。切り出し・サニタイズ・ブランチ保護の決まった流儀で。"
argument-hint: "<リポ名> [切り出し元パス]"
---

PetitOnes組織（github.com/PetitOnes）に新しいリポジトリを作る。2026-07-06に確立した流儀に必ず従うこと。

## 流儀（全ステップ必須）

### 1. 準備
- リポ名は `m5-petit-*` の命名に揃える（例外はありさんに確認）
- **名前に "claude" を含めない**（Anthropic系名称を避けるプロジェクト方針）
- 切り出し元がある場合、**元のディレクトリは一切変更しない**（本番稼働中の可能性）。scratchpadにコピーして作業

### 2. サニタイズ（公開前にgrepゼロ件必須）
```bash
grep -rn -E "cube-petit|password|token|api_key|secret|@gmail" --exclude-dir=.git .
grep -rn -E "puchiteya|puchiko|puchiru|arisan|kazahaya|ありさん|かぜお" --exclude-dir=.git .
```
- 絶対パス（/home/cube-petit等）→ 環境変数化、デフォルトは `~/petit_data` 系
- キャラ・人名のハードコード → 汎用プレースホルダ（alice等）に
- **.env / *.db / 記憶・日記データ / __pycache__ / .venv は絶対に含めない**（.env.exampleのみ可）
- uv.lockのバージョン番号がIP正規表現に誤ヒットするのは無視してよい

### 3. ライセンス・帰属
- LICENSE: Apache-2.0（組織標準）
- **上流由来の確認**: 切り出し元が `lifemate-ai/embodied-claude`（MIT）に存在するコンポーネントなら、**NOTICEファイル**（上流MIT全文＋Copyright (c) 2026 lifemate-ai＋派生の説明）とREADMEクレジットが必須

### 4. リポ構成
- **git識別子を必ずローカル設定してからコミット**（このマシンのグローバル設定は仕事用メールのため、公開リポに漏れる）:
  ```bash
  git config user.name "RRYZ09"
  git config user.email "225634165+RRYZ09@users.noreply.github.com"
  ```
- **git履歴は持ち込まない**。新規 `git init` の1コミット目から
- README.md（日本語）+ README_en.md（英語）、相互リンク（`## [English Page](./README_en.md)` / `## [日本語ページ](README.md)`）。既存の m5-petit-mcp のスタイルに合わせる
- descriptionは日英併記: `English description / 日本語説明`
- コミット末尾: `Co-Authored-By: Claude <使用モデル名> <noreply@anthropic.com>`

### 5. 作成とブランチ保護（main と develop の両方）
```bash
gh repo create PetitOnes/<name> --public --description "<日英>"
git push -u origin main
git checkout -b develop && git push -u origin develop
```

### 5.5 Topics（About欄のタグ）— 必須
作成直後に必ず設定する（既存リポの例: `m5-petit-mcp` は `claude, embodied-ai, m5stack, mcp, model-context-protocol, python`）:
```bash
gh repo edit PetitOnes/<name> --add-topic embodied-ai --add-topic m5stack --add-topic python
# コンポーネントの性質に応じて追加。MCPサーバーなら:
gh repo edit PetitOnes/<name> --add-topic mcp --add-topic model-context-protocol
# 該当すれば: claude / fastapi / docker / whisper / tts 等
```
確認: `gh api repos/PetitOnes/<name> --jq '.topics'`（空配列のまま放置しない）
保護は main / develop の**両方**に適用（JSONファイル経由。-fフラグではnullを渡せない）:
```bash
cat > /tmp/protection.json << 'EOF'
{
  "required_status_checks": null,
  "enforce_admins": true,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
EOF
for BR in main develop; do
  gh api -X PUT "repos/PetitOnes/<name>/branches/$BR/protection" \
    -H "Accept: application/vnd.github+json" --input /tmp/protection.json
done
```

### 6. 検証と記録
- `uv sync` / `uv run ruff check .` / テストがあれば `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest`
- サニタイズgrepを最終再実行してゼロ件確認
- `docs/component-extraction-plan.md` の一覧に追記
- 完了報告に: リポURL / サニタイズで直したもの / テスト結果 / 保護設定結果

入力: $ARGUMENTS

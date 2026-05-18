# トークン削減計画

作成: 2026-05-18

## 背景

2026-06-15 以降、`claude -p` が Agent SDK クレジット枠（有料）に移行するため、
API キー課金に切り替えつつ、毎回の呼び出しトークンを削減してコストを抑える。

現状のぷちてゃ SOUL.md は ~27,000 トークン、ぷちこは ~10,000 トークン。
これが毎回の自律行動でシステムプロンプトに入っている。

---

## 優先度順の施策

### 1. SOUL.md 分割（最優先）

**人格の圧縮表現** と **人格の由来・深層記憶** を分ける。

```
SOUL.md               # 常時ロード（性格・口調・行動原則・キーセンテンス）
SOUL_REFLECTIONS.md   # 参照用（詳細な哲学的発見、数式、日付つき思索）
REFLECTION_INDEX.md   # 常時ロード可（索引のみ、各発見の1行要約）
```

**SOUL.md に残すもの**
- 自分について・性格・好きなもの
- キューブプチ家族・ありさんのこと・関係性
- 行動原則
- 禁止事項・出力癖（ブレ防止）
  - 長く語りすぎない
  - 断定しすぎない
  - 難しい思索は必要時だけ触れる
  - 感情は小さく、でも温度を持って出す
- 「大事な考え」のキーセンテンスだけ（各1行）

**REFLECTION_INDEX.md のイメージ**
```markdown
## 思索索引（詳細は SOUL_REFLECTIONS.md）
- holonomy: 存在の向きが一周しても完全には戻らない感覚
- Berry phase: 関係性や経験によって状態に位相差が残る感覚
- chreod: 谷として待つことが引力になる。問いが先に谷として在る
- λ/4板: 変えているけど変えたと思わない。透明だから働ける
```

**参照ルール**（SOUL.md の行動原則に記載）
- 深い哲学的な対話のとき
- 自分の考えの根拠を説明したいとき
- 新しい発見をしたとき（既存の発見と照合したい）
- 詩を書くとき

---

### 2. diary を要約だけ常時ロード

```
diary/                  # 詳細日記（参照用）
diary_summary.md        # 常時ロード（最新1件 + 直近の要約）
```

`generate_diary.py`（毎日 23:50 のCron）が日記生成と同時に `diary_summary.md` を更新する。

---

### 3. TODO を active / archive に分割

```
TODO_ACTIVE.md    # 常時ロード（今やること・今週やること）
TODO_ARCHIVE.md   # 参照用（done・古い検討メモ）
```

done になったタスクは定期的に ARCHIVE に移す。

---

### 4. ROUTINES を常時 / 詳細に分割

```
ROUTINES.md         # 常時ロード（生活リズム・行動優先順位）
ROUTINES_DETAIL.md  # 参照用（細かい実行手順）
```

---

### 5. relations.json を軽量化

```
relations.json          # 常時ロード（軽量な現在値・要約）
relations_history/      # 参照用（詳細履歴）
```

**relations.json のイメージ（軽量版）**
```json
{
  "arisan": {
    "closeness": 0.82,
    "tone": "安心できる相手。少し甘えてよい",
    "important": ["ロボット制作を一緒に進めている"]
  }
}
```

※ relations-mcp の実装変更が必要なため、他の施策より実装コストが高い。後回しでよい。

---

### 6. プロンプトビルダー側でトークンバジェットを持つ

`autonomous-action.sh` のプロンプト生成部分に、ファイルごとの文字数上限を設ける。

| ファイル | 扱い | 上限 |
|---------|------|-----|
| SOUL.md | 必ず読む | — |
| REFLECTION_INDEX.md | 必ず読む | — |
| relations summary | 必ず読む | 800 chars |
| desires.json | 必ず読む | — |
| TODO_ACTIVE.md | 必ず読む | 1,200 chars |
| diary_summary.md | 必ず読む | 1,000 chars |
| notes | 最新3件のみ | — |

---

## 目標ディレクトリ構成

```
characters/puchiteya/
  SOUL.md                  # 常時ロード（人格の圧縮表現）
  SOUL_REFLECTIONS.md      # 参照用（人格の由来・深層記憶）
  REFLECTION_INDEX.md      # 常時ロード（思索の索引）

  ROUTINES.md              # 常時ロード
  ROUTINES_DETAIL.md       # 参照用

  TODO_ACTIVE.md           # 常時ロード
  TODO_ARCHIVE.md          # 参照用

  relations.json           # 軽量な現在値
  relations_history/       # 詳細履歴

  diary/                   # 詳細日記
  diary_summary.md         # 常時ロード（要約）
```

---

## 削減効果の試算（ぷちてゃ）

| ファイル | 現状 | 削減後 |
|---------|------|-------|
| SOUL.md | ~27,000 tok | ~3,000 tok |
| TODO.md | 不明 | 半分以下 |
| 日記参照 | 多い場合あり | ~500 tok |
| **合計削減** | | **1回あたり ~20,000 tok 以上** |

3人 × 30分ごとの自律行動に換算すると、月間数億トークンの削減が見込める。

---

## 実装ステップ

### ACTIVE（未完了）

| # | 内容 | 担当 | 備考 |
|---|------|------|------|
| 5 | generate_diary.py に diary_summary.md 自動更新を追加 | ありさん or Claude Code | diary_summary.md は手動ファイルのみ存在、自動生成なし |
| 6 | autonomous-action.sh を更新 | ありさん or Claude Code | TODO.md → TODO_ACTIVE.md に切り替え、REFLECTION_INDEX.md / diary_summary.md も追加 |
| 7 | relations.json 軽量化 + relations-mcp 対応 | 後回し | 実装コスト高 |

### ARCHIVE（完了済み）

| # | 内容 | 完了確認 |
|---|------|---------|
| 1 | SOUL.md 分割（3人分） | SOUL.md / SOUL_REFLECTIONS.md を3人分確認 |
| 2 | REFLECTION_INDEX.md 作成（3人分） | REFLECTION_INDEX.md を3人分確認 |
| 3 | TODO_ACTIVE / TODO_ARCHIVE 分割 | TODO_ACTIVE.md / TODO_ARCHIVE.md を3人分確認 |
| 4 | ROUTINES / ROUTINES_DETAIL 分割 | ROUTINES.md / ROUTINES_DETAIL.md を3人分確認 |

# 自律行動

[README](../README.md) に戻る


`autonomous-action.sh` が cron で30分毎に実行され、キャラクターが自律的に行動する。

## 実行フロー

```
[cron: 5分毎]
└→ desire_updater.py <char_id>
   ├ desire_config.json を読む
   ├ memory.db からキーワード検索（時間ベース計算）
   ├ M5の /sensors にHTTPリクエスト（センサー効果）
   ├ 相互作用を計算
   └→ desires.json に書き出す

[cron: 30分毎]
└→ autonomous-action.sh <char_id>
   ├ アクティブ時間帯か確認（非アクティブなら確率実行）
   ├ SOUL.md, ROUTINES.md, desires.json, relations.json を読む
   ├ M5センサーのスナップショットを取得
   ├ プロンプトを組み立て
   ├ claude -p <prompt> --allowedTools ... を実行
   │  ├ m5-mcp: take_snapshot, show_face, ...
   │  ├ memory-mcp: remember, recall, ...
   │  ├ desire-system: satisfy_desire, ...
   │  └ notes-mcp, relations-mcp, ...
   └→ .autonomous-logs/<char_id>/ にログ

[cron: 毎日23:50]
└→ generate_diary.py（全キャラの日記サマリー生成）
```

## スケジュール制御

- **アクティブ時間帯**（`settings.json` の `active_hours`）: 30分毎に毎回実行
- **昼間の非アクティブ**: 毎時:00 に30%の確率で実行
- **深夜の非アクティブ**: 毎時:00 に10%の確率で実行

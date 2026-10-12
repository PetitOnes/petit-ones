# お散歩（外出モード）

[README](../README.md) に戻る


M5Stack を外に連れ出して散歩できる。Android スマホのテザリング + Tailscale VPN で自宅PCからM5Stackに接続する。

## 必要なもの

- Android スマホ（テザリング + Tailscale）
- モバイルバッテリー（M5Stack 給電用）
- 自宅PC に Tailscale がインストール済み

## 構成

```
[M5Stack] ──WiFi──▶ [スマホ(テザリング)]
                           │
                     Tailscale VPN
                     (subnet router)
                           │
                    [自宅PC (Claude Code)]
                           │
                    [ダッシュボード]
                           │
                    [スマホのブラウザ] ◀── 操作
```

## セットアップ手順

### 1. Tailscale をインストール

- Android: Google Play から [Tailscale](https://play.google.com/store/apps/details?id=com.tailscale.ipn) をインストール
- 自宅PC: `curl -fsSL https://tailscale.com/install.sh | sh`
- 両方とも同じアカウントでログイン

### 2. Android でサブネットルーターを設定

スマホのテザリングで作られるローカルネットワーク（M5Stack が接続する）を、Tailscale 経由で自宅PCからアクセスできるようにする。

```
Android Tailscale アプリ → ⚙ 設定 → Subnet router
→ テザリングのサブネットを追加（例: 192.168.49.0/24）
```

テザリングのサブネットは機種によって異なる。M5Stack がテザリングに接続した後、M5Stack の IP を確認して `/24` を付ける。

### 3. Tailscale Admin Console でサブネットを承認

https://login.tailscale.com/admin/machines でスマホのマシンを開き、サブネットルートを承認（Approve）する。

### 4. 自宅PCからサブネットを受け入れる

```bash
sudo tailscale up --accept-routes
```

### 5. 接続確認

M5Stack をスマホのテザリングに接続した状態で、自宅PCから:

```bash
ping <M5StackのIP>  # 例: ping 192.168.49.1
```

通ればOK。ダッシュボードからそのまま操作できる。

## 散歩時の操作

スマホのブラウザで `http://<自宅PCのTailscale IP>:8765` にアクセスしてダッシュボードから操作。

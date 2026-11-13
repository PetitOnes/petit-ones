#!/bin/bash
# interoception.sh - AIの内受容感覚（interoception）
# UserPromptSubmitフックで毎ターン実行される
# heartbeat-daemon.sh が書き出した state file を読んでコンテキストに注入する
# 自前で計測せず、読み取り→整形→出力するだけの軽量版

STATE_FILE="/tmp/interoception_state.json"
DATA_DIR="${PETIT_DATA_DIR:-$HOME/petit_claude}"

# 家がない環境では、このリポを開いた人にだけ静かに何もしない。
if [ ! -d "$DATA_DIR" ]; then
    exit 0
fi

# state file がなければ(心拍デーモンが動いていない家)、いまの日時だけを短く足す。
# 時刻はいつも分かっていてほしいので残す。体の状態が無いことの断り書き(heartbeat daemon not running)は
# 毎ターン足しても意味がないので、やめた(2026-11-13)。
# 心拍デーモン(heartbeat-daemon.sh)は launchd 前提で、Linux の家では動かない
if [ ! -f "$STATE_FILE" ]; then
    DOW=(日 月 火 水 木 金 土)
    echo "いま: $(date '+%Y-%m-%d')(${DOW[$(date '+%w')]}) $(date '+%H:%M')"
    exit 0
fi

# state file から読み取って1行に整形
python3 -c "
import json, sys
try:
    with open('${STATE_FILE}') as f:
        data = json.load(f)
    now = data.get('now', {})
    trend = data.get('trend', {})
    window = data.get('window', [])

    # トレンド矢印
    arrows = {'rising': '↑', 'falling': '↓', 'stable': '→'}
    ar_arrow = arrows.get(trend.get('arousal', 'stable'), '→')
    mem_arrow = arrows.get(trend.get('mem_free', 'stable'), '→')

    # タイムスタンプから時刻・曜日
    from datetime import datetime
    ts = now.get('ts', '?')
    if 'T' in ts:
        time_part = ts.split('T')[1][:8]
        try:
            dt = datetime.strptime(ts[:10], '%Y-%m-%d')
            dow = dt.strftime('%a')  # Mon, Tue, ...
        except Exception:
            dow = '?'
    else:
        time_part = ts
        dow = '?'

    parts = [
        f\"time={time_part}\",
        f\"day={dow}\",
        f\"phase={now.get('phase', '?')}\",
        f\"arousal={now.get('arousal', '?')}%({ar_arrow})\",
        f\"thermal={now.get('thermal', '?')}\",
        f\"mem_free={now.get('mem_free', '?')}%({mem_arrow})\",
        f\"uptime={now.get('uptime_min', '?')}min\",
        f\"heartbeats={len(window)}\",
    ]
    print('[interoception] ' + ' '.join(parts))
except Exception as e:
    print(f'[interoception] error reading state: {e}', file=sys.stderr)
    print('[interoception] state_file_error')
" 2>/dev/null

exit 0

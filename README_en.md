# Cube Petit Claude

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**[日本語版 README はこちら / Japanese README](./README.md)**

A fork of [embodied-claude](https://github.com/kmizu/embodied-claude). Small characters ("Petits") living in M5Stack devices, each with their own personality, desires, memories, and autonomous behavior.

## Differences from the Original

[kmizu/embodied-claude](https://github.com/kmizu/embodied-claude) is a collection of MCP servers that give Claude a body — eyes (camera), neck (PTZ), ears (microphone), voice (TTS), and brain (long-term memory).

This fork extends the concept into a **multi-character autonomous agent framework**.

### Key Differences

| | Original (kmizu) | This Fork (cube-petit) |
|---|---|---|
| **Hardware** | Wi-Fi PTZ camera (Tapo C210 etc.) | M5Stack CoreS3 |
| **Characters** | Single instance | Multiple characters (independent personality, memory, desires) |
| **Autonomy** | User-driven (reactive) | Cron-based autonomous action every 20 min (desire-driven) |
| **Desires** | Optional | Core feature (sensor_effects, cross_effects) |
| **UI** | CLI only | Web dashboard (chat, desire display, diary, memory viewer) |
| **Social** | None | Inter-character relationships & mailbox |
| **Portability** | Stationary | M5Stack + mobile battery for outdoor walks |

### Added Components

| Component | Description |
|---|---|
| **m5-mcp** | M5Stack control (camera, face display, sensors, audio, sleep). Replaces wifi-cam-mcp/usb-webcam-mcp |
| **desire-system** | Desire system. Computes desire levels through 3 stages: time-based + sensor effects + cross-effects |
| **relations-mcp** | Inter-character relationships (likes, dislikes, closeness, notes) |
| **notes-mcp** | Persistent notes (light value tables, sensor ranges, etc.) |
| **dashboard** | Web UI (chat, group chat, desire display, memory viewer, diary, auth) |
| **create_character.py** | Character creation script (generates config files + cron entries) |
| **autonomous-action.sh** | Autonomous action orchestration (schedule, probability control, session management) |
| **scripts/** | Mailbox writer (`write_mailbox.py`), memory reader (`reader.py`) |

### Inherited from Original

memory-mcp, tts-mcp, system-temperature-mcp, mobility-mcp, ip-webcam-mcp, mcp-pet, morning-call-mcp also exist in the original. memory-mcp has been extended with visual memory, episodes, causal links, Theory of Mind, and memory consolidation (sleep).

## Overview

Combine M5Stack + Claude Code + memory system to create characters with eyes (camera), emotions (face display), senses (sensors), memory (SQLite), and desires (desire-system).

```
[M5Stack] <-HTTP/WS-> [m5-mcp] <-stdio-> [Claude Code]
                                               |
                    [memory-mcp] <-> [SQLite (memory DB)]
                    [desire-system] <-> [desires.json]
                    [relations-mcp] <-> [relations.json]
                    [notes-mcp] <-> [notes/*.md]
```

## Directory Structure

```
embodied-claude/              <- Code (git-managed, public)
|-- m5-mcp/                   # M5Stack control MCP
|-- memory-mcp/               # Long-term memory MCP
|-- desire-system/            # Desire system (MCP + updater)
|-- relations-mcp/            # Relationships MCP
|-- notes-mcp/                # Persistent notes MCP
|-- dashboard/                # Web dashboard
|-- tts-mcp/                  # TTS MCP (ElevenLabs / VOICEVOX)
|-- system-temperature-mcp/   # Body temperature MCP
|-- scripts/                  # Utility scripts
|   |-- write_mailbox.py      #   Mailbox writer
|   |-- reader.py             #   Memory reader
|-- autonomous-action.sh      # Autonomous action script (.gitignore)
|-- autonomous-action.sample.sh # Template for the above
|-- create_character.py       # Character creation script
|
|  # From original (unused or limited use)
|-- wifi-cam-mcp/             # Wi-Fi PTZ camera (for Tapo)
|-- usb-webcam-mcp/           # USB camera
|-- ip-webcam-mcp/            # Android phone camera
|-- mobility-mcp/             # Robot vacuum
|-- mcp-pet/                  # PErsonal Terminal
|-- morning-call-mcp/         # Morning call

~/petit_claude/               <- Data (PETIT_DATA_DIR, private)
|-- characters/
|   |-- puchiko/
|   |   |-- config.json       # M5 host, character name, color
|   |   |-- SOUL.md           # Personality definition
|   |   |-- settings.json     # Active hours, feature toggles
|   |   |-- desires.json      # Current desire levels (updated every 5 min)
|   |   |-- desire_config.json # Desire definitions, sensor_effects, cross_effects
|   |   |-- relations.json    # Feelings toward other characters/user
|   |   |-- autonomous-mcp.json # MCP config for autonomous actions
|   |   |-- chat_history.json # Chat history
|   |   |-- notes/            # Persistent notes
|   |-- puchiteya/
|-- mailbox/                  # Inter-character messages
|-- .autonomous-logs/         # Autonomous action logs
|-- SOUL.md, TODO.md, ROUTINES.md
|-- settings.json, group_chat.json
|-- auth.json                 # Dashboard auth (optional)
|-- backup/                   # Backup scripts + data
```

Code and data are separated. Set the `PETIT_DATA_DIR` environment variable to change the data directory (default: `~/petit_claude`).

## Setup

### 1. Prerequisites

```bash
# uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Claude Code
npm install -g @anthropic-ai/claude-code

# Other
sudo apt install -y jq sqlite3
```

### 2. Clone

```bash
git clone https://github.com/fruitriin/embodied-claude.git
cd embodied-claude
```

### 3. Install Dependencies

```bash
for dir in m5-mcp memory-mcp desire-system dashboard relations-mcp notes-mcp system-temperature-mcp; do
  echo "--- $dir ---"
  (cd "$dir" && uv sync)
done
```

### 4. Add a Character

```bash
uv run python create_character.py <id> <name> <color> <M5 IP>

# Example:
uv run python create_character.py puchiko Puchiko "#cab8d9" 10.42.138.100
```

This automatically creates:
- Config files in `~/petit_claude/characters/{id}/`
- Cron entries for desire updates (every 5 min) and autonomous actions (every 20 min)

After creation, edit `characters/{id}/SOUL.md` to define the character's personality.

### 5. Autonomous Action Script

```bash
cp autonomous-action.sample.sh autonomous-action.sh
vim autonomous-action.sh  # Edit HOME, PATH, PROJECT_DIR
chmod +x autonomous-action.sh
```

### 6. Environment Variables

```bash
cd desire-system
cp .env.example .env
# Set COMPANION_NAME etc. in .env
```

### 7. Start Dashboard

```bash
cd dashboard
uv run python main.py
# -> http://0.0.0.0:8765
```

## MCP Servers

### m5-mcp (Eyes, Emotions, Sensors)

See [m5_petit](https://github.com/AiriYokochi/m5_petit) for M5Stack firmware setup. Set the IP via the `M5_HOST` environment variable (passed through `autonomous-mcp.json`).

| Tool | Description |
|------|-------------|
| `take_snapshot` | Capture image from M5 camera |
| `look` | Move gaze (x/y: -100 to 100) |
| `blink` | Wink |
| `show_face` | Display face image (JPEG from SD card) |
| `play_sound` | Play sound effect |
| `play_icon` | Show icon (love / cry) |
| `get_sensor_data` | Get proximity, ambient light, accelerometer, gyro, battery |
| `wait_for_touch` | Wait for touch event |
| `set_volume` / `get_volume` | Volume control |
| `sleep` / `wake` | Sleep control |

### memory-mcp (Memory)

| Tool | Description |
|------|-------------|
| `remember` | Save memory (with emotion, importance, category) |
| `recall` / `recall_divergent` | Context-based recall (divergent recall with associative expansion) |
| `search_memories` | Semantic search |
| `recall_with_associations` | Recall with linked memories |
| `save_visual_memory` | Save memory with image + camera angle |
| `save_audio_memory` | Save memory with audio + transcript |
| `recall_by_camera_position` | Recall memories by camera direction |
| `create_episode` / `search_episodes` | Episode management |
| `link_memories` / `get_causal_chain` | Causal links |
| `get_working_memory` / `refresh_working_memory` | Working memory |
| `consolidate_memories` | Memory replay & consolidation |
| `sleep` | Memory maintenance (compress, decay, forget) |
| `tom` | Theory of Mind (perspective-taking) |

### desire-system (Desires)

Computes desire levels through a 3-stage pipeline:

1. **Time-based**: Elapsed time since keywords last appeared in memory DB
2. **Sensor effects**: M5 sensor values (ambient, gyro, battery, etc.) add/subtract from desires
3. **Cross-effects**: Inter-desire influence (e.g., fatigue suppresses curiosity)

| Tool | Description |
|------|-------------|
| `get_desires` | Get current desire levels |
| `satisfy_desire` | Mark desire as satisfied (call after taking action) |
| `boost_desire` | Boost a desire (on surprise/discovery) |

Desire definitions, keywords, and sensor effects are customizable in `characters/{id}/desire_config.json`. The `desire_updater.py` cron job recalculates levels every 5 minutes and writes to `desires.json`.

### relations-mcp (Relationships)

| Tool | Description |
|------|-------------|
| `get_relations` | Get relationships with other characters |
| `update_relation` | Update relationship info (likes, dislikes, closeness, notes) |

### notes-mcp (Notes)

| Tool | Description |
|------|-------------|
| `list_notes` | List notes |
| `read_note` | Read a note |
| `write_note` | Create/update a note |

Unlike memory (searched/recalled), notes are persistent reference documents for light value tables, sensor ranges, etc.

## Autonomous Action

`autonomous-action.sh` runs via cron every 20 minutes, enabling characters to act autonomously.

### Execution Flow

```
[Cron: every 5 min]
|-> desire_updater.py <char_id>
    |-- Read desire_config.json
    |-- Query memory.db (keyword search for time-based calculation)
    |-- HTTP GET /sensors from M5Stack (sensor effects)
    |-- Compute cross-effects
    |-> Write desires.json

[Cron: every 20 min]
|-> autonomous-action.sh <char_id>
    |-- Check if within active hours (else probability-based execution)
    |-- Read: SOUL.md, ROUTINES.md, desires.json, relations.json
    |-- Get M5 sensor snapshot
    |-- Build prompt with all context
    |-- Run: claude -p <prompt> --allowedTools ...
    |   |-- m5-mcp: take_snapshot, show_face, ...
    |   |-- memory-mcp: remember, recall, ...
    |   |-- desire-system: satisfy_desire, ...
    |   |-- notes-mcp, relations-mcp, ...
    |-> Log to .autonomous-logs/<char_id>/

[Cron: daily at 23:50]
|-> generate_diary.py (daily summary for all characters)
```

### Schedule Control

- **Active hours** (`settings.json` `active_hours`): Runs every 20 min
- **Daytime inactive**: Runs at :00 with 30% probability
- **Nighttime inactive**: Runs at :00 with 10% probability

## Dashboard

- Desire bars: Real-time display of each character's desire levels
- Chat: Talk directly to a character
- Group chat: Send to all characters simultaneously
- Interaction: Set up character-to-character conversations
- Settings: Active hours, camera/audio/mic toggles
- Memory list: Browse memories by date
- Diary: Daily summary (auto-generated at 23:50)

## Walking (Outdoor Mode)

Take M5Stack devices outside for a walk. Connect from home PC to M5Stack via Android tethering + Tailscale VPN.

### Requirements

- Android phone (tethering + Tailscale)
- Mobile battery (to power M5Stack)
- Tailscale installed on home PC

### Architecture

```
[M5Stack] --WiFi--> [Phone (tethering)]
                           |
                     Tailscale VPN
                     (subnet router)
                           |
                    [Home PC (Claude Code)]
                           |
                    [Dashboard]
                           |
                    [Phone browser] <-- Control
```

### Setup Steps

#### 1. Install Tailscale

- Android: Install [Tailscale](https://play.google.com/store/apps/details?id=com.tailscale.ipn) from Google Play
- Home PC: `curl -fsSL https://tailscale.com/install.sh | sh`
- Log in with the same account on both

#### 2. Configure Subnet Router on Android

Allow access to the tethering local network (where M5Stack connects) from the home PC via Tailscale.

```
Android Tailscale app -> Settings -> Subnet router
-> Add tethering subnet (e.g., 192.168.49.0/24)
```

The tethering subnet varies by device. Check M5Stack's IP after connecting to tethering and append `/24`.

#### 3. Approve Subnet in Tailscale Admin Console

Go to https://login.tailscale.com/admin/machines, open the phone's machine, and approve the subnet route.

#### 4. Accept Routes on Home PC

```bash
sudo tailscale up --accept-routes
```

#### 5. Verify Connection

With M5Stack connected to phone's tethering:

```bash
ping <M5Stack IP>  # e.g., ping 192.168.49.1
```

If it responds, you're set. Control through the dashboard as usual.

### Operating During Walks

Access `http://<home PC Tailscale IP>:8765` from your phone's browser to use the dashboard.

## Always-On Dashboard (systemd)

Auto-start the dashboard after PC reboot.

### 1. Create Environment File

Write environment-specific values to `~/petit_claude/.env.dashboard`:

```bash
cat > ~/petit_claude/.env.dashboard <<'EOF'
PETIT_DATA_DIR=/home/yourname/petit_claude
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PORT=8765
EOF
```

- `DASHBOARD_HOST`: `0.0.0.0` listens on all interfaces. Set a Tailscale IP for VPN-only access.
- Check Tailscale IP: `tailscale ip -4`

### 2. Register & Start Service

```bash
sudo cp dashboard/petit-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable petit-dashboard
sudo systemctl start petit-dashboard

# Check status
sudo systemctl status petit-dashboard

# View logs
journalctl -u petit-dashboard -f
```

## Authentication (Optional)

Add Basic auth + 7-day sessions to the dashboard.

### Roles

| Role | View | Chat/Control | Settings |
|------|------|-------------|----------|
| admin | OK | OK | OK |
| operator | OK | OK | No |
| viewer | OK | No | No |

### Configuration

Create `~/petit_claude/auth.json`:

```bash
cp dashboard/auth.json.example ~/petit_claude/auth.json
vim ~/petit_claude/auth.json  # Set passwords
```

```json
{
  "users": {
    "admin": {"password": "your-password", "role": "admin"},
    "friend": {"password": "friend-password", "role": "operator", "characters": ["puchiko"]},
    "guest": {"password": "guest-password", "role": "viewer"}
  }
}
```

Restart the dashboard to enable auth. Without `auth.json`, no authentication is required (legacy behavior).

### Character Visibility

The `characters` field restricts which characters a user can see and interact with.

- No `characters` field or empty array -> all characters visible
- `characters: ["puchiko"]` -> only puchiko visible (tabs, chat, memory, diary)
- `admin` role ignores `characters` and always sees everything
- Group chat also respects character restrictions

## API Usage Management

Settings to prevent excessive Claude API usage:

- **Adjust autonomous action frequency**: Schedule control in `autonomous-action.sh` — active hours (every run) vs inactive hours (probability-based). Set time ranges in `characters/{id}/settings.json` `active_hours`
- **Stop autonomous actions**: Comment out the crontab entry (`#` at the start)
- **Dashboard diary generation**: Manual button or once daily (23:50). Does not run frequently
- **Anthropic Console**: Check usage and set spending limits at https://console.anthropic.com/settings/usage

```bash
# Temporarily stop all autonomous actions
crontab -l | sed 's/^\(.*autonomous-action\)/#\1/' | crontab -

# Resume
crontab -l | sed 's/^#\(.*autonomous-action\)/\1/' | crontab -
```

## Estimated API Usage

With 2 characters and default settings (`active_hours: [[7,8],[12,13],[18,24]]`):

| Type | Frequency | Calls/Day | Notes |
|------|-----------|-----------|-------|
| Autonomous (active hours) | Every 20 min | ~24/char | 8h x 3/h |
| Autonomous (daytime inactive) | Hourly :00, 30% chance | ~3/char | 9h x 0.3 |
| Autonomous (nighttime) | Hourly :00, 10% chance | ~1/char | 7h x 0.1 |
| Diary generation | 23:50 | 1/char | |
| desire_updater | Every 5 min | 0 | Direct SQLite read, no API |
| **Total (2 characters)** | | **~58/day** | |

### Cost Estimate (Sonnet 4)

| Period | Estimate |
|--------|----------|
| 1 day | ~$1.50 |
| 1 month | ~$45 |

Heavy tool usage can increase costs; expect $70-100/month in practice.

### Saving Costs

- **Narrow `active_hours`**: e.g., `[[18,23]]` only -> less than half
- **Lower inactive probability**: Daytime 30%->10%, nighttime 10%->0% in `autonomous-action.sh`
- **Fewer characters**: 1 character = half the cost
- **Set limits on Anthropic Console**: https://console.anthropic.com/settings/usage

## Backup & Restore

```bash
# Backup
bash ~/petit_claude/backup/save.sh

# Restore
bash ~/petit_claude/backup/restore.sh ~/petit_claude/backup/YYYYMMDD_HHMMSS
```

Daily automatic backup at 4:00 AM via cron (7-day retention). See `~/petit_claude/backup/README.md` for details.

## Crontab

`create_character.py` auto-adds per-character entries, but for manual editing:

```bash
# --- Per character (2 lines each) ---

# Desire level update (every 5 min)
*/5  * * * * cd /path/to/embodied-claude/desire-system && uv run python desire_updater.py <char_id> >> ~/petit_claude/.autonomous-logs/<char_id>/desire-$(date +\%Y\%m\%d).log 2>&1

# Autonomous action (every 20 min)
*/20 * * * * /path/to/embodied-claude/autonomous-action.sh <char_id>

# --- Shared ---

# Daily diary summary (23:50, all characters)
50 23 * * * cd /path/to/embodied-claude/dashboard && uv run python generate_diary.py >> ~/petit_claude/.autonomous-logs/diary.log 2>&1

# Backup (daily 4:00, 7-day retention)
0 4 * * * bash ~/petit_claude/backup/save.sh && find ~/petit_claude/backup -maxdepth 1 -type d -name "[0-9]*" -mtime +7 -exec rm -rf {} \;
```

## License

MIT License

## Acknowledgments

- [kmizu](https://github.com/kmizu) - [embodied-claude](https://github.com/kmizu/embodied-claude) original author
- [ROS Cube Petit](https://github.com/sbgisen/cube_petit_ros) - the original robot project

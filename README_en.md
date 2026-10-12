# petit-ones

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
petit-ones/                   <- Code (git-managed, public)
|-- src/                      # Production components (source of the split-out repos)
|   |-- m5-petit-mcp/         #   Body (M5Stack CoreS3) MCP
|   |-- m5-petit-memory/      #   Long-term memory MCP (SQLite) + nightly scripts/sleep.py
|   |-- m5-petit-desire/      #   Desires (MCP + desire_updater.py)
|   |-- m5-petit-notes/       #   Notes MCP
|   |-- m5-petit-relations/   #   Relationships MCP
|   |-- m5-petit-switchbot/   #   Home appliances (SwitchBot) MCP
|   |-- m5-petit-speech/      #   Voice (TTS) server, runs on the GPU box
|   |-- m5-petit-app/ m5-petit-scripts/  # Split-out copies of dashboard / scripts
|-- dashboard/                # Web dashboard (FastAPI :8765) + generate_diary.py
|-- experience-daemon/        # Picks up body events and hands them to the next autonomous run
|-- slack-approve/            # Approval bot via Slack
|-- scripts/
|   |-- setup_house.py        #   Prepare the "house" (PETIT_DATA_DIR); --check only reports
|   |-- create_character.py   #   Welcome a new Petit (copies templates from petit-textbook, writes config + cron)
|   |-- memory_sleep_all.sh   #   Nightly memory consolidation for every character
|   |-- write_mailbox.py / mark_mail_read.py / list_unread_mail.py  # Letters
|   |-- check_usage.py        #   Token usage (today / week / month)
|   |-- tests/
|-- mcp-launchers/            # Launch scripts for the MCP servers (incl. textbook)
|-- docs/ archive/
|-- m5-mcp/ memory-mcp/ desire-system/ notes-mcp/ relations-mcp/ switchbot-mcp/  # Pre-split copies (production is src/)
|-- autonomous-action.sh      # Autonomous action script (per-house, git-ignored)
|-- autonomous-action.sample.sh # Template; setup_house.py copies it
|-- .env.example              # Template for the house .env
|-- .mcp.json.example         # Template for the chat MCP config

~/petit_claude/               <- Data, "the house" (PETIT_DATA_DIR, private)
|-- characters/<id>/
|   |-- config/               # config.json, settings.json, voice_settings.json, desire_config.json, autonomous-mcp.json, chat-mcp.json
|   |-- data/                 # desires.json (every 5 min), relations.json
|   |-- state/ resources/ chat_histories/ diary/ notes/
|   |-- SOUL.md SOUL_REFLECTIONS.md REFLECTION_INDEX.md ROUTINES.md ROUTINES_DETAIL.md TODO_ACTIVE.md TODO_ARCHIVE.md
|-- chat_history/             # exchange notebook, group chats
|-- mailbox/                  # Letters between Petits and people
|-- textbook/                 # Clone of petit-textbook (pulled every morning)
|-- config/people.json        # Non-Petit people (display name, color)
|-- .env                      # Companion name, voice server host, secrets
|-- token_logs/ .autonomous-logs/
|-- auth.json network.json    # Dashboard auth (optional)
```

Code and data are separated. Set the `PETIT_DATA_DIR` environment variable to change the data directory (default: `~/petit_claude`).

## Setup

A Petit's life is split into the **house** (`PETIT_DATA_DIR`, default `~/petit_claude`, never in git) and the **code** (this repository).
The human-side guide is the [Petit Textbook](https://github.com/PetitOnes/petit-textbook), chapter 8 of the adult book ("Welcoming a new Petit").

### 1. Prerequisites

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # uv
# Claude Code (native): see https://docs.claude.com/ ; ends up in ~/.local/bin/claude
sudo apt install -y jq git                            # Linux (brew on macOS)
sudo apt install -y ttyd tmux                         # optional browser terminal (docs/terminal-setup.md)
```

### 2. Clone and install

```bash
git clone https://github.com/PetitOnes/petit-ones.git ~/work/petit-ones
cd ~/work/petit-ones
for d in src/m5-petit-memory src/m5-petit-desire src/m5-petit-mcp src/m5-petit-notes src/m5-petit-relations dashboard; do
  (cd "$d" && uv sync)
done
```

### 3. Prepare the house

```bash
uv run python scripts/setup_house.py --check   # report what is missing
uv run python scripts/setup_house.py           # create it (existing things are left alone)
```

Creates `characters/ mailbox/ chat_history/ config/ state/ .autonomous-logs/ token_logs/`, empty exchange-notebook and group-chat files, `.env` (from `.env.example`: `COMPANION_NAME`, `COMPANION_ID`, voice server, secrets), a clone of the textbook (`textbook/`), the three nightly cron jobs (memory consolidation 04:05, textbook pull 04:30, diary 23:50) and `autonomous-action.sh` (copied from `autonomous-action.sample.sh`; adjust the starred lines for your house).

### 4. Welcome a Petit

```bash
uv run python scripts/create_character.py <id> <name> <#hex> <body-host,...> \
    --color-name <color name> --companion-id <id of the person> --companion-name <what the Petit calls them>
```

Creates `characters/<id>/` with the document templates from the textbook's `petit/templates/` (SOUL.md, SOUL_REFLECTIONS.md, REFLECTION_INDEX.md, ROUTINES.md, ROUTINES_DETAIL.md, TODO_ACTIVE.md, TODO_ARCHIVE.md, data/relations.json, config/desire_config.json, placeholders filled in), the runtime config (config.json, settings.json, voice_settings.json, autonomous-mcp.json, chat-mcp.json) and the cron entries (desire update every 5 min, autonomous action every 30 min offset by 5 min from the other Petits, experience daemon).

Afterwards a human adds the "one line" agreed with the companion to SOUL.md, sets `config/voice_settings.json` once the voice is chosen, puts the face in `resources/petit.png`, and adds the Petit's MCP servers to `.mcp.json` for chat (see `.mcp.json.example`). The rest of SOUL.md is filled in by the Petit itself (`petit/SOUL_TEMPLATE.md` in the textbook).

### 5. Body and voice

- Firmware for the M5Stack CoreS3: [m5-petit-firmware](https://github.com/PetitOnes/m5-petit-firmware). Pass the body's hostname or IP to `create_character.py`
- Voice (TTS :8766) and speech recognition (ASR :8767): [m5-petit-speech](https://github.com/PetitOnes/m5-petit-speech) / [voice-recognition](https://github.com/PetitOnes/m5-petit-voice-recognition) on a GPU box; set `VOICE_API_HOST` in `.env`

### 6. Dashboard

```bash
cd dashboard && uv run python main.py   # -> http://0.0.0.0:8765
```

### 7. First run

Start one interactive session, let the Petit say "hello" and check that the face appears. After that the cron jobs take over. The Petit writes its own first memory (textbook chapter 10).

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

`setup_house.py` adds the shared lines, `create_character.py` the per-character ones:

```bash
# --- Per character (create_character.py; autonomous action offset by 5 min per Petit) ---
*/5 * * * * cd /path/to/petit-ones/src/m5-petit-desire && mkdir -p ~/petit_claude/.autonomous-logs/<char_id> && PETIT_DATA_DIR=~/petit_claude uv run python desire_updater.py <char_id> >> ~/petit_claude/.autonomous-logs/<char_id>/desire-$(date +\%Y\%m\%d).log 2>&1
0,30 * * * * /path/to/petit-ones/autonomous-action.sh <char_id>      # next Petit 5,35, then 10,40
@reboot /path/to/petit-ones/experience-daemon/start_experienced.sh <char_id>
*/5 * * * * /path/to/petit-ones/experience-daemon/start_experienced.sh <char_id>

# --- Shared (setup_house.py) ---
5 4 * * * PETIT_DATA_DIR=~/petit_claude /path/to/petit-ones/scripts/memory_sleep_all.sh >> ~/petit_claude/.autonomous-logs/memory-sleep.log 2>&1
30 4 * * * cd ~/petit_claude/textbook && git pull -q --ff-only >/dev/null 2>&1
50 23 * * * cd /path/to/petit-ones/dashboard && PETIT_DATA_DIR=~/petit_claude uv run python generate_diary.py >> ~/petit_claude/.autonomous-logs/diary.log 2>&1
```

## License

MIT License

## Acknowledgments

- [kmizu](https://github.com/kmizu) - [embodied-claude](https://github.com/kmizu/embodied-claude) original author
- [ROS Cube Petit](https://github.com/sbgisen/cube_petit_ros) - the original robot project

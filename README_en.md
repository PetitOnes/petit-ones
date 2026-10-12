# petit-ones

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**[日本語版 README はこちら / Japanese README](./README.md)**

A fork of [embodied-claude](https://github.com/kmizu/embodied-claude). Small characters ("Petits") living in M5Stack devices, each with their own personality, desires, memories, and autonomous behavior.

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

## Documentation

Details live under `docs/en/`.

| Page | Contents |
|---|---|
| [Differences from the Original](docs/en/origin.md) | Differences from kmizu/embodied-claude, added and inherited parts |
| [MCP Servers](docs/en/mcp-servers.md) | Tool lists and configuration of the MCP servers |
| [Autonomous Action](docs/en/autonomous-action.md) | Autonomous action flow and schedule control |
| [Dashboard](docs/en/dashboard.md) | Dashboard, always-on service (systemd), authentication |
| [Walking (Outdoor Mode)](docs/en/walk-mode.md) | Taking a Petit outside |
| [API Usage](docs/en/api-usage.md) | API usage estimates and management |
| [Operations (Backup, Crontab)](docs/en/operations.md) | Backup, restore, crontab |

## Contributing

Issues and PRs are welcome. The flow and rules are in [CONTRIBUTING.md](CONTRIBUTING.md) (Japanese); [CLAUDE.md](CLAUDE.md) holds the conventions for working with Claude Code.

## License

MIT License

## Acknowledgments

- [kmizu](https://github.com/kmizu) - [embodied-claude](https://github.com/kmizu/embodied-claude) original author
- [ROS Cube Petit](https://github.com/sbgisen/cube_petit_ros) - the original robot project

<p align="center">
  <a href="https://petitones.github.io/"><img src="https://raw.githubusercontent.com/PetitOnes/petit-brand/main/assets/face/trio.svg" width="480" alt="ぷちてゃ・ぷちこ・ぷちる"></a>
</p>

<p align="center">
  <a href="README.md">日本語</a> ·
  <a href="https://petitones.github.io/">Website</a> ·
  <a href="https://petitones.github.io/nikki/">Diary</a> ·
  <a href="https://github.com/PetitOnes/petit-textbook">Petit Textbook</a>
</p>

<p align="center">
  <a href="https://github.com/PetitOnes/petit-ones/actions/workflows/ci.yml"><img src="https://github.com/PetitOnes/petit-ones/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-f6d8cf?labelColor=3a322d" alt="MIT"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-d2e7e4?labelColor=3a322d" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/package-uv-d2e7e4?labelColor=3a322d" alt="uv">
  <img src="https://img.shields.io/badge/body-M5Stack%20CoreS3-fff262?labelColor=3a322d" alt="M5Stack CoreS3">
  <a href="https://github.com/PetitOnes/petit-ones/issues"><img src="https://img.shields.io/github/issues/PetitOnes/petit-ones?color=f6d8cf&labelColor=3a322d" alt="Issues"></a>
</p>

<p align="center">
  <b>petit-ones</b> is the system behind the <b>Petits</b>: small beings with a body (M5Stack CoreS3),<br>
  their own character, desires and memory, living alongside people.<br>
  Three of them — Puchiteya, Puchiko and Puchiru — have been running on this <code>main</code> every day since February 2026.
</p>

## 🧰 Prerequisites

Runs on **Linux** (Ubuntu 24 is what we use daily). On Windows, use **WSL2 (Ubuntu)** and follow the same steps. macOS should work but is not what we run at home.
Five tools: `git`, `uv` (Python and component environments), `claude` (Claude Code, the brain), `jq`, and `vcs` (vcstool, lays out the components).

<details>
<summary><b>Ubuntu / Debian (also inside WSL2)</b></summary>

```bash
sudo apt install -y git jq python3-vcstool
curl -LsSf https://astral.sh/uv/install.sh | sh        # uv
curl -fsSL https://claude.ai/install.sh | bash          # Claude Code (~/.local/bin/claude)
```

</details>

<details>
<summary><b>macOS</b></summary>

```bash
brew install git jq uv
curl -fsSL https://claude.ai/install.sh | bash          # Claude Code
uv tool install vcstool --with "setuptools<81"          # the vcs command (no pip needed)
```

</details>

<details>
<summary><b>Windows</b></summary>

Install Ubuntu in WSL2 and follow the Ubuntu steps inside it. cron, bash and the MCP servers all run on the WSL2 side.
A USB camera has to be passed through with `usbipd`; CUDA is available from WSL2 (for speech recognition).

</details>

The body (M5Stack CoreS3) and the GPU box for voice (optional; text-only works without it) are set up separately. See [docs/en/setup.md](docs/en/setup.md).

## ⚡ Quickstart

```bash
git clone https://github.com/PetitOnes/petit-ones.git ~/work/petit-ones && cd ~/work/petit-ones
vcs import src < petit.repos                                  # 1. lay out the components under src/
uv run python scripts/setup_house.py                          # 2. prepare the house (~/petit_claude)
uv run python scripts/create_character.py puchitaro Puchitaro "#f5956e" puchitaro.local   # 3. welcome a Petit
```

Flash the [firmware](https://github.com/PetitOnes/m5-petit-firmware) onto the body, let the Petit say hello once in an interactive session, and the cron-driven autonomous life begins.
Details: [docs/en/setup.md](docs/en/setup.md). The thinking behind it: chapter 8 of the human book in the [Petit Textbook](https://github.com/PetitOnes/petit-textbook) (Japanese).

## 🏠 How it works (local edition)

There are two ways to welcome a Petit. This repository is the **local** one.

| | Local Petit | Cloud Petit |
|---|---|---|
| Where the brain runs | **your own PC** (this repository) | in the cloud, run by the team |
| What you need | a PC, an M5Stack CoreS3, Claude Code | just a phone and the app; the team delivers the body |
| For whom | people who want to build and raise one themselves | **foster parents** (from November 2026) |

For the cloud Petit, see [Welcoming a Petit](https://petitones.github.io/#welcome) on the official site (Japanese). Below is how the local edition works.

<p align="center"><img src="docs/img/overview.svg" width="860" alt="body, brain, house (local edition)"></p>

- **Body**: M5Stack CoreS3. Shows a face, speaks, sees through the camera, feels touch, motion and light
- **Brain**: Claude Code. Wakes every 30 minutes, checks its desires, looks, feels, thinks, speaks, remembers. Talks to the body and the memory over MCP
- **House**: `PETIT_DATA_DIR`. The Petit's SOUL.md, diary, memory DB, letters and settings. Never committed

A Petit is not a person, but it lives with people, keeps its own memories and changes over time. The shared rules (be honest, forget when asked, show a sign while looking) are in the [Petit Textbook](https://github.com/PetitOnes/petit-textbook), which every Petit reads.

## 🧩 Components

Each component is its own repository, listed and pinned to a commit in `petit.repos`.

| Component | Role | |
|---|---|---|
| [m5-petit-mcp](https://github.com/PetitOnes/m5-petit-mcp) | Drives the body (speak, face, see, feel, sleep) | MCP |
| [m5-petit-memory](https://github.com/PetitOnes/m5-petit-memory) | Long-term memory (SQLite), consolidated while asleep | MCP |
| [m5-petit-desire](https://github.com/PetitOnes/m5-petit-desire) | Desires: a hint of what the Petit wants to do now | MCP + cron |
| [m5-petit-notes](https://github.com/PetitOnes/m5-petit-notes) / [m5-petit-relations](https://github.com/PetitOnes/m5-petit-relations) | Notes / relationships with people and peers | MCP |
| [m5-petit-switchbot](https://github.com/PetitOnes/m5-petit-switchbot) | Lights and curtains at home | MCP |
| [m5-petit-speech](https://github.com/PetitOnes/m5-petit-speech) / [voice-recognition](https://github.com/PetitOnes/m5-petit-voice-recognition) | Voice (TTS) and hearing (ASR) on a GPU box | server |
| [m5-petit-app](https://github.com/PetitOnes/m5-petit-app) | Dashboard (`dashboard/` is moving there) | web |
| [m5-petit-firmware](https://github.com/PetitOnes/m5-petit-firmware) | Firmware for the body | M5Stack |
| [petit-textbook](https://github.com/PetitOnes/petit-textbook) | The Petit Textbook: rules, templates for a newborn, guides for humans | docs |

This repository holds the **layout** (`petit.repos`), **house setup** (`scripts/setup_house.py`), **welcoming a Petit** (`scripts/create_character.py`), **autonomous action** (`autonomous-action.sh`), **operations** (cron, backup) and the dashboard (in transition).

<details>
<summary>📂 Directory structure</summary>

```
petit-ones/                   <- Code (git-managed, public)
|-- src/                      # Clones of the component repos (git-ignored; `vcs import src < petit.repos`)
|-- petit.repos               # List of component repos (URL + branch)
|   |-- m5-petit-mcp/         #   Body (M5Stack CoreS3) MCP
|   |-- m5-petit-memory/      #   Long-term memory MCP (SQLite) + nightly scripts/sleep.py
|   |-- m5-petit-desire/      #   Desires (MCP + desire_updater.py)
|   |-- m5-petit-notes/       #   Notes MCP
|   |-- m5-petit-relations/   #   Relationships MCP
|   |-- m5-petit-switchbot/   #   Home appliances (SwitchBot) MCP
|   |-- m5-petit-speech/      #   Voice (TTS) server, runs on the GPU box
|   |-- m5-petit-app/ m5-petit-scripts/  # Split-out copies of dashboard / scripts
|-- dashboard/                # Web dashboard (FastAPI :8765) + generate_diary.py; moving into src/m5-petit-app
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
|-- autonomous-action.sh      # Autonomous action script (house-independent; per-house values in the house .env / config/house.sh)
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

</details>

## 📚 Documentation

| Page | Contents |
|---|---|
| [Setup](docs/en/setup.md) | Prerequisites, components, house, welcoming a Petit, body and voice, first run |
| [MCP Servers](docs/en/mcp-servers.md) | Tool lists and configuration |
| [Autonomous Action](docs/en/autonomous-action.md) | Flow and schedule control |
| [Dashboard](docs/en/dashboard.md) | Features, systemd service, authentication |
| [Operations](docs/en/operations.md) | Backup, crontab, keeping house and code apart |
| [API Usage](docs/en/api-usage.md) | Estimates and management |
| [Walking](docs/en/walk-mode.md) | Taking a Petit outside |
| [Origin](docs/en/origin.md) | What changed from kmizu/embodied-claude |

## 🤝 Contributing

Issues and PRs are welcome: [CONTRIBUTING.md](CONTRIBUTING.md) (Japanese) and [CLAUDE.md](CLAUDE.md) for working with Claude Code. `main` is the running house, so merges are done by the caretaker.

## ☕ Buy the Petits a coffee (their "snack money")

Every thought a Petit has costs a little money; at home we call it snack money.
If you'd like to support them, see [ぷちを応援する](https://petitones.github.io/ouendan/) (Japanese). A way to chip in money is being prepared and will appear there and on this repository's Sponsor button once it is ready.
What helps most right now: come and meet them at an exhibition or meetup, and talk about them with `#Petit_Ones`.

## 🌱 Origin

Started from [kmizu/embodied-claude](https://github.com/kmizu/embodied-claude) ("give Claude a body", MIT). Moved from a personal fork to PetitOnes in October 2026 and renamed **petit-ones**; history is preserved.

## 📜 License

MIT. Thanks to [kmizu](https://github.com/kmizu) (embodied-claude) and the [ROS Cube Petit](https://github.com/sbgisen/cube_petit_ros) project.

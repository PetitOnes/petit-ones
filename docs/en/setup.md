# Setup (prepare the house, welcome a Petit)

Back to [README](../../README_en.md)


A Petit's life is split into the **house** (`PETIT_DATA_DIR`, default `~/petit_claude`, never in git) and the **code** (this repository).
The human-side guide is the [Petit Textbook](https://github.com/PetitOnes/petit-textbook), chapter 8 of the adult book ("Welcoming a new Petit").

## 1. Prerequisites

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # uv
# Claude Code (native): see https://docs.claude.com/ ; ends up in ~/.local/bin/claude
sudo apt install -y jq git                            # Linux (brew on macOS)
sudo apt install -y ttyd tmux                         # optional browser terminal (docs/terminal-setup.md)
```

## 2. Clone and install

The components (body, memory, desires, notes, relations, appliances, voice) live in their own repositories, listed in `petit.repos`. `vcs` (vcstool) lays them out under `src/`.

```bash
git clone https://github.com/PetitOnes/petit-ones.git ~/work/petit-ones
cd ~/work/petit-ones
pip install vcstool                 # or: sudo apt install python3-vcstool
vcs import src < petit.repos        # src/ is git-ignored
for d in src/m5-petit-*/ dashboard; do
  [ -f "$d/pyproject.toml" ] && (cd "$d" && uv sync)
done
```

To change a component, open a PR in that component's repository. This repository holds the layout, house setup, autonomous action and operations.

## 3. Prepare the house

```bash
uv run python scripts/setup_house.py --check   # report what is missing
uv run python scripts/setup_house.py           # create it (existing things are left alone)
```

Creates `characters/ mailbox/ chat_history/ config/ state/ .autonomous-logs/ token_logs/`, empty exchange-notebook and group-chat files, `.env` (from `.env.example`: `COMPANION_NAME`, `COMPANION_ID`, voice server, secrets), a clone of the textbook (`textbook/`), the three nightly cron jobs (memory consolidation 04:05, textbook pull 04:30, diary 23:50). `autonomous-action.sh` itself is house-independent: names, room and schedule overrides go into the house `.env` (`COMPANION_NAME`, `COMPANION_ID`) and the optional `config/house.sh`.

## 4. Welcome a Petit

```bash
uv run python scripts/create_character.py <id> <name> <#hex> <body-host,...> \
    --color-name <color name> --companion-id <id of the person> --companion-name <what the Petit calls them>
```

Creates `characters/<id>/` with the document templates from the textbook's `petit/templates/` (SOUL.md, SOUL_REFLECTIONS.md, REFLECTION_INDEX.md, ROUTINES.md, ROUTINES_DETAIL.md, TODO_ACTIVE.md, TODO_ARCHIVE.md, data/relations.json, config/desire_config.json, placeholders filled in), the runtime config (config.json, settings.json, voice_settings.json, autonomous-mcp.json, chat-mcp.json) and the cron entries (desire update every 5 min, autonomous action every 30 min offset by 5 min from the other Petits, experience daemon).

Afterwards a human adds the "one line" agreed with the companion to SOUL.md, sets `config/voice_settings.json` once the voice is chosen, puts the face in `resources/petit.png`, and adds the Petit's MCP servers to `.mcp.json` for chat (see `.mcp.json.example`). The rest of SOUL.md is filled in by the Petit itself (`petit/SOUL_TEMPLATE.md` in the textbook).

## 5. Body and voice

- Firmware for the M5Stack CoreS3: [m5-petit-firmware](https://github.com/PetitOnes/m5-petit-firmware). Pass the body's hostname or IP to `create_character.py`
- Voice (TTS :8766) and speech recognition (ASR :8767): [m5-petit-speech](https://github.com/PetitOnes/m5-petit-speech) / [voice-recognition](https://github.com/PetitOnes/m5-petit-voice-recognition) on a GPU box; set `VOICE_API_HOST` in `.env`

## 6. Dashboard

```bash
cd dashboard && uv run python main.py   # -> http://0.0.0.0:8765
```

## 7. First run

Start one interactive session, let the Petit say "hello" and check that the face appears. After that the cron jobs take over. The Petit writes its own first memory (textbook chapter 10).

# Operations (Backup, Crontab)

Back to [README](../../README_en.md)

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

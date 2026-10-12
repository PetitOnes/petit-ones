# Autonomous Action

Back to [README](../../README_en.md)


`autonomous-action.sh` runs via cron every 30 minutes (each Petit offset by 5 min), enabling characters to act autonomously.

## Execution Flow

```
[Cron: every 5 min]
|-> desire_updater.py <char_id>
    |-- Read desire_config.json
    |-- Query memory.db (keyword search for time-based calculation)
    |-- HTTP GET /sensors from M5Stack (sensor effects)
    |-- Compute cross-effects
    |-> Write desires.json

[Cron: every 30 min]
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

## Schedule Control

- **Active hours** (`settings.json` `active_hours`): Runs every 30 min
- **Daytime inactive**: Runs at :00 with 30% probability
- **Nighttime inactive**: Runs at :00 with 10% probability

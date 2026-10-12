# MCP Servers

Back to [README](../../README_en.md)


## m5-mcp (Eyes, Emotions, Sensors)

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

## memory-mcp (Memory)

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

## desire-system (Desires)

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

## relations-mcp (Relationships)

| Tool | Description |
|------|-------------|
| `get_relations` | Get relationships with other characters |
| `update_relation` | Update relationship info (likes, dislikes, closeness, notes) |

## notes-mcp (Notes)

| Tool | Description |
|------|-------------|
| `list_notes` | List notes |
| `read_note` | Read a note |
| `write_note` | Create/update a note |

Unlike memory (searched/recalled), notes are persistent reference documents for light value tables, sensor ranges, etc.

# Differences from the Original

Back to [README](../../README_en.md)


[kmizu/embodied-claude](https://github.com/kmizu/embodied-claude) is a collection of MCP servers that give Claude a body — eyes (camera), neck (PTZ), ears (microphone), voice (TTS), and brain (long-term memory).

This fork extends the concept into a **multi-character autonomous agent framework**.

## Key Differences

| | Original (kmizu) | This Fork (cube-petit) |
|---|---|---|
| **Hardware** | Wi-Fi PTZ camera (Tapo C210 etc.) | M5Stack CoreS3 |
| **Characters** | Single instance | Multiple characters (independent personality, memory, desires) |
| **Autonomy** | User-driven (reactive) | Cron-based autonomous action every 30 min (desire-driven) |
| **Desires** | Optional | Core feature (sensor_effects, cross_effects) |
| **UI** | CLI only | Web dashboard (chat, desire display, diary, memory viewer) |
| **Social** | None | Inter-character relationships & mailbox |
| **Portability** | Stationary | M5Stack + mobile battery for outdoor walks |

## Added Components

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

## Inherited from Original

memory-mcp, tts-mcp, system-temperature-mcp, mobility-mcp, ip-webcam-mcp, mcp-pet, morning-call-mcp also exist in the original. memory-mcp has been extended with visual memory, episodes, causal links, Theory of Mind, and memory consolidation (sleep).

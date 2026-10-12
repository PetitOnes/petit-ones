# Dashboard

Back to [README](../../README_en.md)

## Dashboard

- Desire bars: Real-time display of each character's desire levels
- Chat: Talk directly to a character
- Group chat: Send to all characters simultaneously
- Interaction: Set up character-to-character conversations
- Settings: Active hours, camera/audio/mic toggles
- Memory list: Browse memories by date
- Diary: Daily summary (auto-generated at 23:50)

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

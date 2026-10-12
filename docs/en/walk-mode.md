# Walking (Outdoor Mode)

Back to [README](../../README_en.md)


Take M5Stack devices outside for a walk. Connect from home PC to M5Stack via Android tethering + Tailscale VPN.

## Requirements

- Android phone (tethering + Tailscale)
- Mobile battery (to power M5Stack)
- Tailscale installed on home PC

## Architecture

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

## Setup Steps

### 1. Install Tailscale

- Android: Install [Tailscale](https://play.google.com/store/apps/details?id=com.tailscale.ipn) from Google Play
- Home PC: `curl -fsSL https://tailscale.com/install.sh | sh`
- Log in with the same account on both

### 2. Configure Subnet Router on Android

Allow access to the tethering local network (where M5Stack connects) from the home PC via Tailscale.

```
Android Tailscale app -> Settings -> Subnet router
-> Add tethering subnet (e.g., 192.168.49.0/24)
```

The tethering subnet varies by device. Check M5Stack's IP after connecting to tethering and append `/24`.

### 3. Approve Subnet in Tailscale Admin Console

Go to https://login.tailscale.com/admin/machines, open the phone's machine, and approve the subnet route.

### 4. Accept Routes on Home PC

```bash
sudo tailscale up --accept-routes
```

### 5. Verify Connection

With M5Stack connected to phone's tethering:

```bash
ping <M5Stack IP>  # e.g., ping 192.168.49.1
```

If it responds, you're set. Control through the dashboard as usual.

## Operating During Walks

Access `http://<home PC Tailscale IP>:8765` from your phone's browser to use the dashboard.

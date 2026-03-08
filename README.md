# pixels

Scripts for the AWTRIX 3 display at `pixels.local` (Ulanzi TC001).

## Setup

Device: Ulanzi TC001 flashed with AWTRIX 3 firmware  
Hostname: `pixels.local` / `192.168.6.1`

## Scripts

### enrollment.py

Displays Tradewinds enrollment stats:
- **tw_enrolled**: Green checkmark + enrolled count
- **tw_applied**: Yellow pencil + applied count

Cycles between apps every 3 seconds.

```bash
python3 enrollment.py
```

Runs via OpenClaw cron every 15 minutes.

## Icon Approach

Uses base64-encoded static JPEG icons (generated in Python via PIL) instead of LaMetric icon IDs. This avoids issues with animated GIFs that reset to blank frames.

## AWTRIX API Quick Reference

```bash
# Push custom app
curl -X POST http://pixels.local/api/custom?name=myapp \
  -H "Content-Type: application/json" \
  -d '{"icon": 2, "text": "hello", "color": "#FF0000"}'

# Send notification
curl -X POST http://pixels.local/api/notify \
  -H "Content-Type: application/json" \
  -d '{"text": "Alert!", "duration": 5000}'

# Check current screen (256 RGB values)
curl http://pixels.local/api/screen

# Reboot
curl -X POST http://pixels.local/api/reboot

# Settings
curl -X POST http://pixels.local/api/settings \
  -H "Content-Type: application/json" \
  -d '{"TIM": false, "TEMP": false}'
```

## Dependencies

- Python 3
- PIL/Pillow
- google-api-python-client, google-auth (for enrollment.py)

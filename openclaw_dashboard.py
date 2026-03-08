#!/usr/bin/env python3
"""
openclaw_dashboard.py
Real-time OpenClaw stats on AWTRIX display.

Polls OpenClaw every 3 seconds and pushes to pixels.local:
  - Active sessions count
  - Current model (Opus/Sonnet indicator)
  - Context usage percentage

Run as daemon: python3 openclaw_dashboard.py
Stop with Ctrl+C
"""

import json
import urllib.request
import subprocess
import time
import sys
import io
import base64
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
AWTRIX_HOST = "http://192.168.6.1"
POLL_INTERVAL = 1  # seconds
APP_NAME = "openclaw"

# ── Icons (base64 JPEG) ───────────────────────────────────────────────────────
def make_icon(color_rgb):
    """Create a simple 8x8 icon with a claw/lobster shape."""
    from PIL import Image
    img = Image.new('RGB', (8, 8), (0, 0, 0))
    # Simple claw shape
    pixels = [
        (1, 1), (2, 1), (5, 1), (6, 1),
        (0, 2), (1, 2), (2, 2), (5, 2), (6, 2), (7, 2),
        (1, 3), (2, 3), (5, 3), (6, 3),
        (2, 4), (3, 4), (4, 4), (5, 4),
        (3, 5), (4, 5),
        (2, 6), (3, 6), (4, 6), (5, 6),
        (1, 7), (2, 7), (5, 7), (6, 7),
    ]
    for x, y in pixels:
        img.putpixel((x, y), color_rgb)
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=95)
    return base64.b64encode(buf.getvalue()).decode()

# Pre-generate icons
ICON_OPUS = make_icon((255, 100, 50))    # Orange for Opus
ICON_SONNET = make_icon((100, 150, 255)) # Blue for Sonnet
ICON_IDLE = make_icon((80, 80, 80))      # Gray when no sessions

# ── OpenClaw Stats ────────────────────────────────────────────────────────────
def get_openclaw_stats():
    """Get active sessions and token usage from OpenClaw."""
    try:
        # Run openclaw status and parse
        result = subprocess.run(
            ['openclaw', 'status', '--json'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        pass
    
    # Fallback: parse sessions list via internal API
    try:
        # Use the gateway API directly
        sessions = get_active_sessions()
        return {
            'sessions': len(sessions),
            'details': sessions
        }
    except:
        return None

def get_active_sessions():
    """Get active sessions with age in seconds (max 30s window)."""
    import os
    sessions_file = os.path.expanduser('~/.openclaw/agents/main/sessions/sessions.json')
    try:
        with open(sessions_file, 'r') as f:
            data = json.load(f)
        
        now = time.time() * 1000
        sessions = []
        for key, session in data.items():
            if not isinstance(session, dict):
                continue
            updated = session.get('updatedAt', 0)
            age_sec = (now - updated) / 1000
            
            if age_sec < 30:  # Only show sessions active in last 30 seconds
                sessions.append({'key': key, 'age_sec': age_sec})
        
        # Sort by most recent first
        sessions.sort(key=lambda s: s['age_sec'])
        return sessions
    except Exception as e:
        print(f"[WARN] Failed to read sessions: {e}")
        return []

# ── Equalizer Bar Drawing ─────────────────────────────────────────────────────
def draw_bar(x_offset, height, max_height=8):
    """Draw a vertical bar with gradient (brighter at top)."""
    commands = []
    bar_width = 3  # 3 pixels wide per bar
    
    for y in range(max_height - height, max_height):
        # Gradient: brighter at top (lower y values when drawn)
        intensity = 1.0 - (y / max_height) * 0.6  # 100% at top, 40% at bottom
        r = int(255 * intensity)
        g = int(100 * intensity)
        b = int(50 * intensity)
        color = f"#{r:02x}{g:02x}{b:02x}"
        
        for dx in range(bar_width):
            commands.append({"dp": [x_offset + dx, y, color]})
    
    return commands

# ── AWTRIX Push ───────────────────────────────────────────────────────────────
def push_dashboard(sessions):
    """Push stats to AWTRIX display with equalizer bars."""
    draw_commands = []
    bar_width = 4  # 3px bar + 1px gap
    max_bars = 32 // bar_width  # How many bars fit on 32px display
    
    for i, session in enumerate(sessions[:max_bars]):
        x_offset = i * bar_width
        age_sec = session.get('age_sec', 30)
        
        # Map age to height: 0s = 8px, 30s = 1px (linear decay)
        height = max(1, int(8 - (age_sec / 30) * 7))
        draw_commands.extend(draw_bar(x_offset, height))
    
    payload = json.dumps({
        "draw": draw_commands,
        "duration": 5,
        "lifetime": 0,  # Never auto-remove
    }).encode()
    
    url = f"{AWTRIX_HOST}/api/custom?name={APP_NAME}"
    req = urllib.request.Request(
        url, data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        urllib.request.urlopen(req, timeout=5)
        return True
    except:
        return False

# ── Main Loop ─────────────────────────────────────────────────────────────────
def main():
    print(f"OpenClaw Dashboard starting... (polling every {POLL_INTERVAL}s)")
    print(f"Pushing to {AWTRIX_HOST}")
    print("Press Ctrl+C to stop\n")
    
    last_push = ""
    errors = 0
    
    while True:
        try:
            sessions = get_active_sessions()
            
            # Build state string for change detection (round age to reduce noise)
            state = "|".join(f"{s['key']}:{int(s['age_sec'])}" for s in sessions) or "idle"
            
            # Only push if something changed (reduce traffic)
            if state != last_push:
                success = push_dashboard(sessions)
                if success:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    ages = [f"{s['age_sec']:.0f}s" for s in sessions[:4]]
                    print(f"[{timestamp}] {len(sessions)} bars: {', '.join(ages) if ages else 'idle'}")
                    last_push = state
                    errors = 0
                else:
                    errors += 1
                    if errors > 3:
                        print(f"[WARN] Failed to push to AWTRIX ({errors} errors)")
            
            time.sleep(POLL_INTERVAL)
            
        except KeyboardInterrupt:
            print("\nStopping dashboard...")
            # Clear the app on exit
            try:
                req = urllib.request.Request(
                    f"{AWTRIX_HOST}/api/custom?name={APP_NAME}",
                    data=b'',
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                urllib.request.urlopen(req, timeout=3)
            except:
                pass
            break
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()

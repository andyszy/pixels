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
    """Get active sessions with activity level (hot = <5s, warm = <30s)."""
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
            age_ms = now - updated
            
            if age_ms < 5000:  # Very active (last 5 seconds)
                sessions.append({'key': key, 'level': 'hot'})
            elif age_ms < 30000:  # Semi-active (last 30 seconds)
                sessions.append({'key': key, 'level': 'warm'})
        return sessions
    except Exception as e:
        print(f"[WARN] Failed to read sessions: {e}")
        return []

# ── Crab Drawing ──────────────────────────────────────────────────────────────
def draw_crab(x_offset, color):
    """Generate draw instructions for a small crab at x_offset."""
    # Small 7x7 crab shape
    crab_pixels = [
        (1, 0), (5, 0),                          # Claws top
        (0, 1), (1, 1), (5, 1), (6, 1),          # Claws
        (1, 2), (2, 2), (4, 2), (5, 2),          # Upper body
        (2, 3), (3, 3), (4, 3),                  # Body middle
        (1, 4), (2, 4), (3, 4), (4, 4), (5, 4),  # Body
        (1, 5), (3, 5), (5, 5),                  # Legs
        (0, 6), (2, 6), (4, 6), (6, 6),          # Feet
    ]
    return [{"dp": [x + x_offset, y, color]} for x, y in crab_pixels]

# ── AWTRIX Push ───────────────────────────────────────────────────────────────
def push_dashboard(sessions):
    """Push stats to AWTRIX display with repeated crab icons."""
    # Draw crabs for each active session (max 4 to fit display)
    draw_commands = []
    num_crabs = min(len(sessions), 4)  # Cap at 4 crabs (display is 32px wide)
    
    for i in range(num_crabs):
        x_offset = i * 8  # Each crab is ~7px, space by 8
        level = sessions[i].get('level', 'warm')
        color = "#FF0000" if level == 'hot' else "#606060"  # Red for hot, gray for warm
        draw_commands.extend(draw_crab(x_offset, color))
    
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
            
            # Build state string for change detection
            state = "|".join(f"{s['key']}:{s['level']}" for s in sessions) or "idle"
            
            # Only push if something changed (reduce traffic)
            if state != last_push:
                success = push_dashboard(sessions)
                if success:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    hot = sum(1 for s in sessions if s['level'] == 'hot')
                    warm = sum(1 for s in sessions if s['level'] == 'warm')
                    print(f"[{timestamp}] {hot} hot, {warm} warm")
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

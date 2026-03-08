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
POLL_INTERVAL = 3  # seconds
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
    """Get active sessions from the gateway."""
    import os
    sessions_file = os.path.expanduser('~/.openclaw/agents/main/sessions/sessions.json')
    try:
        with open(sessions_file, 'r') as f:
            data = json.load(f)
        
        # Sessions are top-level keys (not nested)
        now = time.time() * 1000
        active = []
        for key, session in data.items():
            if not isinstance(session, dict):
                continue
            updated = session.get('updatedAt', 0)
            if now - updated < 300000:  # 5 minutes
                active.append({
                    'key': key,
                    'model': session.get('model', 'unknown'),
                    'tokens': session.get('totalTokens', 0),
                    'context': session.get('contextTokens', 200000),
                })
        return active
    except Exception as e:
        print(f"[WARN] Failed to read sessions: {e}")
        return []

# ── AWTRIX Push ───────────────────────────────────────────────────────────────
def push_dashboard(sessions, model, context_pct):
    """Push stats to AWTRIX display."""
    # Pick icon based on model
    if 'opus' in model.lower():
        icon = ICON_OPUS
        color = "#FF6432"  # Orange
    elif 'sonnet' in model.lower():
        icon = ICON_SONNET
        color = "#6496FF"  # Blue
    else:
        icon = ICON_IDLE
        color = "#808080"  # Gray
    
    # Format text: "1s 69%" (1 session, 69% context)
    text = f"{sessions}s {context_pct}%"
    
    payload = json.dumps({
        "icon": icon,
        "text": text,
        "color": color,
        "duration": 5,
        "lifetime": 0,  # Never auto-remove
        "noScroll": True,
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
            
            if sessions:
                # Use the most recent session's model
                sessions.sort(key=lambda s: s.get('tokens', 0), reverse=True)
                top = sessions[0]
                model = top.get('model', 'unknown')
                tokens = top.get('tokens', 0)
                context = top.get('context', 200000)
                context_pct = int((tokens / context) * 100) if context > 0 else 0
            else:
                model = 'idle'
                context_pct = 0
            
            n_sessions = len(sessions)
            
            # Only push if something changed (reduce traffic)
            current = f"{n_sessions}|{model}|{context_pct}"
            if current != last_push:
                success = push_dashboard(n_sessions, model, context_pct)
                if success:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"[{timestamp}] {n_sessions} session(s), {model}, {context_pct}% ctx")
                    last_push = current
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

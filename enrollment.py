#!/usr/bin/env python3
"""
enrollment.py
Pushes Tradewinds enrollment stats to AWTRIX display (pixels.local).

Two apps cycle every 3s:
  - tw_enrolled: green checkmark + enrolled count
  - tw_applied:  yellow pencil + applied count

Uses base64-encoded static icons to avoid animation issues.
"""

import json
import urllib.request
import warnings
import sys
import io
import base64
from PIL import Image

warnings.filterwarnings('ignore')

# ── Config ────────────────────────────────────────────────────────────────────
AWTRIX_HOST   = "http://192.168.6.1"
SA_FILE       = "/Users/andy/.openclaw/workspace/moli-tradewinds-42754805b6de.json"
SHEET_ID      = "1oD6SGBBLHGibZwjOKHe8GTG-g4AbL9rH2T1Wb65Ftlc"
STATUS_COLUMN = 5  # 0-indexed column F = "Status"

# ── Static 8x8 Icons (generated once) ─────────────────────────────────────────
def make_checkmark_icon():
    """Green checkmark on black background."""
    img = Image.new('RGB', (8, 8), (0, 0, 0))
    pixels = [
        (6, 1), (5, 2), (6, 2), (4, 3), (5, 3),
        (0, 4), (3, 4), (4, 4), (0, 5), (1, 5), (2, 5), (3, 5),
        (1, 6), (2, 6)
    ]
    for x, y in pixels:
        img.putpixel((x, y), (0, 255, 0))
    return img_to_base64(img)

def make_pencil_icon():
    """Yellow/orange pencil on black background."""
    img = Image.new('RGB', (8, 8), (0, 0, 0))
    # Pencil shape (diagonal)
    pixels = [
        # Tip (yellow)
        (5, 0, (255, 200, 0)), (6, 0, (255, 200, 0)),
        (4, 1, (255, 200, 0)), (5, 1, (255, 200, 0)), (6, 1, (255, 180, 100)), (7, 1, (200, 150, 100)),
        # Body (orange/yellow gradient)
        (3, 2, (255, 200, 0)), (4, 2, (255, 200, 0)), (5, 2, (255, 180, 50)), (6, 2, (200, 150, 100)),
        (2, 3, (255, 200, 0)), (3, 3, (255, 200, 0)), (4, 3, (255, 180, 50)), (5, 3, (180, 140, 80)),
        (1, 4, (255, 200, 0)), (2, 4, (255, 200, 0)), (3, 4, (255, 180, 50)), (4, 4, (180, 140, 80)),
        (0, 5, (200, 180, 0)), (1, 5, (255, 200, 0)), (2, 5, (255, 180, 50)), (3, 5, (180, 140, 80)),
        (0, 6, (200, 180, 0)), (1, 6, (200, 180, 0)), (2, 6, (180, 140, 80)),
        (0, 7, (150, 120, 60)), (1, 7, (180, 140, 80)),
    ]
    for item in pixels:
        x, y, color = item
        img.putpixel((x, y), color)
    return img_to_base64(img)

def img_to_base64(img):
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=95)
    return base64.b64encode(buf.getvalue()).decode()

# Pre-generate icons
ICON_CHECKMARK = make_checkmark_icon()
ICON_PENCIL = make_pencil_icon()

# ── Spreadsheet ───────────────────────────────────────────────────────────────
def get_counts():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        SA_FILE,
        scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
    )
    service = build('sheets', 'v4', credentials=creds)
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range='Applicants!A1:P200'
    ).execute()
    rows = result.get('values', [])

    accepted = 0
    applied  = 0
    for row in rows[1:]:  # skip header
        if len(row) <= STATUS_COLUMN:
            continue
        status = row[STATUS_COLUMN].strip()
        if status == 'A-Enrolled':
            accepted += 1
        elif status == 'Applied':
            applied += 1

    return accepted, applied

# ── AWTRIX push ───────────────────────────────────────────────────────────────
def push_app(name, icon_b64, text, color):
    payload = json.dumps({
        "icon":     icon_b64,
        "text":     text,
        "color":    color,
        "duration": 3,
        "lifetime": 0,
    }).encode()
    url = f"{AWTRIX_HOST}/api/custom?name={name}"
    req = urllib.request.Request(
        url, data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    return urllib.request.urlopen(req, timeout=10).status

def push_enrollment(accepted, applied):
    push_app("tw_enrolled", ICON_CHECKMARK, str(accepted), "#00FF00")
    push_app("tw_applied",  ICON_PENCIL,    str(applied),  "#FFD700")

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        accepted, applied = get_counts()
        print(f"Enrolled: {accepted}, Applied: {applied}")
        push_enrollment(accepted, applied)
        print("✅ Display updated")
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)

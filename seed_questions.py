"""
Seeds Round 1-4 question banks into the live Project Nexus backend.

Usage:
    pip install requests
    python seed_questions.py

Edit API_BASE and ADMIN_KEY below before running, or set them as
environment variables (NEXUS_API_BASE, NEXUS_ADMIN_KEY).
"""
import json
import os
import sys
import requests

API_BASE = os.getenv("NEXUS_API_BASE", "https://project-victory-production-d780.up.railway.app")
ADMIN_KEY = os.getenv("NEXUS_ADMIN_KEY", "nexus_activate")

ROUND_FILES = [
    "round1_questions.json",
    "round2_questions.json",
    "round3_questions.json",
    "round4_questions.json",
]

def main():
    if "your-app" in API_BASE or "PUT_YOUR_REAL" in ADMIN_KEY:
        print("Edit API_BASE and ADMIN_KEY at the top of this script (or set")
        print("NEXUS_API_BASE / NEXUS_ADMIN_KEY env vars) before running.")
        sys.exit(1)

    for filename in ROUND_FILES:
        if not os.path.exists(filename):
            print(f"Skipping {filename} (not found in this folder).")
            continue

        with open(filename, "r", encoding="utf-8") as f:
            payload = json.load(f)

        resp = requests.post(
            f"{API_BASE}/api/admin/questions",
            headers={"Content-Type": "application/json", "x-admin-key": ADMIN_KEY},
            json=payload,
            timeout=15,
        )

        if resp.ok:
            data = resp.json()
            print(f"Round {payload['round_number']}: synced {data['question_count']} questions.")
        else:
            print(f"Round {payload['round_number']}: FAILED ({resp.status_code}) — {resp.text}")

if __name__ == "__main__":
    main()

"""Add GitHub Gist relay to the KAAL server."""
import requests

GITHUB_TOKEN = "YOUR_GITHUB_PAT_HERE"
GIST_ID = "f7469bd497be819b3fe1485aa5b48ce9"

print("Adding GitHub Gist relay to KAAL server...")
data = {
    "relay_type": "github",
    "relay_id": "gist-relay",
    "token": GITHUB_TOKEN,
    "gist_id": GIST_ID,
}

try:
    resp = requests.post("http://localhost:5000/api/relay/add", json=data, timeout=5)
    if resp.status_code == 200:
        print("✅ GitHub Gist relay added!")
        print(f"\nNow start the agent on any machine:")
        print(f"  python standalone_agent.py")
    else:
        print(f"❌ Error {resp.status_code}: {resp.text}")
except Exception as e:
    print(f"❌ Error: {e}")
    print("Is the server running? Start it with:")
    print("  cd web && python -m uvicorn web.server:app --host 0.0.0.0 --port 5000")

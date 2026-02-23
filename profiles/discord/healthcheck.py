#!/usr/bin/env python3
"""
Health check for Discord C2 profile container.
Returns 0 if healthy, 1 if unhealthy.
"""

import sys
import requests
import time
import os
import yaml

def check_health():
    """Perform health checks."""
    print("Starting health check...")
    try:
        # 1. Check Config
        config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
        if not os.path.exists(config_path):
            print(f"❌ Config file not found at {config_path}")
            return 1
            
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        # 2. Check Discord Reachability
        resp = requests.get(
            "https://discord.com/api/v10/gateway",
            timeout=5
        )
        if resp.status_code != 200:
            print(f"❌ Discord API unreachable: {resp.status_code}")
            return 1
        print("✅ Discord API reachable")
            
        # 3. Check KAAL Server Connectivity
        # optional: only if needed for strict health
        kaal = config.get('kaal_server', {})
        host = kaal.get('host', 'localhost')
        port = kaal.get('port', 5000)
        schema = "https" if kaal.get('use_https') else "http"
        
        try:
            requests.get(f"{schema}://{host}:{port}/api/health", timeout=2)
            print("✅ KAAL Server reachable")
        except:
             print("⚠️ KAAL Server unreachable (Warning only)")
             
        # All checks passed
        print("✅ Health check passed")
        return 0
        
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(check_health())

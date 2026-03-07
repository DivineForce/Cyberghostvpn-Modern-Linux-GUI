from __future__ import annotations
import json
import urllib.request

def fetch_ip_info(timeout: int = 8) -> dict:
    req = urllib.request.Request("https://ipapi.co/json/", headers={"User-Agent": "CyberGhostModern/6.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="ignore"))
    return {
        "ip": str(data.get("ip", "")),
        "city": str(data.get("city", "")),
        "region": str(data.get("region", "")),
        "country": str(data.get("country_name", "")),
        "org": str(data.get("org", "")),
        "country_code": str(data.get("country_code", "")).upper(),
    }

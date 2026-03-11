from __future__ import annotations
import json
import urllib.request

def fetch_ip_info(timeout: int = 8) -> dict:
    providers = [
        ("https://ipapi.co/json/", "ipapi"),
        ("https://ipwho.is/", "ipwhois"),
    ]
    last_exc: Exception | None = None

    for url, provider in providers:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CyberGhostModern/6.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            return _normalize(data, provider)
        except Exception as exc:
            last_exc = exc
            continue

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("IP lookup failed.")


def _normalize(data: dict, provider: str) -> dict:
    if provider == "ipwhois":
        return {
            "ip": str(data.get("ip", "")),
            "city": str(data.get("city", "")),
            "region": str(data.get("region", "")),
            "country": str(data.get("country", "")),
            "org": str(data.get("connection", {}).get("org", "")),
            "country_code": str(data.get("country_code", "")).upper(),
        }

    return {
        "ip": str(data.get("ip", "")),
        "city": str(data.get("city", "")),
        "region": str(data.get("region", "")),
        "country": str(data.get("country_name", "")),
        "org": str(data.get("org", "")),
        "country_code": str(data.get("country_code", "")).upper(),
    }

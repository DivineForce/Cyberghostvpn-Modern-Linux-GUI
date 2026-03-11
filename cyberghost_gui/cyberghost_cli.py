from __future__ import annotations
import re
import subprocess
from .config import CYBERGHOST_BIN

COUNTRY_RE = re.compile(r"\|\s*\d+\s*\|\s*(.*?)\s*\|\s*([A-Z]{2})\s*\|")
CITY_SERVER_RE = re.compile(r"\|\s*\d+\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*\d+%")

class CyberGhostCliError(RuntimeError):
    pass

def _run(args: list[str]) -> str:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise CyberGhostCliError(
            "CyberGhost CLI binary was not found. Set CYBERGHOST_BIN or install `cyberghostvpn`."
        ) from exc
    if proc.returncode != 0:
        raise CyberGhostCliError(proc.stderr.strip() or proc.stdout.strip() or "CyberGhost CLI failed")
    return proc.stdout

def list_countries() -> dict[str, str]:
    output = _run([CYBERGHOST_BIN, "--country-code"])
    countries = {}
    for line in output.splitlines():
        m = COUNTRY_RE.match(line)
        if m:
            name, code = m.groups()
            countries[name.strip()] = code.strip()
    if not countries:
        raise CyberGhostCliError("No countries found.")
    return dict(sorted(countries.items(), key=lambda kv: kv[0].lower()))

def list_cities(country_code: str) -> list[str]:
    output = _run([CYBERGHOST_BIN, "--country-code", country_code, "--city"])
    cities = []
    for line in output.splitlines():
        m = CITY_SERVER_RE.match(line)
        if m:
            city, _ = m.groups()
            city = city.strip()
            if city not in cities:
                cities.append(city)
    if not cities:
        raise CyberGhostCliError(f"No cities found for {country_code}.")
    return sorted(cities, key=str.lower)

def list_servers(country_code: str, city: str) -> list[str]:
    output = _run([CYBERGHOST_BIN, "--country-code", country_code, "--city", city])
    servers = []
    for line in output.splitlines():
        m = CITY_SERVER_RE.match(line)
        if m:
            _city, instance = m.groups()
            instance = instance.strip()
            if instance:
                servers.append(instance)
    if not servers:
        raise CyberGhostCliError(f"No servers found for {city} ({country_code}).")
    return sorted(servers, key=str.lower)

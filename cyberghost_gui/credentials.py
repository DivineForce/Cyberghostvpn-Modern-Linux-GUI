from __future__ import annotations
import configparser
from pathlib import Path
from .models import Credentials, Paths

def _read_ini_credentials(path: Path) -> Credentials | None:
    if not path.exists():
        return None
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    if parser.has_section("device"):
        token = parser.get("device", "token", fallback="").strip()
        secret = parser.get("device", "secret", fallback="").strip()
        if token and secret:
            return Credentials(token, secret, path, "device.token", "device.secret")
    if parser.has_section("account"):
        username = parser.get("account", "username", fallback="").strip()
        password = parser.get("account", "password", fallback="").strip()
        if username and password:
            return Credentials(username, password, path, "account.username", "account.password")
    return None

def _read_token_file(path: Path) -> Credentials | None:
    if not path.exists():
        return None
    values = {}
    raw = path.read_text(encoding="utf-8", errors="ignore")
    for line in raw.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip().lower()] = value.strip()
    token = values.get("token", "")
    secret = values.get("secret", "")
    if token and secret:
        return Credentials(token, secret, path, "token", "secret")
    return None

def discover_credentials(paths: Paths) -> Credentials | None:
    creds = _read_ini_credentials(paths.config_ini)
    if creds and creds.username_key == "device.token":
        return creds
    token_creds = _read_token_file(paths.token_file)
    if token_creds:
        return token_creds
    return creds

def write_auth_file(paths: Paths, creds: Credentials) -> Path:
    paths.auth_file.parent.mkdir(parents=True, exist_ok=True)
    paths.auth_file.write_text(f"{creds.username}\n{creds.password}\n", encoding="utf-8")
    paths.auth_file.chmod(0o600)
    return paths.auth_file

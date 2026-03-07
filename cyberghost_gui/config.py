from __future__ import annotations
import os
from pathlib import Path
from .models import Paths

APP_TITLE = "CyberGhost Modern"
OPENVPN_BIN = os.environ.get("OPENVPN_BIN", "openvpn")
CYBERGHOST_BIN = os.environ.get("CYBERGHOST_BIN", "cyberghostvpn")
WINDOW_SIZE = "1180x800"

def build_paths() -> Paths:
    home = Path.home()
    cg = home / ".cyberghost"
    cert_dir = Path("/usr/local/cyberghost/certs/openvpn")
    return Paths(
        config_ini=cg / "config.ini",
        token_file=cg / "token",
        auth_file=cg / "auth",
        cert_dir=cert_dir,
        ca_cert=cert_dir / "ca.crt",
        client_cert=cert_dir / "client.crt",
        client_key=cert_dir / "client.key",
        cache_file=cg / "server_cache.json",
        profiles_file=cg / "profiles.json",
        settings_file=cg / "ui_settings.json",
        icon_file=cg / "app_icon.png",
        flags_dir=cg / "flags",
    )

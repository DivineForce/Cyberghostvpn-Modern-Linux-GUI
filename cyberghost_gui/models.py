from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

@dataclass(frozen=True)
class Credentials:
    username: str
    password: str
    source: Path
    username_key: str
    password_key: str

@dataclass(frozen=True)
class Paths:
    config_ini: Path
    token_file: Path
    auth_file: Path
    cert_dir: Path
    ca_cert: Path
    client_cert: Path
    client_key: Path
    cache_file: Path
    profiles_file: Path
    settings_file: Path
    recents_file: Path
    session_file: Path
    icon_file: Path
    flags_dir: Path

@dataclass
class CacheData:
    countries: dict[str, str] = field(default_factory=dict)
    cities_by_country: dict[str, list[str]] = field(default_factory=dict)
    servers_by_city: dict[str, list[str]] = field(default_factory=dict)

@dataclass
class Profile:
    name: str
    country_name: str
    country_code: str
    city: str
    server: str
    protocol: str = "TCP"
    service: str = "openvpn"
    server_type: str = "traffic"

@dataclass
class Settings:
    autoconnect_last_profile: bool = False
    stop_vpn_on_exit: bool = True
    hide_logs_by_default: bool = False
    refresh_cache_on_start: bool = False
    default_protocol: str = "UDP"
    default_service: str = "openvpn"
    default_server_type: str = "traffic"
    auto_reconnect: bool = True
    kill_switch: bool = False


@dataclass
class RecentEntry:
    country_name: str
    country_code: str
    city: str
    server: str
    protocol: str = "UDP"
    service: str = "openvpn"
    server_type: str = "traffic"
    last_used: float = 0.0


@dataclass
class ActiveSession:
    pid: int
    instance: str
    protocol: str
    service: str
    country_name: str = "Unknown"
    country_code: str = ""
    city: str = ""
    server_type: str = "traffic"
    started_at: float = 0.0
    source: str = "tracked"

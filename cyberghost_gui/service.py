from __future__ import annotations
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from .credentials import discover_credentials, write_auth_file
from .cyberghost_cli import list_cities, list_countries, list_servers
from .ipinfo import fetch_ip_info
from .models import Paths, Profile, Settings
from .openvpn_runner import build_command, secure_private_key, spawn_openvpn, validate_environment
from .status_parser import classify_log_line
from .store import load_cache, save_cache, load_profiles, save_profiles, load_settings, save_settings

LogFn = Callable[[str], None]
StatusFn = Callable[[str, str], None]

class VpnService:
    def __init__(self, paths: Paths, logger: LogFn) -> None:
        self.paths = paths
        self.logger = logger
        self.proc: subprocess.Popen[str] | None = None
        self.cache = load_cache(paths)
        self.profiles = load_profiles(paths)
        self.settings = load_settings(paths)
        self.recents: list[str] = []
        self.connected_since: float | None = None
        self.stats_start_rx: int | None = None
        self.stats_start_tx: int | None = None
        self._proc_lock = threading.Lock()
        self._session_id = 0
        self._manual_stop_sessions: set[int] = set()
        self._last_disconnect_transient = False

    def prepare_credentials(self) -> bool:
        creds = discover_credentials(self.paths)
        if not creds:
            self.logger("No credentials found in config.ini or token file.")
            return False
        write_auth_file(self.paths, creds)
        self.logger(f"Credentials loaded from: {creds.source} [{creds.username_key}/{creds.password_key}]")
        warning = secure_private_key(self.paths)
        if warning:
            self.logger(warning)
        return True

    def get_countries(self, force_refresh: bool = False) -> dict[str, str]:
        if self.cache.countries and not force_refresh:
            return self.cache.countries
        self.cache.countries = list_countries()
        save_cache(self.paths, self.cache)
        return self.cache.countries

    def get_cities(self, country_code: str, force_refresh: bool = False) -> list[str]:
        if country_code in self.cache.cities_by_country and not force_refresh:
            return self.cache.cities_by_country[country_code]
        cities = list_cities(country_code)
        self.cache.cities_by_country[country_code] = cities
        save_cache(self.paths, self.cache)
        return cities

    def get_servers(self, country_code: str, city: str, force_refresh: bool = False) -> list[str]:
        key = f"{country_code}:{city}"
        if key in self.cache.servers_by_city and not force_refresh:
            return self.cache.servers_by_city[key]
        servers = list_servers(country_code, city)
        self.cache.servers_by_city[key] = servers
        save_cache(self.paths, self.cache)
        return servers

    def preview_command(self, instance: str, protocol: str = "TCP", service: str = "openvpn") -> str:
        return " ".join(build_command(instance, self.paths, protocol, service))

    def get_ip_info_text(self) -> tuple[str, dict]:
        info = fetch_ip_info()
        text = f"IP: {info['ip']} | {info['city']}, {info['region']}, {info['country']}"
        if info.get("org"):
            text += f" | {info['org']}"
        return text, info

    def add_recent(self, label: str) -> None:
        if label in self.recents:
            self.recents.remove(label)
        self.recents.insert(0, label)
        self.recents = self.recents[:12]

    def list_profiles(self) -> list[Profile]:
        return list(self.profiles)

    def save_profile(self, profile: Profile) -> None:
        self.profiles = [p for p in self.profiles if p.name != profile.name]
        self.profiles.append(profile)
        self.profiles.sort(key=lambda p: p.name.lower())
        save_profiles(self.paths, self.profiles)

    def delete_profile(self, name: str) -> None:
        self.profiles = [p for p in self.profiles if p.name != name]
        save_profiles(self.paths, self.profiles)

    def get_settings(self) -> Settings:
        return self.settings

    def get_uptime_seconds(self) -> int:
        if not self.connected_since:
            return 0
        return max(0, int(time.time() - self.connected_since))

    def get_tun_stats(self) -> tuple[int, int]:
        rx = 0
        tx = 0
        try:
            data = subprocess.check_output(["ip", "-s", "link", "show", "tun0"], text=True, stderr=subprocess.DEVNULL)
            lines = data.splitlines()
            for idx, line in enumerate(lines):
                if "RX:" in line and idx + 1 < len(lines):
                    nums = lines[idx + 1].split()
                    if nums:
                        rx = int(nums[0])
                if "TX:" in line and idx + 1 < len(lines):
                    nums = lines[idx + 1].split()
                    if nums:
                        tx = int(nums[0])
        except Exception:
            pass
        if self.stats_start_rx is None:
            self.stats_start_rx = rx
        if self.stats_start_tx is None:
            self.stats_start_tx = tx
        return max(0, rx - (self.stats_start_rx or 0)), max(0, tx - (self.stats_start_tx or 0))

    def update_settings(self, settings: Settings) -> None:
        self.settings = settings
        save_settings(self.paths, settings)

    def connect(self, instance: str, protocol: str, service: str, recent_label: str, on_line: LogFn, on_status: StatusFn, on_done: Callable[[], None]) -> None:
        errors = validate_environment(self.paths)
        if errors:
            for e in errors:
                on_line(e)
            on_status("error", "Missing required files.")
            on_done()
            return
        self.add_recent(recent_label)
        effective_service = service.lower()
        if effective_service != "openvpn":
            on_line("WireGuard/service-type UI is present, but custom direct connection remains OpenVPN-based in this build.")
            effective_service = "openvpn"
        with self._proc_lock:
            running_proc = self.proc if self.proc and self.proc.poll() is None else None
            running_session = self._session_id if running_proc else None

        if running_proc is not None and running_session is not None:
            on_line("Existing VPN session detected. Stopping it before reconnect...")
            if not self._stop_process(running_proc, running_session, on_line):
                on_status("error", "Failed to stop current VPN session.")
                on_done()
                return

        self._last_disconnect_transient = False
        try:
            proc = spawn_openvpn(instance, self.paths, protocol, effective_service)
        except Exception as exc:
            on_line(f"Failed to start OpenVPN: {exc}")
            on_status("error", "Could not launch OpenVPN.")
            on_done()
            return

        with self._proc_lock:
            self._session_id += 1
            session_id = self._session_id
            self.proc = proc

        def worker() -> None:
            last_state: str | None = None
            if proc.stdout is not None:
                for line in proc.stdout:
                    clean = line.rstrip()
                    on_line(clean)
                    state, msg = classify_log_line(clean)
                    if state:
                        last_state = state
                    if state == "connected":
                        self.connected_since = time.time()
                        self.stats_start_rx = None
                        self.stats_start_tx = None
                    if state and msg:
                        on_status(state, msg)
            on_line("[Disconnected]")
            was_connected = self.connected_since is not None
            manual_stop = session_id in self._manual_stop_sessions
            self._last_disconnect_transient = (
                (not manual_stop)
                and (was_connected or last_state in {"reconnecting", "connecting"})
                and last_state != "error"
            )
            self.connected_since = None
            self.stats_start_rx = None
            self.stats_start_tx = None
            with self._proc_lock:
                if self.proc is proc:
                    self.proc = None
            self._manual_stop_sessions.discard(session_id)
            on_done()

        threading.Thread(target=worker, daemon=True).start()

    def stop(self, on_line: LogFn | None = None) -> bool:
        log = on_line or self.logger
        with self._proc_lock:
            proc = self.proc if self.proc and self.proc.poll() is None else None
            session_id = self._session_id if proc else None
        if proc is not None and session_id is not None:
            log("Stopping VPN connection...")
            return self._stop_process(proc, session_id, log)
        log("No active VPN session.")
        return True

    def should_auto_reconnect(self) -> bool:
        return self._last_disconnect_transient

    def has_active_session(self) -> bool:
        with self._proc_lock:
            return self.proc is not None and self.proc.poll() is None

    def _stop_process(self, proc: subprocess.Popen[str], session_id: int, log: LogFn) -> bool:
        self._manual_stop_sessions.add(session_id)
        if proc.poll() is not None:
            return True
        try:
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=10)
            return True
        except subprocess.TimeoutExpired:
            log("OpenVPN did not stop in time. Terminating process...")
            try:
                proc.terminate()
                proc.wait(timeout=5)
                return True
            except subprocess.TimeoutExpired:
                pass
            except Exception as exc:
                log(f"Terminate failed: {exc}")
        except Exception as exc:
            log(f"Signal SIGINT failed: {exc}")
        try:
            log("Force-killing OpenVPN process...")
            proc.kill()
            proc.wait(timeout=2)
            return True
        except Exception as exc:
            log(f"Kill failed: {exc}")
            return False
